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
from pydantic import BaseModel, Field

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


class TriggerEvalRequest(BaseModel):
    triggered_by: str = Field(min_length=1, description="发起人（记名，证据链一环）")


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
            triggered_by=body.triggered_by,
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
    sample_id: int
    fixed_by: str = Field(min_length=1, description="固化人（记名进 provenance）")


@router.post("/agents/{agent_id}/eval-cases")
def fix_sample(agent_id: str, body: FixSampleRequest, request: Request) -> dict[str, Any]:
    _agent_or_404(request, agent_id)
    try:
        return curation.fix_sample_as_eval_case(
            conn_factory=request.app.state.conn_factory,
            agent_registry=request.app.state.agent_registry,
            agent_id=agent_id,
            sample_id=body.sample_id,
            fixed_by=body.fixed_by,
        )
    except curation.SampleAlreadyFixed as exc:
        raise HTTPException(
            status_code=409,
            detail=f"样本已固化为 {exc.case_file}，拒绝重复生成",
        ) from exc
    except curation.CurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class PromoteRequest(BaseModel):
    to_maturity: str
    eval_run_id: str
    # 显式不给默认值结构：缺失/false/非 bool 都要走到门内被 is True 拒绝，
    # 而不是被请求模型偷偷归一化（D6）。
    confirmations: dict[str, Any] = Field(default_factory=dict)
    confirmed_by: str = ""


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
            confirmed_by=body.confirmed_by,
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
