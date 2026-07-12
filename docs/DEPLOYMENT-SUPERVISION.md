# 生产进程守护指南（M12：D-Day 部署运维）

> **诚实边界（先读）**：本文的 systemd / NSSM 单元是**参考模板，非本机实测的可运行
> 交付物**——FLAi-OS 内网目标是 **Windows**，systemd 属 Linux；两者都无法在开发机
> （macOS）执行验证。**上线前必须在目标机逐项实测**：ExecStart 路径解析 / 运行账户
> 权限 / 环境变量加载 / 开机自启 / 崩溃自动重启 / 关机顺序。本文的**事实性声明**
> （启动命令、锁文件、恢复行为、环境变量、启动顺序）已逐条对照仓内真实代码，
> 可信；**模板脚本本身**只是起点，勿当作已验证。

本文回答 deploy_selfcheck（部署门）与 backup_restore（备份）之外的一个 D-Day 空白：
**API 与 Job Runner 两个常驻进程，在生产上如何被拉起、保活、崩溃重启、有序关闭。**

## 一、被守护的两个进程（事实，对照代码）

| 进程 | 启动命令 | 端口/锁 | 副本数 |
|---|---|---|---|
| **API** | `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port ${FLAI_BACKEND_PORT:-8620}` | 监听 8620（默认，尊重 `FLAI_BACKEND_PORT`） | 单实例（SQLite WAL 单节点部署） |
| **Worker** | `python -m backend.app.jobs.runner` | 文件锁 `<FLAI_DB_PATH 父目录>/worker.lock` | **恰一个**（锁强制） |

> 事实来源：`scripts/dev_start_backend.sh` / `scripts/dev_start_worker.sh`（启动命令）、
> `backend/app/jobs/runner.py:_run_default_worker`（锁位于 DB 同目录 worker.lock）。

**⚠️ ExecStart 不要用 dev 脚本里的 `uv run --with <deps>`**：那会**联网**拉 wheel，
内网离线必失败。生产 ExecStart 必须指向**预置依赖的 Python 环境**（venv，依赖从
wheelhouse 离线装好——见 `docs/M11-OFFLINE-PACKAGE-PLAN.md`）。下文模板用
`/opt/flai-os/venv/bin/python`（Linux）/ `C:\flai-os\venv\Scripts\python.exe`（Windows）
占位，替换成目标机真实路径。

## 二、单实例 worker + 崩溃恢复（事实，已实现，勿在守护层重复造）

平台**已内建**两条守护相关的安全属性，守护器只需「拉起一个 worker」，其余交给代码：

1. **单实例锁**（`worker_singleton_lock`）：非阻塞 `fcntl.flock`（Linux）/ `msvcrt.locking`
   （Windows），第二个 worker 抢锁失败即 `WorkerAlreadyRunningError` **fail-fast 退出**。
   故守护器**绝不可配 worker 多副本**；锁文件释放后**不删除**（重启复用同一 inode/路径）。
2. **中断任务恢复**（`recover_interrupted_tasks`，worker 启动时跑）：上次进程遗留的
   执行态任务（`validating`/`running`/`parsing`/`analyzing`）一律置 `failed` + `worker_interrupted`
   事件，**绝不重放外部副作用**（幂等：并发已转出的任务被仓储锁内白名单拒绝，只有
   本次真置 failed 才留痕）。故 worker **崩溃后由守护器直接重启即可**，无需人工清理
   卡住的任务——但产出**不会自动续跑**（中断=失败，需人重新发起，这是有意的诚实设计）。

> 事实来源：`backend/app/jobs/runner.py`（WorkerAlreadyRunningError:51 / recover_interrupted_tasks:122 /
> fail_task_from_execution 白名单，waiting_review 免疫）。

## 三、启动顺序（事实）

```
1. scripts/init_db          # 建表/迁移，幂等（API 与 worker 启动时也各自 init_db，但显式先跑更清晰）
2. scripts/user_admin.py create <用户名> <显示名>   # 无账户=全员锁门外（ADR-0019 fail-closed）
3. 起 API + 起 worker        # 两者都自 init_db；worker 先加锁再装配
4. scripts/deploy_selfcheck.py   # 12 项全 PASS 才算部署完成（含 worker 心跳新鲜+代际见证）
```

- API 与 worker **无硬启动依赖**（各自 `init_db` 幂等），可并行拉起；但 `deploy_selfcheck`
  的 worker 心跳检查要求 worker 已在跑，故**自检必须在两进程都起来之后**。
- **DB 必须在本地盘**（SQLite WAL 不支持网络盘）——DB_PATH 指向网络共享会静默损坏。

## 四、必需环境变量（事实，对照 config.py / .env.example）

| 变量 | 作用 | 缺省行为 |
|---|---|---|
| `FLAI_DB_PATH` | SQLite 库路径（决定 logs/、worker.lock、uploads 的父目录） | `data/flai_os.db` |
| `FLAI_BACKEND_PORT` | API 端口 | `8620` |
| `FLAI_MAX_UPLOAD_MB` | 上传大小上限（MB） | `100`（files.py:174） |
| `FLAI_LLM_BASE_URL` / `FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING` | 模型网关（对话/导引/fta 主入口） | **未配→首条消息 503**（deploy_selfcheck 第 7 项会拦） |
| `FLAI_LLM_MODEL_FAST` | 快模型档 | 可选 |
| `FLAI_MONITOR_CORE_DIR` | 监控生成工具的承重核目录 | **未配=fail-closed**（monitor 工具不可达，有意） |

> **key 纪律**：`FLAI_LLM_API_KEY` 等 secret 由守护器的环境注入（systemd `EnvironmentFile=`
> 权限 600 / Windows 服务账户环境），**绝不写进本仓、日志、单元文件明文**。

## 五、参考模板（未实测，上线前在目标机验证）

### 5.1 systemd（Linux 参考）

`/etc/systemd/system/flai-os-api.service`：
```ini
[Unit]
Description=FLAi-OS API (uvicorn)
After=network.target

[Service]
Type=simple
User=flai
WorkingDirectory=/opt/flai-os
EnvironmentFile=/etc/flai-os/flai.env      # 权限 600，含 FLAI_* 与 secret
ExecStart=/opt/flai-os/venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8620
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/flai-os-worker.service`：
```ini
[Unit]
Description=FLAi-OS Job Runner (single instance)
After=network.target

[Service]
Type=simple
User=flai
WorkingDirectory=/opt/flai-os
EnvironmentFile=/etc/flai-os/flai.env
ExecStart=/opt/flai-os/venv/bin/python -m backend.app.jobs.runner
Restart=on-failure
RestartSec=3
# 不配任何多副本；worker.lock 已强制单实例，多副本只会 fail-fast 刷日志

[Install]
WantedBy=multi-user.target
```

> `Restart=on-failure` 与代码的崩溃恢复是**互补**：systemd 拉起新 worker → 新 worker
> 启动时 `recover_interrupted_tasks` 把上次中断的任务置 failed。**不要**用 `Restart=always`
> 掩盖反复崩溃——崩溃循环应触发告警而非静默重启（诚实优先于可用性表演）。

### 5.2 Windows NSSM（**主目标**，参考命令）

内网目标是 Windows。用 NSSM 把两个进程注册成 Windows 服务（示意，路径/账户按目标机改）：
```bat
nssm install FLAiOS-API   "C:\flai-os\venv\Scripts\python.exe" "-m uvicorn backend.app.main:app --host 0.0.0.0 --port 8620"
nssm set     FLAiOS-API   AppDirectory C:\flai-os
nssm set     FLAiOS-API   AppExit Default Restart
nssm set     FLAiOS-API   AppStdout C:\flai-os\data\logs\nssm-api.out.log

nssm install FLAiOS-Worker "C:\flai-os\venv\Scripts\python.exe" "-m backend.app.jobs.runner"
nssm set     FLAiOS-Worker AppDirectory C:\flai-os
nssm set     FLAiOS-Worker AppExit Default Restart
```
- FLAI_* 环境变量：`nssm set <svc> AppEnvironmentExtra FLAI_DB_PATH=...`（secret 走服务账户环境，勿明文入库）。
- **Windows 单实例锁走 `msvcrt.locking`**（已实现），但 R4 批次注明 msvcrt 分支未在真 Windows
  实测（M4 侦察 2-5/2-6 待验）——上线前必测「起第二个 Worker 服务应 fail-fast」。

## 六、验证（上线后必跑）

```
scripts/deploy_selfcheck.py --base-url http://127.0.0.1:8620 --db <FLAI_DB_PATH>
```
必须 12/12 PASS——其中「worker 心跳代际新鲜」直接证明 worker 服务已被守护器拉起且在跑。
崩溃重启演练：`kill`/停服务 worker → 守护器应自动拉起 → 自检 worker 心跳恢复 PASS
（负例咬合已进 `backend/tests/test_deploy_selfcheck_negatives.py`：无心跳/过期心跳必 FAIL）。

## 七、未决（交 owner / M4 侦察）

- 本文模板**未在目标机实测**（诚实边界，见开头）——M4 内网首日按 `docs/M4_intranet_day1_recon_checklist.md`
  验证 msvcrt 锁 + NSSM 自启 + env 加载。
- 崩溃告警接入（systemd `OnFailure=` / Windows 事件日志 → 告警渠道）随内网监控体系落地。
- 反代/TLS/端口暴露面属部署层，ADR-0019 威胁模型已声明不在应用内解决。
