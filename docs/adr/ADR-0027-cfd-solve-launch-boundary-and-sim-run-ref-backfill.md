# ADR-0027：cfd_solve_launch 安全边界 + sim_run_ref Runtime 回填接线

> 后续状态（2026-07-21）：P1-A 的 owner 选项①已由 ADR-0031 落地。direct task、
> interactive conversation、eval admission、safe_auto 与 task review 共享
> `visibility ∩ allowed_roles` 默认拒绝门；最终 capability/RBAC 矩阵仍见 ADR-0029 S1。

- **状态**：Accepted（2026-07-13）
- **关联**：ADR-0022（allow_shell_command 子进程边界先例）· ADR-0026（CFD 解析器
  vendoring）· spec/plan = `docs/superpowers/{specs,plans}/2026-07-13-cfd-flai-os-integration*.md`
- **审查**：Codex 异源审（86gs gpt-5.6-sol ultra）R0 CHANGES_REQUIRED（4P1+2P2，
  全 grounded 复核为真后落地于 0641ebd）→ R1 复审（结果见 commit 尾注/witness）。

## 一、cfd_solve_launch（第二个 allow_shell_command 工具）

平台第二个 `allow_shell_command=true` 工具（首个=ADR-0022 monitor_adapter_recon）。
差异：本工具**发起长驻真实进程**（容器内 pimpleFoam ~200s）而非跑一次性只读核，
新增两类风险与对应守卫：

- **谎报已发起**（fire-and-register 的固有风险）：`… && nohup x &` 整体后台化恒
  返 0（bashrc 缺失/可执行缺失也「成功」）。守卫=fire 后按**进程 cwd 精确对账**
  本 run 子目录（裸 pgrep 会误认并行/legacy run 的求解进程）+ sidecar 最后盖
  （失败残留无 sidecar，hub `run_discovery.marker_file` 不认作 run）。
- **管道吞退出码**：`checkMesh | tee` 无 pipefail 时恒 0。守卫=固定脚本前缀
  `set -o pipefail` + stdout 正向断言 `Mesh OK.`（agent-cfd-live checkMesh.log
  实测 marker）。

其余边界与 ADR-0022 同款：shell=False 参数列表、固定脚本模板零用户串拼、容器名/
路径来自可信 env 非请求体、case 枚举白名单、run_id `fullmatch(r"[0-9]{8}-[0-9]{6}")`
先于任何路径拼接（`re.match`+`$` 放行尾换行、`\d` 收非 ASCII 数字——Codex R0-P2-2，
三处统一：launch / result_read / runtime 回填）、config 缺失 fail-closed、
**零删除操作**（每 run 新建时间戳子目录，同名即拒；bind-mount 铁律强化版）。
timeout 预算闭合（worst ≈298s < tool.yaml 360s），杜绝 Registry 已记 failed 而
adapter 线程稍后盖 marker 的幽灵 run。tamper witness：
`docs/reviews/cfd-solve-launch-tamper-witness.md`（R0 四注伤 + R1 重放五注伤全咬）。

### mesh 来源两条腿（Codex R0-P1-1）

真实 `case/template/` **不含 cyl2d.msh**（实测：只有 0/ constant/ system/ geo/），
canonical 流程是 host gmsh 从 geo 生成（rehearse.sh staging-v2 host 直出）。
Tool 依次：template 自备 `cyl2d.msh` → 直接随 copytree 用；否则 host `gmsh
<run_dir>/geo/domain_parametric.geo -3 -format msh2 -o <run_dir>/cyl2d.msh`
（逐字 canonical 参数）；两腿全断 fail-closed。R0 单测夹具曾发明生产不存在的
`template/cyl2d.msh` 布局——修后测试以真实布局为主夹具、自备 msh 为副。

## 二、sim_run_ref 回填接线（spec §4.3 挂账项裁决）

**裁决：Runtime 成功路径回填**（三选一中的第二条）。workflow 执行 context 刻意
不暴露 repos/conn（M1 隔离设计，不为此破例），故 workflow 只在
`outputs[0].sim_run_ref`（`"module@run_id"`）声明引用，Runtime 在
`set_task_outputs` 之后、review gate 之前调 `repos.set_task_sim_run_ref` 回填
（与 `POST /tasks/{id}/sim-run-ref` 人工关联**同一 setter**：metadata 标注非
状态迁移，不 bump updated_at、不 append 冻结枚举事件——不破「人是唯一签发者」）。

- **格式门**：module `^[a-z][a-z0-9_]*$`、run_id `^[0-9]{8}-[0-9]{6}$`（与工具/
  hub 同一白名单语义）；畸形不回填、记 warning `agent_log` 事件。
- **标注非承重**：回填失败只 log 不摧毁已成功任务——错误方向必须是「少标注」。
- 无 `sim_run_ref` 声明的 agent 零行为变化（绝大多数 agent 走空路径）。

### run_id 生成（修 plan 原稿缺陷）

plan 原稿 `context.get("run_id_seed") or context.get("task_id")` 不可用：context
无此键，且 task_id 是 uuid 过不了 run_id 白名单。裁决：`inputs.run_id` 可选注入
（schema pattern 校验，测试/eval 确定性重放用），缺省 workflow 生成 UTC 时间戳
`YYYYMMDD-HHMMSS`（hub `newest_by_name` 排序键 + Tool 白名单双满足）。

## 三、Codex R1 处置（5P1+3P2，2026-07-13）

| # | Finding | 处置 |
|---|---------|------|
| P1 | pgrep 匹配不到 OF11 真进程（pimpleFoam 是 sh wrapper，comm=foamRun） | 真跑取证后修 `pgrep -x 'foamRun\|pimpleFoam'`（孤儿 run 实证假阴性） |
| P1 | rehearse.sh `rm -rf case/run/*` 会清 managed runs（共享目录） | **运维红线**（代码不可修：bind-mount 固定 + 他仓零改动铁律）——managed 求解在场勿跑 rehearse.sh；被清后评估 fail-closed 诚实报缺不静默错读；红线记 agent README |
| P1 | detached 求解生命周期 > Tool 调用，max_parallel_jobs 无法防并发 | 发起前容器内活跃求解扫描（pgrep+cwd 在 run 根下即拒）。注：扫描→发起有 TOCTOU 窗口，单 worker 串行下实际风险极低，显式接受 |
| P1 | end_time 无上界（1e12 无限烧 CPU，无取消路径） | 三层同守：tool.yaml maximum 600 + agent schema maximum 600 + adapter 0<t≤600 fail-closed（600=canonical 150 的 4×） |
| P1 | eval output_field 检查缺 file/无 JSON 产物，治理跑必报配置错 | workflow 落 `solve_receipt.json` 持久回执，checks 带 file |
| P2 | eval 固定 run_id 重跑即拒（零删除），治理跑一次性毒化 | case_001 去 run_id 注入，每次生成新时间戳 |
| P2 | run_id pattern 只查宽度，hour-30/远未来 ID 钉死 hub newest_by_name | adapter 语义校验（strptime 真日期 + 不超前 now+24h）；过去 ID 不设限（重放合法） |
| P2 | 短 end_time 在探测窗口内正常跑完被误报失败 | log 末行 `End` 收尾即判已完成，照常盖 sidecar |

## 四、Codex R2 处置（3P1+2P2，2026-07-13，round cap 终轮）

| # | Finding | 处置 |
|---|---------|------|
| P1-A | `permissions: admin_only` 纯声明——任务创建路径无角色检查，任何登录账户可发起真求解（CPU/盘副作用） | **平台横断债交 owner 裁决**（round cap 已尽）：users 表无 role 字段，admin_only 角色轴本就 owner-gated 在册（M11 后续）。现状风险有界=内网单实例+账户仅管理员手工建（ADR-0019 无自助注册）+end_time 有界。owner 选项：①接受现状角色轴统一收口 ②requires_human_review 改 true（发起也人签）③status disabled 至角色轴落地。**owner 裁决（2026-07-13）：选项①**——内网单实例+账户仅管理员手工建+end_time 有界+单并发锁，风险有界；admin_only 角色轴落地时全平台统一收口 |
| P1-B | 评估只看周期数——solver 在跑/已崩也可能发 Williamson-consistent verdict | verbatim 修：收敛=三门 AND（oracle 周期+残差门 resid_p 尾部全<0.05+ended 收尾门）；tol 依 golden 尾部实测 1.17e-2 的 4× 余量（瞬态 Initial residual 语义，非稳态 1e-6） |
| P1-C | 快完成分支返回 note 超 output_schema（additionalProperties:false）→ 已盖 sidecar 的 run 被 Registry 误判 failed | verbatim 修：tool.yaml 声明 note |
| P2-D | 流式半写行逐列 append 撕裂 t/cd/cl 长度 → 有效 run 被 oracle 误拒 | verbatim 修：整行先转换再 append（两仓同源同修+diff 实证） |
| P2-E | 发散 run 的 nan/inf 透传进 evaluation.json/FastAPI 严格 JSON | verbatim 修：`math.isfinite` 整行拒（两仓同修） |

## 四b、Codex R2 全分支审处置（86gs sol ultra `--base main`，5P1+2P2，2026-07-13——与上表 CRS 轴独立，两审互补）

全部 grounded 复核为真后 verbatim 落地（宪法 verbatim 例外：逐字落地上轮
Suggested fix 不计新轮）；每条配 witness 测试且 tamper 咬合实证。

| # | Finding | 处置 |
|---|---------|------|
| P1-α | eval 证据指纹不含夹具字节（case 只传 run_id，`FLAI_CFD_CASE_DIR` 进程全局）——换数据/改夹具后旧绿证据仍有效 | verbatim 修：两 case 补 `input_files` 列夹具三件（digest 吃到字节+staging 校验在场）。**残余诚实标注**：workflow 经 env 路径读 run 树而非 staged 副本，「被指纹的字节=被评估的字节」仍依赖 env 指向 vendored fixtures（case description 已写死该前置） |
| P1-β | busy 探测 rc≠0 一律当 idle——docker exec 125 等探测失败时照常开跑，破单并发契约 | verbatim 修：rc=1（grep 确认无匹配）才 idle；rc=0 拒；其他 rc+超时 fail-closed |
| P1-γ | alive 探测慢启动竞态（子壳后台化后 foamRun 未必已在）+ TimeoutExpired 直接穿透 | verbatim 修：launch `& echo $!` PID 握手——按子壳 PID+cwd 对账，与进程名/启动时序解耦；探测超时按未确认 fail-closed。**残余诚实标注**：fail 返回后 detached 求解仍可能起来=孤儿 run（无 sidecar 不被认作 run，错误信息已注明人工处置路径；零删除铁律不代杀） |
| P1-δ | result_read `ended` 子串判定——重启/损坏 log 中段 End 冒充正常收尾 | verbatim 修：末非空行全等 "End"（与 solve_launch 同判据） |
| P1-ε | 残差门过滤 None——「尾部全部达标」被偷换成「可得样本达标」 | verbatim 修：原样本全数值+有限+≥10 样本，任一 None/NaN/缺样即不过（未知按不健康算） |
| P2-ζ | 半写残差 token（`1e-`）regex 能中 float() 炸——live 读把整次任务炸 failed | verbatim 修：`_float_or_none` 跳过不完整行（两仓同源同修，hub commit 见 sim-live-hub） |
| P2-η | 叙事无数字校验——prompt 约束不了模型，改数/编数直进人签草案 | verbatim 修：`_rogue_numbers` 舍入归属校验（显示精度四舍五入全等；字符串事实如 run_id 内数字串放行；Re=100/1996 白名单），含 rogue 即整段弃用换占位 |

## 影响面

- `tools_impl/cfd_solve_launch/`（新，安全边界）、`agents/cfd_solve_agent/`（新）、
  `backend/app/runtime/runtime.py`（`_backfill_sim_run_ref` 最小 patch）、
  `tools_impl/cfd_result_read/adapter.py`（正则统一）。
- agent-cfd-live 零改动；sim-live-hub 零改动。
