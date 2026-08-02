"""专家团队模板接口（批八，ADR-0031）：可保存/可复用/召集前对账的团队蓝本。

三端点：POST /api/teams（从导引会话方案存蓝本——**不接受前端直传成员列表**，
蓝本必须源自会话 recommendation 快照，存入时按后端规则重验，guide 校验层不被
信任为唯一防线）；GET /api/teams(+/{id})（只读投影，团队密级展示口径 =
min(成员 clearance)，**仅展示**——召集判定仍按成员各自 clearance）；
POST /api/teams/{id}/summon（对账 gate G1-G5 fail-closed → seq 升序重排 →
复用 tasks.run_batch_creation 同一创建内核，密级 gate/事务原子/charter 事件
零平行实现）。

对账时点诚实边界（ADR-0031）：对账读 registry 内存态在创建事务之前，窗口不设锁
（与 create_task 单建同宽）；执行期 runtime._execute 的未注册/版本漂移/disabled
三兜底闭合残窗。
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .tasks import (
    BatchTaskItem,
    _get_package_snapshot_or_none,
    _package_snapshot_parts,
    run_batch_creation,
)
from ..storage import repos

router = APIRouter(prefix="/api", tags=["teams"])

_MAX_MEMBERS = 5  # 同 guide _MAX_AGENTS 口径

_CLEARANCE_RANK = {"public": 0, "internal": 1, "sensitive": 2}


def _agent_clearance(agent: dict[str, Any]) -> str:
    return ((agent.get("clearance") or {}).get("max_data_classification")) or "internal"


def _team_projection(team: dict[str, Any], agent_registry: Any) -> dict[str, Any]:
    """列表/详情投影：成员按 seq + 团队密级 min 口径（仅展示）+ 成员现势快照
    （在场/禁用/现版本——前端召集入口据此预先置灰，权威判定仍在 summon 对账）。"""
    members = []
    min_rank = _CLEARANCE_RANK["sensitive"]
    for m in team["members"]:
        agent = agent_registry.get(m["agent_id"])
        clearance = _agent_clearance(agent) if agent is not None else None
        # 缺位成员按最保守 internal 参与取 min（Codex R0 P3：此前跳过缺位成员，
        # 全员缺位或缺位+高位组合会虚标 sensitive——注释口径与代码不一致）。
        min_rank = min(
            min_rank,
            _CLEARANCE_RANK.get(clearance, 1) if clearance is not None else _CLEARANCE_RANK["internal"],
        )
        members.append(
            {
                "seq": m["seq"],
                "agent_id": m["agent_id"],
                "role": m.get("role"),
                "after": m["after"],
                "agent_version_at_save": m["agent_version_at_save"],
                "current_version": (agent or {}).get("version"),
                "present": agent is not None,
                "disabled": (agent or {}).get("status") == "disabled",
            }
        )
    return {
        "id": team["id"],
        "name": team["name"],
        "goal_template": team.get("goal_template"),
        "owner_user": team["owner_user"],
        "created_from_conversation_id": team.get("created_from_conversation_id"),
        "created_at": team["created_at"],
        "members": members,
        # min 口径（仅展示）：成员缺位时按最保守 internal 参与取 min，不虚标高位。
        "clearance_display": next(
            k for k, v in _CLEARANCE_RANK.items() if v == min_rank
        ),
    }


class CreateTeamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=64)


@router.post("/teams")
def create_team(body: CreateTeamRequest, request: Request) -> dict[str, Any]:
    """从会话方案存团队蓝本。成员/顺序/after 全部取自该会话 recommendation
    （decision=orchestrate）快照并按后端规则重验（R5 纵深）：agent 在场、未禁用、
    非 interactive、after 仅引更早条目、≤5 席。任一不过 → 422 逐条清单零写入。"""
    agent_registry = request.app.state.agent_registry
    conn = request.app.state.conn_factory()
    try:
        conv = repos.get_conversation(conn, body.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{body.conversation_id}")
        rec = conv.get("recommendation") or {}
        plan_agents = rec.get("agents") or []
        if rec.get("decision") != "orchestrate" or not plan_agents:
            raise HTTPException(
                status_code=422,
                detail="该会话没有结构化协作方案（decision=orchestrate）——团队蓝本必须源自导引方案",
            )
        if len(plan_agents) > _MAX_MEMBERS:
            raise HTTPException(
                status_code=422, detail=f"方案成员数 {len(plan_agents)} 超上限 {_MAX_MEMBERS}"
            )
        errors: list[str] = []
        members: list[dict[str, Any]] = []
        for idx, a in enumerate(plan_agents):
            agent_id = a.get("agent_id")
            agent = agent_registry.get(agent_id) if agent_id else None
            if agent is None:
                errors.append(f"席位 {idx}：agent 不存在或已拒载：{agent_id!r}")
                continue
            if agent.get("status") == "disabled":
                errors.append(f"席位 {idx}：agent 已下线：{agent_id}")
                continue
            if (agent.get("workflow", {}) or {}).get("mode") == "interactive":
                errors.append(f"席位 {idx}：interactive Agent 不可入团队（job 型才可召集）：{agent_id}")
                continue
            after = a.get("after")
            after = [d for d in after if isinstance(d, int)] if isinstance(after, list) else []
            bad = [d for d in after if not (0 <= d < idx)]
            if bad:
                errors.append(f"席位 {idx}：after 引用非法（仅可引更早席位）：{bad}")
                continue
            members.append(
                {
                    "agent_id": agent_id,
                    "agent_version_at_save": agent.get("version") or "0.0.0",
                    "role": a.get("role"),
                    "seq": idx,
                    "after": sorted(set(after)),
                }
            )
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "团队未保存（全有全无）", "team_errors": errors},
            )
        team_id = f"team_{uuid.uuid4().hex}"
        conn.execute("BEGIN IMMEDIATE")
        try:
            team = repos.create_team(
                conn,
                team_id=team_id,
                name=body.name,
                owner_user=request.state.user["username"],
                members=members,
                goal_template=(rec.get("goal") or None),
                created_from_conversation_id=body.conversation_id,
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return _team_projection(team, agent_registry)
    finally:
        conn.close()


@router.get("/teams")
def list_teams(request: Request, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    """列表（新→旧）。分页参数（Codex R2 P2）：repos 默认 LIMIT 100 此前是静默
    截断——超过 100 份蓝本后旧团队从 UI 永久失联；limit/offset 显式暴露翻页能力
    （门户当前只取首页，翻页 UI 随规模需要再长）。"""
    if not (1 <= limit <= 500):
        raise HTTPException(status_code=422, detail="limit 取值 1..500")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset 不得为负")
    agent_registry = request.app.state.agent_registry
    conn = request.app.state.conn_factory()
    try:
        return [
            _team_projection(t, agent_registry)
            for t in repos.list_teams(conn, limit=limit, offset=offset)
        ]
    finally:
        conn.close()


@router.get("/teams/{team_id}")
def get_team(team_id: str, request: Request) -> dict[str, Any]:
    conn = request.app.state.conn_factory()
    try:
        team = repos.get_team(conn, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=f"团队不存在：{team_id}")
        return _team_projection(team, request.app.state.agent_registry)
    finally:
        conn.close()


class SummonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: StrictInt
    inputs: dict[str, Any] = Field(default_factory=dict)
    input_file_ids: list[str] = Field(default_factory=list, max_length=64)


class SummonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SummonItem] = Field(min_length=1, max_length=_MAX_MEMBERS)
    conversation_id: str | None = Field(default=None, max_length=64)


def _version_drift_rejects(saved: str, current: str) -> bool:
    """G4：major 变化，或 0.x 期 minor 变化 → 拒；patch 不拒。任一侧解析失败
    按 major 变化处理（fail-closed；schema pattern 下结构上不可达，纵深兜底）。"""
    try:
        s_major, s_minor, _ = (int(x) for x in saved.split("."))
        c_major, c_minor, _ = (int(x) for x in current.split("."))
    except (ValueError, AttributeError):
        return True
    if s_major != c_major:
        return True
    if s_major == 0 and s_minor != c_minor:
        return True
    return False


@router.post("/teams/{team_id}/summon")
def summon_team(team_id: str, body: SummonRequest, request: Request) -> dict[str, Any]:
    """召集：对账 gate G1-G5 fail-closed（422 逐席位清单零写入）→ 按 seq 升序
    重排（**绝不信任客户端提交顺序**：after_json 存 seq 值、batch after 是数组
    位置下标，乱序直译会建错依赖边）→ 复用 run_batch_creation。"""
    agent_registry = request.app.state.agent_registry
    conn = request.app.state.conn_factory()
    try:
        team = repos.get_team(conn, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail=f"团队不存在：{team_id}")

        # G5：席位对齐——不多、不少、不重。
        member_by_seq = {m["seq"]: m for m in team["members"]}
        item_seqs = [it.seq for it in body.items]
        errors: list[str] = []
        if len(item_seqs) != len(set(item_seqs)):
            errors.append("席位 seq 重复")
        missing = sorted(set(member_by_seq) - set(item_seqs))
        extra = sorted(set(item_seqs) - set(member_by_seq))
        if missing:
            errors.append(f"缺席位：{missing}（召集是整团动作，逐席位补参后提交）")
        if extra:
            errors.append(f"多余席位：{extra}（团队没有这些 seq）")
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "召集未发起（对账不过，整单拒发）", "summon_errors": errors},
            )

        # G1-G4：逐席位对账（读 registry 现势）。pinned_versions 记对账时点观察
        # 到的现势版本，随后传入 run_batch_creation 钉版本校验（Codex R0 P1：
        # 闭「对账后 registry 热切换不兼容版→新版被盖进任务→runtime 漂移复检
        # 恒过」的 TOCTOU 旁路）。
        warnings: list[str] = []
        pinned_versions: dict[str, str] = {}
        pinned_package_digests: dict[str, str] = {}
        for m in team["members"]:
            snapshot = _get_package_snapshot_or_none(agent_registry, m["agent_id"])
            label = f"席位 {m['seq']}（{m['agent_id']}）"
            if snapshot is None:
                errors.append(
                    f"{label}：agent 不在注册表或不可变包快照不可用（已下架或拒载隔离）"
                )
                continue
            snapshot_parts = _package_snapshot_parts(snapshot, m["agent_id"])
            if snapshot_parts is None:
                errors.append(f"{label}：Agent 不可变包快照结构或摘要无效")
                continue
            agent, snapshot_digest = snapshot_parts
            if agent.get("status") == "disabled":
                errors.append(f"{label}：agent 已下线")
                continue
            if (agent.get("workflow", {}) or {}).get("mode") == "interactive":
                errors.append(f"{label}：agent 已变更为 interactive，团队蓝本失效")
                continue
            saved, current = m["agent_version_at_save"], agent.get("version") or ""
            if saved != current:
                if _version_drift_rejects(saved, current) is True:
                    errors.append(
                        f"{label}：版本漂移 {saved} → {current}（major/0.x-minor 变化）"
                        "——请从最新导引方案另存新团队"
                    )
                else:
                    warnings.append(f"{label}：版本 {saved} → {current}（patch 变化，放行）")
            pinned_versions[m["agent_id"]] = current
            pinned_package_digests[m["agent_id"]] = snapshot_digest
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "召集未发起（对账不过，整单拒发）", "summon_errors": errors},
            )

        # seq 升序重排 → seq 值映射为数组位置下标（auditor F3）。
        ordered_seqs = sorted(member_by_seq)
        pos_of_seq = {seq: pos for pos, seq in enumerate(ordered_seqs)}
        item_by_seq = {it.seq: it for it in body.items}
        # 材料校验（Codex R0 P2）：SummonItem 不带 BatchTaskItem 的尺寸/文件 id
        # validator，超限 inputs / 空白重复 file id / 超长 role 会在此构造时抛
        # ValidationError——逐席位捕获译成结构化 422（material_errors 独立列表，
        # 不与上方 gate 的 errors 混流），绝不放大成 500。
        batch_items: list[BatchTaskItem] = []
        material_errors: list[str] = []
        for seq in ordered_seqs:
            m = member_by_seq[seq]
            it = item_by_seq[seq]
            try:
                batch_items.append(
                    BatchTaskItem(
                        agent_id=m["agent_id"],
                        # role→任务名收口到 200（Codex R1 P2）：导引 role 上限 2000、
                        # BatchTaskItem.name 上限 200——不收口则长 role 团队存得进但
                        # 每次召集都被材料校验拒发（合法蓝本永久死锁）。蓝本存储的
                        # role 原文不动（展示轴），只在盖任务名时截断。
                        name=((m.get("role") or "").strip()[:200] or None),
                        inputs=it.inputs,
                        input_file_ids=it.input_file_ids,
                        after=[pos_of_seq[d] for d in m["after"] if d in pos_of_seq],
                    )
                )
            except ValidationError as exc:
                first = (exc.errors() or [{}])[0]
                material_errors.append(
                    f"席位 {seq}（{m['agent_id']}）：材料不合法——{str(first.get('msg') or exc)[:200]}"
                )
        if material_errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "召集未发起（材料校验不过，整单拒发）",
                    "summon_errors": material_errors,
                },
            )
        result = run_batch_creation(
            conn=conn,
            agent_registry=agent_registry,
            items=batch_items,
            conversation_id=body.conversation_id,
            created_by=request.state.user["display_name"],
            created_by_username=request.state.user["username"],
            pinned_versions=pinned_versions,
            pinned_package_digests=pinned_package_digests,
        )
        result["team_id"] = team_id
        result["warnings"] = warnings
        return result
    finally:
        conn.close()
