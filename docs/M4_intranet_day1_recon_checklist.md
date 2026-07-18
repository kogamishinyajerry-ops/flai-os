# M4 内网首日侦察 Checklist

> 目的：内网踏点是一次性、时间受限的窗口。本清单把散落全仓的「待内网侦察」标记
> 汇总为可逐项打勾的现场核对表，**每条均为未验证假设**（声明 ≤ 证据等级）——
> 「验证结果」栏由踏点当天现场填写，未填即未验证。
>
> 来源盘点方式：`grep -rn "待内网侦察" backend/ docs/ agents/ contracts/`
> （2026-07-18 复核；若代码更新以 grep 现扫为准）。

## 使用方式

1. 踏点当天带上本文件（打印或离线副本）。
2. 每项按「验证方法」操作，把**原始观测**（命令输出/截图/报文摘要）记入「验证结果」。
3. 回来后把结果同步回对应源文件（profiles.yaml notes / docs/04 §6 / ADR），再动代码。

---

## ① LLM 端点协议与鉴权（最高优先——阻塞 fta/guide/knowledge_qa 三个 Agent 真实点火）

> 公网参照证据（2026-07-11）：本机经公网 GLM（glm-5.1）已验证 1-1/1-3/1-4 的
> **协议链路侧**（探针全绿 + 导引/fta 真实业务闭环），存档
> `docs/reviews/GLM-real-fire-record.md`。内网形态可能不同，现场列保持空白照填。

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 1-1 | 内网 GLM 端点是 OpenAI 兼容协议（`POST {base}/chat/completions`） | `backend/app/model_gateway/gateway.py:10,289`、`docs/04:63` | `export FLAI_LLM_*` 后跑 `python scripts/probe_llm_gateway.py`，逐层看原始观测 | |
| 1-2 | 鉴权方式是 `Authorization: Bearer <key>` | `profiles.yaml:13` | 同上（探针即用 Bearer 头；401/403 只是观测——可能是鉴权形态不符，也可能是 Key 错误/过期、模型 ACL、IP 白名单，需用已知有效凭据或与服务方确认后才能下结论） | |
| 1-3 | 响应 body 是 JSON 且有 `choices[0].message.content`（网关必需）；`usage` 字段（网关允许缺失，缺则 token 消耗记 None） | `gateway.py`（chat 形状校验） | 探针输出逐层观测 | |
| 1-4 | 中文往返正常（无编码/截断问题） | 隐含假设 | 探针后手工发一条中文 prompt 核对 | |
| 1-5 | 真实 reasoning 请求的延迟分布与安全 timeout 尚未知 | `backend/app/config.py`、`.env.example`、`docs/PRODUCTION-READINESS-PROGRAM.md` P0-B3 | 用目标模型重复发送代表性复杂 prompt，记录样本量、p50/p99/失败率；将 `FLAI_LLM_TIMEOUT_S` 配置为高于经确认的 p99 后复测 | |
| 1-6 | 模型名（`FLAI_LLM_MODEL_REASONING/FAST`）在内网服务上真实存在 | `profiles.yaml:21` | 探针 + 服务方确认模型清单 | |
| 1-7 | vision/embed profile 的报文形态（V0.1 只占位） | `gateway.py:289`、`docs/06:73-80` | 询问服务方是否提供，暂不接入，观测记回 docs/06 §6 | |

## ② 数据库与部署环境

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 2-1 | 部署机 `FLAI_DB_PATH` 指向**本地磁盘**（WAL 禁网络盘） | `README 环境变量表`、`.env.example` | 确认路径非 UNC/映射盘；`sqlite3 <db> "PRAGMA journal_mode"` 应回 `wal` | |
| 2-2 | Windows 下 `.ps1` 启动脚本可用（DECLARED-NOT-VERIFIED） | `scripts/*.ps1` 头注 | 逐个跑 init_db/dev_start_backend/dev_start_worker 的 .ps1 | |
| 2-3 | 内网机器可安装 Python 3.10+ 与依赖（离线 wheels 策略未定） | `scripts/package_release.*`（NOT-IMPLEMENTED） | 确认现场 Python 版本/架构 + 是否有内网 pip 源 | |
| 2-4 | 部署机有 Node 或可接受「带 dist 产物入场」（后端静态托管 dist，现场可免 node） | `README 前端节` | 确认 dist 随包带入即可，无需现场构建 | |
| 2-5 | worker 单实例锁的 Windows 分支（msvcrt.locking）真实生效（DECLARED-NOT-VERIFIED，本机仅测 POSIX fcntl） | `backend/app/jobs/runner.py`（R4 批） | Windows 上起第一个 worker 后再起第二个，应 stderr 报「已有 worker 正在运行」且退出码 1 | |
| 2-6 | 完整性闸 O_NOFOLLOW 在 Windows/NTFS 上的行为（符号链接/junction 拒绝路径是否等效） | `backend/app/storage/file_integrity.py`（R4 批，README #20③） | Windows 上跑 `python -m pytest backend/tests/test_file_integrity.py -q`，尤其 symlink 用例不应被 skip 掩盖 | |

## ③ Knowledge 检索来源扩展

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 3-1 | 语料实际形态（目录结构/格式/密级分布） | `knowledge/scopes.py:127,141`、`docs/06:12` | 现场盘点部门语料样本 | |
| 3-2 | PDF 是否为主要格式（V0.1 显式拒绝 PDF） | `knowledge/chunking.py:194` | 语料格式统计 | |
| 3-3 | obsidian_vault / mcp 来源是否存在需求 | `contracts/knowledge_scope.schema.json:24` | 与使用方访谈 | |
| 3-4 | 向量检索/embedding 服务是否可用 | `docs/06:73-80` | 服务方确认；观测记回 docs/06 §6 | |

## ④ 具体模型接入与业务流程

| # | 待验证假设 | 来源 | 验证方法 | 验证结果（现场填） |
|---|---|---|---|---|
| 4-1 | GLM 5.x 部署形态（GPU 机器/限流/并发配额） | `docs/01:60,65` | 服务方确认 | |
| 4-2 | 性能盘真实调用形态（CLI？COM？输入输出文件约定？） | ADR-0010（M4 adapter 设计前置） | 现场观摩一次真实性能盘操作 | |
| 4-3 | L2 成熟度「专家审核签字」的记录方式 | `docs/02:64` | 与业务 reviewer 确认流程 | |
| 4-4 | MCP Server 部署方式（工具 MCP 化演进前置） | `docs/03:91` | IT 环境确认 | |

---

## 踏点当天最短路径（30 分钟版）

1. `python scripts/probe_llm_gateway.py`（①-1/2/3 一次性出观测）。
2. `sqlite3 <FLAI_DB_PATH> "PRAGMA journal_mode"` + 确认路径本地盘（②-1）。
3. `.ps1` 三连（②-2）。
4. 语料目录 `dir /s` 样本 + 格式统计（③-1/2）。
5. 观摩性能盘操作一次，录屏或记步骤（④-2）。
