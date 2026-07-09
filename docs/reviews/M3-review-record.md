# M3 收口审查记录（可追溯存档）

> 同 M1/M2 存档纪律。M3 主体 = commit cf91c31（Mock 性能盘 Agent：三 Tool
> Package + performance_disk_agent + E2E + ADR-0010）。

## 真环境冒烟（主控，收口前）

测试环境 230 绿但真环境首跑 **failed**：四启动脚本 uv `--with` 清单漏
openpyxl（测试命令有→假安全）。诚实失败链在真环境如实工作（工具折叠
ModuleNotFoundError→tool_failed 事件→任务 failed 带真实原因）后修复脚本，
复跑全链绿（completed+三产物+3 case_failed 折叠事件）。
教训：**pyproject 加依赖必同步启动脚本×4 + README 跑测命令**。

## 反方审查（异构 subagent 十问+四组实测，2026-07-09，CHANGES_REQUIRED）

审查方法亮点：亲手 tamper 实证 EXPECTED 计数非循环论证（注入异常→
`success==45` 断言真咬）；公式注入用探针实测证实；203 条事件/96.5KB 实测。

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | **P1** | **公式注入（CWE-1236，实测证实）**：excel_summary_writer 把未受信 case_id/error_message 直写 xlsx，openpyxl 自动把 `=` 前缀字符串升级为活公式——上传者可在对外分发的 result_summary.xlsx 植入 HYPERLINK 钓鱼/DDE | 修：全部字符串单元格强制 data_type='s' 惰性化+注入探针回归测试+tamper 自证（共享工具，一处修保护 M4/M5 全部复用方） |
| 2 | P2 | result_summary.xlsx 缺 mock 水印——docs/03「四落点」政策本身没覆盖最易脱离上下文传播的产物 | 修：writer 加 notice 声明 sheet+mock 列，docs/03 扩为五落点 |
| 3 | P2 | events 接口无分页（与 tasks 口径不一致）+表格行数无上限，规模线性放大 | 修：parser 行数上限（默认 1000 超限诚实拒绝）+events limit/offset |
| 4 | P2 | TaskDetail 不展示 ok/failed 计数，「全失败仍绿色已完成」误导 | 修：状态旁显示成功/失败计数 tag（取自 summary_generated 事件） |
| 5 | P2 | README 跑测命令缺 --with openpyxl（复制即炸,与启动脚本同类漂移漏网） | 修 |
| 6 | P2 | README 已知限制清单未同步（M3 未还的债仍写「M3 项」；M3 新债未入清单） | 修：改口 M4 项+新债三条入清单 |
| 7 | P2 | samples.jsonl 在汇总写出失败时留 task_runs_dir 未注册未清理 | 并入孤儿产物 GC 债（M4） |
| 8 | P3 | 再生脚本语义一致但非 byte 一致（zip 元数据 206 字节噪声） | docstring 注明防线=语义对账非 checksum |
| 9 | P3 | 三 tool.yaml require_workspace_isolation=false 与 docs/03 默认值声明不符（M0 老模式非新债） | 记录，不动 |

过关项（有实证）：EXPECTED 计数 oracle 真咬/单 case 隔离真实有效/mock 四落点
全穿透/EAR 红线零命中/白名单未被绕过/合并单元格失败安全/超时机制真实生效。

## 86gs 治理审（异源 Codex，`codex review --commit cf91c31`）

**P1 零**。P2×2：

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P2 | Excel 布尔单元格被 `float()` 吞成 1.0/0.0——坏行静默变合法 case，批量带脏数据跑完 | 修：isinstance(raw,bool)→行级错误+测试 |
| 2 | P2 | workflow 盲取 files[0] 当 case 表——多附件时取错文件或误炸 | 修：按 .xlsx 后缀过滤，恰一用之/零或多则诚实拒绝+E2E 两例 |

## 收口结论

（修复 commit 与最终计数见后续追记）
