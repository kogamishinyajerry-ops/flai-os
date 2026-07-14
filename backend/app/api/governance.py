"""治理闭环 API（M10/ADR-0018）：评测跑批 / 样本固化 / L0→L1 晋升。

- POST /api/agents/{id}/eval-runs      触发一次评测跑批（V0.1 同步执行）
- GET  /api/agents/{id}/eval-runs      跑批历史（证据链，最近优先）
- POST /api/agents/{id}/eval-cases     认可样本固化为 draft eval case
- POST /api/agents/{id}/promote        L0→L1 晋升（fail-closed，422 携逐条判定）
- GET  /api/agents/{id}/promotions     晋升审计记录
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ..governance import curation, eval_runner, promotion
from ..storage import repos

router = APIRouter(prefix="/api", tags=["governance"])


def _agent_or_404(request: Request, agent_id: str) -> dict[str, Any]:
    registry = request.app.state.agent_registry
    try:
        agent = registry.get(agent_id)
    except KeyError:
        agent = None
    if agent is None:
        raise HTTPException(status_code=404, detail=f"agent 不存在：{agent_id}")
    return agent


# ADR-0019 D5：triggered_by 已从请求体删除——发起人=登录会话身份。请求体只剩
# 空对象（保留 body 形态，extra="forbid" 让仍发 triggered_by 的旧客户端 422）。
class TriggerEvalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/agents/{agent_id}/eval-runs")
def trigger_eval_run(agent_id: str, body: TriggerEvalRequest, request: Request) -> dict[str, Any]:
    _agent_or_404(request, agent_id)
    try:
        return eval_runner.run_agent_evals(
            conn_factory=request.app.state.conn_factory,
            agent_registry=request.app.state.agent_registry,
            runtime=request.app.state.runtime,
            uploads_dir=request.app.state.uploads_dir,
            task_runs_dir=request.app.state.task_runs_dir,
            agent_id=agent_id,
            triggered_by=request.state.user["display_name"],  # ADR-0019 D5
        )
    except eval_runner.EvalBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/eval-runs")
def list_eval_runs(agent_id: str, request: Request) -> list[dict[str, Any]]:
    _agent_or_404(request, agent_id)
    conn = request.app.state.conn_factory()
    try:
        return repos.list_eval_runs(conn, agent_id)
    finally:
        conn.close()


class FixSampleRequest(BaseModel):
    # ADR-0019 D5：fixed_by 已删——固化人=登录会话身份（记名进 provenance）
    model_config = ConfigDict(extra="forbid")

    sample_id: int


@router.post("/agents/{agent_id}/eval-cases")
def fix_sample(agent_id: str, body: FixSampleRequest, request: Request) -> dict[str, Any]:
    _agent_or_404(request, agent_id)
    try:
        return curation.fix_sample_as_eval_case(
            conn_factory=request.app.state.conn_factory,
            agent_registry=request.app.state.agent_registry,
            agent_id=agent_id,
            sample_id=body.sample_id,
            fixed_by=request.state.user["display_name"],  # ADR-0019 D5
        )
    except curation.SampleAlreadyFixed as exc:
        raise HTTPException(
            status_code=409,
            detail=f"样本已固化为 {exc.case_file}，拒绝重复生成",
        ) from exc
    except curation.CurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class PromoteRequest(BaseModel):
    # ADR-0019 D5：confirmed_by 已删——晋升门第五条的记名从此指向认证身份。
    model_config = ConfigDict(extra="forbid")

    to_maturity: str
    eval_run_id: str
    # 显式不给默认值结构：缺失/false/非 bool 都要走到门内被 is True 拒绝，
    # 而不是被请求模型偷偷归一化（D6）。
    confirmations: dict[str, Any] = Field(default_factory=dict)


@router.post("/agents/{agent_id}/promote")
def promote(agent_id: str, body: PromoteRequest, request: Request) -> dict[str, Any]:
    _agent_or_404(request, agent_id)
    try:
        return promotion.promote_agent(
            conn_factory=request.app.state.conn_factory,
            agent_registry=request.app.state.agent_registry,
            scope_registry=request.app.state.scope_registry,
            agent_id=agent_id,
            to_maturity=body.to_maturity,
            eval_run_id=body.eval_run_id,
            confirmations=body.confirmations,
            confirmed_by=request.state.user["display_name"],  # ADR-0019 D5
        )
    except promotion.PromotionRejected as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": "晋升条件未全部满足", "checks": exc.checks},
        ) from exc


@router.get("/agents/{agent_id}/promotions")
def list_promotions(agent_id: str, request: Request) -> list[dict[str, Any]]:
    _agent_or_404(request, agent_id)
    conn = request.app.state.conn_factory()
    try:
        return repos.list_promotions(conn, agent_id)
    finally:
        conn.close()


@router.get("/promotions")
def list_promotions_all(request: Request, limit: int = 20) -> list[dict[str, Any]]:
    """全局最近晋升（批B /today）。只读；limit 夹取 1-100 防全表倾倒。"""
    limit = max(1, min(int(limit), 100))
    conn = request.app.state.conn_factory()
    try:
        return repos.list_promotions_all(conn, limit)
    finally:
        conn.close()


@router.get("/agents/{agent_id}/curated_cases_count")
def curated_cases_count(agent_id: str, request: Request) -> dict[str, Any]:
    """该 agent 已固化 eval case 数（批C Agent 成长档案）。按仓内落盘文件计
    （ADR-0018 固化即落盘无 DB 行）。agent 不存在 404；目录缺失=0（不抛）。只读。"""
    _agent_or_404(request, agent_id)
    cases_dir = request.app.state.agents_dir / agent_id / "eval_cases"
    count = sum(1 for _ in cases_dir.glob("case_*.json")) if cases_dir.is_dir() else 0
    return {"agent_id": agent_id, "count": count}
