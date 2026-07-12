"""部署自检门（M11-C2）：内网部署后的轻量运行时探针，纯 stdlib，免 node/playwright。

用法（仓根执行；服务已启动后跑，全部 PASS 才算部署完成）：
    python3 scripts/deploy_selfcheck.py
    python3 scripts/deploy_selfcheck.py --base-url http://127.0.0.1:8620 --db data/flai_os.db

检查项（任一 FAIL → 退出码 1，fail-closed）：
    1. DB 文件存在且可打开
    2. 核心表齐全（缺表=init_db 没跑）
    3. ≥1 活跃账户（ADR-0019 D9：users 空=全员锁在门外，部署第一条命令是 user_admin.py create）
    4. 数据分级轴存在（files/samples 有 classification 列，ADR-0021 代际见证）
    5. worker 心跳+代际（Codex R1 审 P1）：Job Runner 是独立进程——API 换新而
       worker 未重启时，旧 worker 落库走 DDL DEFAULT 洗白派生分级。要求心跳
       60 秒内新鲜且代际=当前 WORKER_GENERATION。**部署顺序：先起 API+worker
       再跑本自检**，worker 未启动=FAIL 是有意判定。
    6. GET /api/health → 200 且 status=ok（服务活着）
    7. health 含 classification_axis=true（**API 运行进程**的 B2 代际见证，Codex
       审 P1：检查 4 只证明磁盘上的库迁移过——若服务重启失败仍是旧进程，库检
       查与鉴权 401 都会假 PASS，必须要活进程自报的代际标记）
    8. health.db_identity = 探针侧库路径指纹（Codex R1 审 P2：两侧 FLAI_DB_PATH
       不一致时，探针查有账户的库 A、服务连空库 B，其余全 PASS 却无人能登录）
    9. 未认证 GET /api/agents → 401（鉴权代际见证：200=裸奔旧代际，404=旧代码，
       同 promote_agent_l1.py 的 401-witness 口径）
    10. frontend/dist/index.html 存在（内网免 node 部署前提，由 FastAPI 静态托管）
    11. uploads/task_runs 目录可写（写删探针文件）

诚实边界：本脚本只验「部署形态正确」，不验业务正确性（那是 verify_all 的事，
在开发机跑）；也不验反代/TLS 等部署层配置（ADR-0019 威胁模型如实声明）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# 只从 config 导（纯 stdlib）——从 jobs.runner 导会连带拉 repos→jsonschema，
# 破坏本探针「免应用依赖、系统 Python 可跑」的承诺（Codex R2 审 P2）。
from backend.app import config  # noqa: E402

WORKER_GENERATION = config.WORKER_GENERATION
_WORKER_STALE_SECONDS = 60

# 缺任何一张=init_db 没跑或库文件指错——直接列全量九表+鉴权两表，不挑子集。
REQUIRED_TABLES = frozenset({
    "agents", "agent_versions", "tasks", "task_events", "files", "feedback",
    "tool_runs", "model_calls", "samples", "conversations",
    "conversation_messages", "eval_runs", "promotions", "users", "auth_sessions",
    "worker_heartbeats",
})

_HTTP_TIMEOUT = 10


class Check:
    """单项检查结果：ok 显式 True/False（安全 gate 判定不走 truthiness）。"""

    def __init__(self, name: str, ok: bool, detail: str) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail


def _http_get(url: str) -> tuple[int, bytes]:
    """返回 (status, body)。4xx/5xx 不抛——状态码本身就是探针的观测值。"""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def check_db_file(db_path: Path) -> Check:
    if db_path.is_file() is not True:
        return Check("DB 文件存在", False, f"未找到 {db_path}（先跑 scripts/init_db）")
    return Check("DB 文件存在", True, str(db_path))


def check_tables(conn: sqlite3.Connection) -> Check:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    present = {r[0] for r in rows}
    missing = sorted(REQUIRED_TABLES - present)
    if missing:
        return Check("核心表齐全", False, f"缺表 {missing}（先跑 scripts/init_db）")
    return Check("核心表齐全", True, f"{len(REQUIRED_TABLES)} 张表全部在位")


def check_active_user(conn: sqlite3.Connection) -> Check:
    n = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
    if n < 1:
        return Check(
            "≥1 活跃账户", False,
            "users 表无活跃账户——所有人被锁在登录门外（有意 fail-closed，"
            "ADR-0019 D9）。执行：python3 scripts/user_admin.py create <用户名> <显示名>",
        )
    return Check("≥1 活跃账户", True, f"活跃账户 {n} 个")


def check_classification_axis(conn: sqlite3.Connection) -> Check:
    missing = []
    for table in ("files", "samples"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "classification" not in cols:
            missing.append(table)
    if missing:
        return Check(
            "数据分级轴（ADR-0021）", False,
            f"{missing} 缺 classification 列——库是旧代际，先跑 scripts/init_db 迁移",
        )
    return Check("数据分级轴（ADR-0021）", True, "files/samples 均有 classification 列")


def check_worker_generation(conn: sqlite3.Connection) -> Check:
    """独立 worker 进程的代际见证（Codex R1 审 P1）：心跳 60s 内新鲜 + 代际
    匹配才 PASS。无表/无行/过期/代际不符/时间戳畸形（含 naive）全 FAIL。"""
    name = "worker 心跳代际"
    try:
        row = conn.execute(
            "SELECT generation, last_beat_at FROM worker_heartbeats WHERE worker_id='default'"
        ).fetchone()
    except sqlite3.Error as exc:
        return Check(name, False, f"worker_heartbeats 表不可读（旧库未迁移？）：{exc}")
    if row is None:
        return Check(
            name, False,
            "无 worker 心跳——worker 未启动，或为 B2 前旧代际（旧代码不写心跳）。"
            "部署顺序：先起 API+worker 再跑自检",
        )
    generation, last_beat = row[0], row[1]
    if generation != WORKER_GENERATION:
        return Check(
            name, False,
            f"worker 代际 {generation!r} ≠ 当前 {WORKER_GENERATION!r}——worker 未重启到新代码",
        )
    try:
        beat_time = datetime.fromisoformat(last_beat)
    except (ValueError, TypeError) as exc:
        return Check(name, False, f"心跳时间戳畸形：{last_beat!r}（{exc}）")
    if beat_time.tzinfo is None:
        return Check(name, False, f"心跳时间戳无时区（naive）：{last_beat!r}，fail-closed")
    age = datetime.now(timezone.utc) - beat_time
    if age > timedelta(seconds=_WORKER_STALE_SECONDS) or age < timedelta(seconds=-5):
        return Check(
            name, False,
            f"心跳过期（{age.total_seconds():.0f}s 前）——worker 已死或挂起",
        )
    return Check(name, True, f"代际 {generation}，{age.total_seconds():.0f}s 前心跳")


def _db_path_fingerprint(db_path: Path) -> str:
    return hashlib.sha256(str(db_path.resolve()).encode("utf-8")).hexdigest()[:16]


def check_db_identity(base_url: str, db_path: Path) -> Check:
    """服务侧库指纹 = 探针侧库指纹（Codex R1 审 P2）：两侧 FLAI_DB_PATH 不一致
    时其余检查全对不同的库各自 PASS，合起来是假绿。旧服务无此字段=FAIL。"""
    name = "库身份一致（服务=探针）"
    url = f"{base_url}/api/health"
    try:
        _, body = _http_get(url)
        payload = json.loads(body)
    except Exception as exc:
        return Check(name, False, f"{url} 不可达或非 JSON：{exc}")
    remote = payload.get("db_identity")
    local = _db_path_fingerprint(db_path)
    if remote is None:
        return Check(name, False, "health 无 db_identity 字段——服务代际过旧，无法证明库一致")
    if remote != local:
        return Check(
            name, False,
            f"服务连的库（{remote}）≠ 探针检查的库（{local}）——两侧 FLAI_DB_PATH 不一致，"
            "库检查结果对活服务无效",
        )
    return Check(name, True, f"指纹一致（{local}）")


def check_health(base_url: str) -> Check:
    url = f"{base_url}/api/health"
    try:
        status, body = _http_get(url)
    except Exception as exc:
        return Check("服务健康检查", False, f"{url} 不可达：{exc}（服务未启动或端口不对）")
    if status != 200:
        return Check("服务健康检查", False, f"{url} → HTTP {status}（期望 200）")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Check("服务健康检查", False, f"{url} 返回非 JSON（不是 FLAi-OS 后端？）")
    if payload.get("status") != "ok":
        return Check("服务健康检查", False, f"status={payload.get('status')!r}（期望 ok）")
    return Check("服务健康检查", True, f"agents={payload.get('agents')} tools={payload.get('tools')}")


def check_live_classification_generation(base_url: str) -> Check:
    """运行进程的 B2 代际见证（Codex 审 P1）：库列检查（检查 4）只证明磁盘，
    活进程必须自报 classification_axis 标记——否则「库已迁移+旧进程未重启」
    双假 PASS。判定 is True，不认 truthy。"""
    url = f"{base_url}/api/health"
    try:
        _, body = _http_get(url)
        payload = json.loads(body)
    except Exception as exc:
        return Check("运行进程分级代际", False, f"{url} 不可达或非 JSON：{exc}")
    if payload.get("classification_axis") is True:
        return Check("运行进程分级代际", True, "活进程自报 classification_axis=true")
    return Check(
        "运行进程分级代际", False,
        "health 无 classification_axis 标记——运行中的是 B2 之前的旧进程"
        "（库可能已迁移但服务未重启到新代码），fail-closed",
    )


def check_auth_generation(base_url: str) -> Check:
    """鉴权代际见证：匿名打有数据的端点，401 才是新代际的证词。

    200=default-deny 中间件缺位（裸奔，最坏结果）；404=旧代码；其余码如实报。
    """
    url = f"{base_url}/api/agents"
    try:
        status, _ = _http_get(url)
    except Exception as exc:
        return Check("鉴权门代际见证", False, f"{url} 不可达：{exc}")
    if status == 401:
        return Check("鉴权门代际见证", True, "未认证请求被 401 拒绝（default-deny 在位）")
    if status == 200:
        return Check("鉴权门代际见证", False, "未认证请求拿到 200——鉴权中间件缺位，API 裸奔！")
    return Check("鉴权门代际见证", False, f"未认证请求 → HTTP {status}（期望 401；404=旧代码）")


def check_frontend_dist() -> Check:
    index = config.FRONTEND_DIST_DIR / "index.html"
    if index.is_file() is not True:
        return Check(
            "前端静态资产", False,
            f"未找到 {index}——内网部署必须带预构建 dist（免 node），见离线包预案",
        )
    return Check("前端静态资产", True, str(index))


def check_writable_dirs() -> Check:
    problems = []
    for d in (config.UPLOADS_DIR, config.TASK_RUNS_DIR):
        probe = d / f".selfcheck_{uuid.uuid4().hex}"
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe.write_text("probe", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"{d}：{exc}")
    if problems:
        return Check("数据目录可写", False, "；".join(problems))
    return Check("数据目录可写", True, f"{config.UPLOADS_DIR} / {config.TASK_RUNS_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="FLAi-OS 部署自检门（M11-C2）")
    parser.add_argument(
        "--base-url", default=f"http://127.0.0.1:{config.BACKEND_PORT}",
        help="后端地址（默认 http://127.0.0.1:%(default_port)s，尊重 FLAI_BACKEND_PORT）"
             .replace("%(default_port)s", str(config.BACKEND_PORT)),
    )
    parser.add_argument(
        "--db", default=str(config.DB_PATH),
        help="SQLite 库路径（默认跟随 config.DB_PATH，尊重 FLAI_DB_PATH）",
    )
    args = parser.parse_args()
    db_path = Path(args.db)
    base_url = args.base_url.rstrip("/")

    checks: list[Check] = [check_db_file(db_path)]
    if checks[0].ok is True:
        conn = sqlite3.connect(str(db_path))
        try:
            for fn in (
                check_tables, check_active_user, check_classification_axis,
                check_worker_generation,
            ):
                try:
                    checks.append(fn(conn))
                except sqlite3.Error as exc:
                    # 单项异常按该项 FAIL 记录并继续——汇总必须完整，不半途而废。
                    checks.append(Check(fn.__doc__ or fn.__name__, False, f"检查执行异常：{exc}"))
        finally:
            conn.close()
    else:
        for name in ("核心表齐全", "≥1 活跃账户", "数据分级轴（ADR-0021）", "worker 心跳代际"):
            checks.append(Check(name, False, "跳过：DB 文件缺失"))

    checks.append(check_health(base_url))
    checks.append(check_live_classification_generation(base_url))
    checks.append(check_db_identity(base_url, db_path))
    checks.append(check_auth_generation(base_url))
    checks.append(check_frontend_dist())
    checks.append(check_writable_dirs())

    print(f"FLAi-OS 部署自检（base_url={base_url} db={db_path}）")
    print("-" * 60)
    all_ok = True
    for i, c in enumerate(checks, 1):
        mark = "PASS" if c.ok is True else "FAIL"
        if c.ok is not True:
            all_ok = False
        print(f"[{mark}] {i}. {c.name} — {c.detail}")
    print("-" * 60)
    if all_ok is True:
        print("自检通过：部署形态正确（业务正确性见开发机 verify_all）。")
        return 0
    print("自检未通过：部署不算完成，按上方 FAIL 项修复后重跑。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
