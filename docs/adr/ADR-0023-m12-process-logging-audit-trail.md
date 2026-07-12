# ADR-0023：M12-2 进程日志基建 + 认证/访问审计留痕

- 状态：Accepted（PM 战略审 M12 rank3；本轮实现）
- 日期：2026-07-12
- 关联：ADR-0019（真鉴权）· ADR-0021（数据分级轴）· 战略审综合输出 rank3
- 审查：待 Codex 异源审（触发条件：认证审计边界 = 安全边界「命中即审」）

## 一、问题（grounded 坐实）

首日事故不可诊断 + EAR 合规硬缺口，两者同根：**进程无持久日志**。

- 全仓零 `logging.basicConfig`/`dictConfig`/`RotatingFileHandler`（亲验：`grep -rn` 空）。
- `logging.getLogger(__name__)` 仅 5 模块（bootstrap / runtime / promotion /
  eval_runner / jobs.runner），**无人配 root**——这些 logger 的 INFO 全被丢弃，
  仅 WARNING+ 经 `logging.lastResort` 落 stderr；服务 detached 启动后 stderr
  无处可去，worker fail-closed 事件（心跳失败 / 启动置 failed / 恢复中断任务 /
  bootstrap 拒 Agent）**全部蒸发**。
- `logs/` 仅 `.gitkeep`（`.gitignore` 有 `logs/*`），无人往里写。
- **认证/访问零审计**：login 成功/失败、logout、敏感文件下载 403（ADR-0021
  下载门）均无留痕。EAR 语境下「谁尝试访问了 sensitive 数据」不可回溯 =
  合规硬缺口，且与「日志基建缺失」是同一个洞。

## 二、决策

### D1 纯 stdlib，零新依赖（离线约束）
`logging` + `logging.handlers.RotatingFileHandler` 全在标准库。不引入
structlog / loguru / 任何 handler 需下载的三方件——续 ADR-0021 Codex R2-P2
「离线包只认 stdlib + 预下载 wheel」纪律。新模块 `backend/app/logging_setup.py`
只 import `logging` / `logging.handlers` / `pathlib`（无业务依赖，杜绝循环导入）。

### D2 进程分文件，杜绝跨进程 rotation 竞争
API 与 Job Runner 是**两个独立进程**。同一 `RotatingFileHandler` 被两进程
持有 → rotate（rename）竞态、交错写。故按进程分文件：
`flai-os-api.log` / `flai-os-worker.log`。审计事件全部 API 侧产生（login /
logout / download），故 `audit.log` **只由 API 进程写**（worker
`enable_audit_file=False`），无跨进程争用。

### D3 log_dir 派生自 db_path.parent，测试天然隔离（关键设计）
`configure_logging` 的 log_dir 在 lifespan 内派生 `db_path.parent / "logs"`：
- 生产 db=`data/flai_os.db` → 日志落 `data/logs/`（运行态与库同根，一处备份）；
- 测试 db=`tmp_path/flai_os.db` → 日志落 `tmp_path/logs/`，**per-test 自动隔离、
  pytest 自动清理、零 conftest 改动**。
worker 侧同理派生 `config.DB_PATH.parent / "logs"`。

### D4 file-only，不挂 root console handler（测试防污染）
**不往 root 加 StreamHandler**。理由：①核心目的是「持久化」，生产 detached
进程 stderr 无处去；②uvicorn 自带 console handler（其 access/error 日志照常
上屏），worker 关键错误已有显式 `print(..., file=sys.stderr)`；③root 挂
console handler 会污染 `capsys`/`readouterr` 断言的测试（test_job_runner /
test_diagnose_gc_debt）。dev 期 tail 文件即可，console 便利不值这个风险。

### D5 configure「先清后加」+ lifespan teardown 复位（handler 泄漏双保险）
跨测试最大风险：test A 的 file handler（指向 tmpA，测试后被删）残留 root，
test B 期被写 → 「logging error」噪声上 stderr 污染 capsys。双保险消除：
- `configure_logging` 每次先移除并 close 既有 `_flai_managed` 标记的 handler，
  再加新的（幂等替换）；
- lifespan 在 `yield` 后调 `reset_logging()` 移除本次所加 handler。
  测试用 `with TestClient(app)` 正常进出 lifespan → handler 随退出即清，零泄漏。
  生产 app 常驻，teardown 仅在进程退出时跑，无副作用。

### D6 审计事件格式：结构化单行、白名单字段、绝不含 secret
`audit_event(action, *, actor, outcome, **fields)` 输出恒为
`action=<> outcome=<> actor=<> k=v ...` 单行可 grep。**只记调用方显式白名单
字段**（username / display_name / file_id / classification / reason）——绝不
记密码、token、cookie 值。login 记 `body.username`（尝试者），download 记
`request.state.user`（已认证者）。审计 logger 若在 configure 前被调（如脱离
lifespan 的单元测试），无 handler = 静默丢弃，绝不抛错拖累主流程（fail-safe）。

## 三、审计事件清单（本轮落点，最小充分集）

| 事件 | 落点 | actor | outcome | 附加字段 |
|---|---|---|---|---|
| 登录成功 | auth.py login 签发前 | body.username | success | — |
| 登录失败（凭据错） | auth.py login 401 前 | body.username | failure | reason=bad-credentials |
| 登录节流（per-user 锁） | auth.py login 429 前 | body.username | throttled | reason=rate-limited |
| 登出 | auth.py logout | request.state.user | success | — |
| 敏感下载拒绝 | files.py download 403 前 | request.state.user | denied | file_id, classification |

> 全局并发闸 429（非 per-user，无安全语义）不记；上传成功/失败本轮不纳入
> （文件已 sha256 落库可追溯，非本 rank 的合规缺口焦点），留后续按需扩。

## 四、验收标准

1. `logging_setup.py` 只 import stdlib（blocked-import 探针：屏蔽 jsonschema
   后仍可 import）。
2. `configure_logging` 后，5 个业务 logger 的 INFO 落 `flai-os-<tag>.log`。
3. login 成功后 `audit.log` 含 `action=login outcome=success actor=<user>`。
4. login 凭据错后 `audit.log` 含 `outcome=failure reason=bad-credentials`。
5. 敏感下载 403 后 `audit.log` 含 `action=sensitive_download_denied ... classification=sensitive`。
6. **tamper**：把 download 403 前的 `audit_event(...)` 删除 → 断言 audit.log
   命中的测试必 FAIL（否则审计留痕是死代码）。
7. 跨测试无 handler 泄漏：全量 pytest 绿，无新增 stderr「logging error」。
8. worker `_run_default_worker` 装配 file logging（`enable_audit_file=False`），
   `run_forever` 恢复/心跳错误落 `flai-os-worker.log`。
9. audit_event 绝不记 secret：白名单字段实现审读 + 无 password/token/cookie 入参。

## 五、威胁模型与声明的边界

- **审计 = 事后可回溯，非实时阻断**：本轮不做告警/联动，只保证留痕。
- **自报 actor 信任根**：login 的 actor 是尝试者自报的 username（合理，失败
  也要记谁在试）；download 的 actor 是中间件已认证的 request.state.user（可信）。
- **日志非防篡改**：文件可被有盘访问者改。V0.1 单实例内网，日志完整性
  由部署层文件权限保障，不做 WORM/签名链（过度工程，非本 rank 目标）。声明。
- **本轮不含日志外发/集中采集**（syslog / ELK）——离线内网无此设施，file 即终点。
