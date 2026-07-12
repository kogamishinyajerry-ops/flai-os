# M12-2 进程日志基建 + 认证/访问审计留痕 · 审查档案

> 来源：PM 战略审 M12 rank3（力乘器——让首日事故可诊断，且折叠 EAR 合规的
> 审计留痕硬缺口）。契约=ADR-0023。触发 Codex 异源审：认证审计=安全边界「命中即审」。

## 一、grounded 复核（战略审论断亲验坐实）

| 论断 | 亲验 |
|---|---|
| 全仓零 basicConfig/dictConfig/RotatingFileHandler | ✓ `grep -rn` 空 |
| getLogger 仅 5 模块（bootstrap/runtime/promotion/eval_runner/jobs.runner），无人配 root | ✓ INFO 全丢弃，仅 WARNING+ 经 lastResort 落 stderr，detached 即蒸发 |
| logs/ 仅 .gitkeep，.gitignore 有 logs/* | ✓ 无人写 |
| login/logout/敏感下载 403 零审计（EAR 合规硬缺口） | ✓ auth.py/files.py 原无任何 audit 调用 |
| 测试零 caplog、零 logging.* 依赖 | ✓ root 重配不破坏任何日志断言 |
| `_run_default_worker` 仅 `__main__` 调用（测试走 run_worker_forever + tmp lock） | ✓ worker 装配日志零测试影响 |

## 二、实现（S 成本，纯 stdlib 零新依赖）

1. **`backend/app/logging_setup.py`（新）**：`configure_logging(log_dir, *, process_tag,
   enable_audit_file)` + `reset_logging()` + `audit_event(action, *, actor, outcome, **fields)`。
   只 import logging/logging.handlers/pathlib——无业务依赖，杜绝循环导入，续离线
   stdlib 约束。RotatingFileHandler 进程分文件（api/worker）+ 独立 audit.log。
2. **装配**：main.py lifespan（log_dir 派生 db_path.parent/logs，退出 reset_logging）
   + jobs/runner.py `_run_default_worker`（process_tag=worker，enable_audit_file=False）。
3. **审计钩子**：auth.py login 成功/失败/节流 + logout（4 处）、files.py 敏感下载 403（1 处）。

### 关键设计决策（ADR-0023 D3/D4/D5）
- **D3 log_dir 派生 db_path.parent**：测试 db 在 tmp → 日志天然 per-test 隔离，
  零 conftest 改动。
- **D4 file-only 不挂 root console**：避免污染 capsys/readouterr 测试
  （test_job_runner/test_diagnose_gc_debt），uvicorn 自带 console。
- **D5 先清后加 + lifespan teardown 复位**：双保险消除跨测试 handler 泄漏
  （旧 file handler 指向已删 tmp 目录、被后续测试写 → stderr 噪声污染 capsys）。

## 三、自证

- **单测**（test_logging_audit.py 5 个）：纯 stdlib 单元（configure→审计/业务日志落文件）、
  登录成功审计、登录失败审计（reason=bad-credentials + 无密码明文）、敏感下载 403
  审计（file_id + classification=sensitive）、internal 下载不产 denied 假阳性。
- **tamper**（验收 6）：删 files.py download-403 的 `audit_event(...)` →
  `test_sensitive_download_denied_is_audited` **FAILED**（1 failed）；复原后 5 passed。
  证明审计留痕非死代码。
- **capsys 无污染实证**（D4）：test_job_runner + test_diagnose_gc_debt **19 passed**
  （file-only 不加 console handler，readouterr 断言不受影响）。
- **全量回归**：614 passed（609 基线 + 5 新），零回归。

## 四、Codex 异源治理审（86gs gpt-5.6-sol ultra）

**R0：CHANGES_REQUIRED**（与 monitor 单元合并审，详见
`M12-monitor-adapter-activation-review-record.md` §四）。本单元相关 finding 全修+witness：
- **P1-3 审计日志注入**（user-controlled username 含 CR/LF 伪造审计行）→ 改 JSON Lines
  + 字段白名单 DROP 非白名单（含误传 secret）+ ts 自含。注入 witness + tamper 咬合。
- **P2-2 reset_logging 不在 finally** → lifespan try/finally 覆盖 configure+启动+yield。
- **P2-3 data/logs/ 未 gitignore** → `.gitignore` 加 `data/logs/*`。
- **P2-4 审计用非唯一 display_name** → actor 改唯一 username，display_name 作附加字段。
- **P3-1 reset 不恢复 logger 原态** → 快照+恢复 root/audit level & propagate。
- **P3-3 测试子串搜索不严** → 审计测试改**解析 JSON 单条记录**（非子串搜索）。

## 五、递延（M12 战略审候选批其余项）

rank2 control_logic 首个真实 L1 晋升（挂服务重启窗口）· rank4=task#16 部署门自证
负例 + 单实例锁探针 · rank6=task#17 reviewer≠creator 子赢 · rank5 进程守护交付物。
本轮插入用户显式优先级：monitor_adapter「可视化监控生成」模块正式接入平台（task#14）。
