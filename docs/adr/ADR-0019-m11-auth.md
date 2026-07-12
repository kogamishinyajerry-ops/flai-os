# ADR-0019: 真鉴权最小落点（本地账户 + 服务端会话）

- 状态：已采纳 R1（loop-auditor 设计审 BLOCK→F1-F8 修订闭合；实现后 Codex 异源审同步阻塞）
- 日期：2026-07-12
- 关联：ADR-0018（治理闭环——记名字段的可信度地基）、docs/PM-M11-DIRECTION.md（三个「0」之二）

## 背景

当前平台身份 = 前端 localStorage 自报称呼（`frontend/src/utils/identity.js`），
后端对 `created_by`/`reviewer`/`confirmed_by`/`triggered_by` 全信请求体。
后果：**任何能访问内网页面的人可以以任何名字签发放行、晋升 Agent、投喂样本**。
M10 治理闭环的全部记名证据（宪法「人是唯一签发者」）建立在可伪造身份上——
内网部署前必须收口。这是安全边界改动，实现后 Codex 异源审同步阻塞。

「记名证据可信度地基」的成立前提（F8 定性收口）：本 ADR 建立的是
**应用层**身份信任；cookie 走内网 HTTP 明文（Secure=False、Max-Age 7 天），
可被动嗅探劫持——地基成立以「内网网络本身对嗅探可信」为前提。该前提
不成立的部署（跨网段/不可信交换环境）必须上反代 TLS，否则 M10 记名证据
的信任等级应相应降级看待（与威胁模型表「不防传输层窃听」行互为引用）。

## 决定

### D1 本地用户表，无自助注册

`users` 表：`id / username(UNIQUE) / display_name / password_hash / is_active / created_at`。
账户只能由管理员在服务器上用 `scripts/user_admin.py` 建立
（create / list / deactivate / reset-password；密码走 getpass 交互输入，
**绝不走 argv**——进程列表与 shell 历史不落密码）。不提供注册端点：
注册端点=多一个攻击面，部门内网场景管理员建号是常态。

### D2 密码哈希：stdlib PBKDF2-HMAC-SHA256

`hashlib.pbkdf2_hmac("sha256", pw, salt16B, 600_000)`，存储格式
`pbkdf2_sha256$600000$<salt_hex>$<hash_hex>`（自描述，迭代数可升级共存）。
校验用 `hmac.compare_digest`。**不引入 bcrypt/argon2 新依赖**——内网离线
装包是硬约束（PM-M11 C3），stdlib 方案零装包风险；600k 次迭代为 OWASP
2023 建议值。

### D3 服务端会话 + HttpOnly cookie

- `auth_sessions` 表存 **token 的 SHA-256**（`token_hash(PK) / user_id /
  created_at / expires_at`）——DB 文件泄露不直接换取活会话。
- 明文 token = `secrets.token_urlsafe(32)`，仅存在于 Set-Cookie。
- Cookie `flai_session`：HttpOnly、SameSite=Lax、Path=/、Max-Age=7 天；
  `Secure=False` 并**如实声明**：内网 HTTP 明文部署，传输层加密不在本层
  （内网若有反代 TLS 则直接受益）。
- 有效期固定 7 天，无滑动续期（最小化）；过期判定 `now < expires_at`
  严格比较；登出=删除会话行（服务端即时作废，非仅清 cookie）。
- 不用 JWT：无 secret 管理、可随时吊销、单实例 SQLite 场景无横向扩展诉求。

### D4 强制点：应用级中间件 default-deny

ASGI 中间件挂 `create_app()` 内、覆盖全部路由：

- **`/api/*` 一律要求有效会话**（含读接口——部门工具无匿名读需求；
  读放开=样本库/任务详情对全内网裸奔，与 B2 数据分级冲突）。
- allowlist 仅两项精确匹配：`POST /api/auth/login`、`GET /api/health`
  （部署自检门 C2 依赖，仅暴露布尔位不含数据）。
- OPTIONS 只放行**真 CORS preflight**，谓词=「Origin 与
  Access-Control-Request-Method 双头共存」（F1）；裸 OPTIONS 落回默认
  拒绝——不留免鉴权的路由枚举探测面。witness：无双头的
  `OPTIONS /api/tasks` → 401。
- 非 `/api/*`（静态资产 + SPA fallback）放行——登录页本身要能加载。
- 未认证 → 401 JSON `{"detail": "未登录或会话已过期"}`；**默认拒绝**：
  新增路由自动落在门内，忘配置=被拒而非裸奔（fail-closed）。
- 通过后 `request.state.user = {id, username, display_name}` 供处理器取用。

### D5 记名字段认证化（服务端派生，不再信请求体）

`created_by`（tasks/feedback/conversations）、`reviewer`（人工放行）、
`triggered_by`（eval-runs）、`confirmed_by`（promote）一律改为
**服务端从会话身份取 `display_name`**，请求体中对应字段删除；
前端各 api 客户端停发。晋升门五条中的「confirmed_by 记名」从此指向
认证身份而非自报文本。DB 列与实体 schema 不变（值的来源变可信）。

**历史数据对账口径（F7，PM 裁决）**：本 ADR 生效前落库的记名行
（含默认值 `anonymous`、e2e 注入名等）是**自报时代数据，如实保留，
不回填不打标不冒充**——分界即 `users` 表建立时间。当前库内数据均为
mock/演示期产物（M4 未解锁，真实工程数据尚未进场），打标成本>收益；
将来治理链溯源历史 promotions/eval_runs 时，早于分界的记名一律按
「自报未认证」的证据等级看待。CLI 侧（scripts/promote_agent_l1.py 等
服务器上运维脚本）的记名仍走 argv——能上服务器执行脚本者即运维身份，
与 ADR-0018 P1-1 同一边界裁决。

### D6 登录失败节流（进程内，诚实边界）

按 username 计数挂 `app.state`：15 分钟窗口内失败 ≥5 次 → 429 锁 15 分钟，
成功登录清零。**锁定期内任意尝试（含正确密码）一律 429**（F5）——节流
判定先于凭据校验，否则锁定只挡「连续猜错」、对「猜中那一次」无效。
**如实声明**：进程内实现，多进程/重启不共享——当前部署形态为单实例
常驻，够用；升级多实例时移入 DB（递延已记录）。

### D7 SSO 适配缝

凭据校验收敛为单点函数 `verify_credentials(conn, username, password)
-> user | None`。将来内网 AD/LDAP/反代 header 认证**只替换此函数**，
会话签发、中间件、记名派生全部不动。本批不实现任何 SSO。

### D8 前端：登录门替换称呼门

- `WelcomeGate.vue` → 真登录表单（用户名+密码 → `POST /api/auth/login`）；
  错误如实展示后端 detail（401 凭据错误 / 429 节流），不粉饰。
- App 启动 `GET /api/auth/me` 定登录态；`client.js` 收到 401 → 派发
  `flai:unauthorized` 事件 → App 重新亮门（会话过期中途兜底）。
- 侧栏身份钮显示 `display_name`，点击 → 确认后 `POST /api/auth/logout`
  回登录门。`identity.js` 的 localStorage 身份**退役**。

### D9 部署引导（配合 C2 自检门）

老库升级后 `users` 为空 → 所有人被锁在门外，这是**有意的 fail-closed**：
部署步骤第一条即 `user_admin.py create`；C2 部署自检门加「users 表存在
且 ≥1 活跃账户」检查项。**不提供任何 `AUTH_OFF` 旁路开关**——旁路 flag
必然漂进内网部署（fail-open 大忌）。开发/e2e 同样走真登录。

## 威胁模型（诚实边界）

| 防 | 不防（如实声明） |
|---|---|
| 身份冒用（自报名字签发/晋升/投喂样本） | 传输层窃听（内网 HTTP 明文；反代 TLS 是部署层选项——与背景段 F8 前提声明互为引用） |
| 匿名读写（default-deny 全 API） | 能读写服务器文件系统者（能改 DB 者能改门代码——同 ADR-0018 P1-1 边界裁决） |
| 会话令牌 DB 泄露复用（存哈希） | 分布式暴力破解（节流为进程内单实例口径） |
| 基础在线暴力猜密（429 节流，锁定期内正确密码同拒） | CSRF 深度防御（SameSite=Lax + CORS localhost 白名单已覆盖主路径——全部写端点均非 GET，前提已核验；无 token 层，递延） |
| 裸 OPTIONS 路由枚举（F1 真 preflight 双头谓词） | XSS session-riding（HttpOnly 防读 cookie，不防 XSS 借已认证浏览器发同源请求——无 CSP 层，递延） |

## 验收标准（R1 按 F1-F6 扩充）

1. 未登录访问任意 `/api/*`（除 allowlist 两项）→ 401；登录后放行。
   **结构不变量（F2）**：遍历 `app.routes` 全部 API 路由（参数占位）逐条
   未登录打一遍，非 allowlist 一律 401——单条 router 挂载漂移/裸奔必咬。
2. 错密码 401 / 连续 5 错 429 / **锁定期内正确密码亦 429（F5）** /
   停用账户 401（与错密码同文案）/ 登出后旧 cookie 401 /
   **过期边界双侧 witness（F3）**：expires_at 过去一侧 401、未来一侧 200
   ——严格 `<` 被改 `<=` 或方向反转必咬。
3. 记名字段全部来自会话身份：请求体伪造 `created_by/reviewer/...` 不生效并测死。
4. tamper 咬合：绕过中间件 allowlist 加一条 `/api/tasks` → 对应测试必红。
5. **会话哈希落库 witness（F4）**：登录后直查 `auth_sessions`，断言
   `token_hash == sha256(cookie 明文)` 且 `!= cookie 明文`——「存哈希」承诺
   有直接见证。
6. **裸 OPTIONS witness（F1）**：无双头的 `OPTIONS /api/tasks` → 401；
   带双头 preflight → 放行（CORSMiddleware 应答）。
7. 全部 7 套 e2e 注入真实登录后重绿；新增 m11_auth e2e：UI 登录/错密码
   诚实报错/未登录 API 401/登出回门。
8. 现有 569 pytest 经 conftest 登录注入后全绿 + 新增 auth 单测。
   **登录注入必须走真实 `POST /api/auth/login` 换真实 Set-Cookie（F6）**——
   绝不 DB 直插 session 行/monkeypatch 短路中间件（那是活在 conftest 里的
   AUTH_OFF，D9 明文拒绝的模式）。配结构检查钉死：扫描 backend/tests/*.py，
   `INSERT INTO auth_sessions` 零命中且 conftest 含真实登录调用。
