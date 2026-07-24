# Open WebUI 只读参考审计

> 状态：`SOURCE_REFERENCE_AUDIT / PROPOSED`
> 审计对象：Open WebUI `v0.10.2`
> 用途：FLAi-OS Desktop Workspace Shell 的交互、布局和接口样本
> 结论：参考，不内嵌；研究，不接管事实；不自动更新。

## 1. 结论

Open WebUI 可以作为 FLAi-OS 的外部设计基准和行为样本库，但不应直接成为 FLAi-OS 的长期 UI
代码底座、运行时底座或事实拥有者。

推荐路线是：

> 锁定 Open WebUI 版本做只读研究，提取可验证的交互模式；在 FLAi-OS 现有 Vue 3 前端和
> observer-contract v2 上独立重实现（no-copy）Workspace Shell。

这不是对 Open WebUI 产品质量的否定。原因是 FLAi-OS 的人签、证据、classification、ACL、
REAL/MOCK/TEST、fail-closed 和离线发布要求，不能委托给一个自带会话数据库、Socket 协议、
工具执行语义和品牌许可边界的外部应用。

## 2. 固定审计对象

| 字段 | 值 |
| --- | --- |
| 上游仓库 | `https://github.com/open-webui/open-webui.git` |
| 版本 | `v0.10.2` |
| commit | `ecd48e2f718220a6400ecf49eafd4867a38feb10` |
| tree | `6273a9ed3d194683775893b36e4541b543156320` |
| commit time | `2026-07-01T03:40:54-05:00` |
| tag kind | lightweight tag |
| 本地签名验证 | `DECLARED-NOT-VERIFIED`：commit 带签名，但本机缺少公钥 `B5690EEEBB952194` |

审计时关键文件摘要：

| 文件 | SHA-256 |
| --- | --- |
| `LICENSE` | `5f1bd74c48bf13ab0f82e177ad9e637313b92533d20ead2593d49347a47fc232` |
| `LICENSE_NOTICE` | `9de72254becbb9a317410a459447be7e8f042b911a846c58307319c77e50df00` |
| `LICENSE_HISTORY` | `b1567cc9763241a41569e01f08272a167dac57273f717b95b31ba7b5ec935e17` |
| `package.json` | `60f26d6101acd07eb302e8f73d2c4fa7e7e36f3b6df69c76086a79e450e9dd8f` |
| `package-lock.json` | `94dc8023d805372a08b56af0d4b98977a4b720c2238aecc03554d8f502391144` |
| `pyproject.toml` | `80cca71d206c0a40bdd2239589bebf5ec823f527f0ec4eafe11db2902a9edc3a` |
| `uv.lock` | `f789bbf43e7c45466fa057ecf20bada5f47bf4d172492b87b08ff6ab8f4c0498` |

这些值只是本次研究的供应链定位证据，不等同于上游身份已验证，也不授权把上游源码复制进
FLAi-OS。

## 3. 四条候选路线

| 路线 | 说明 | 初期速度 | 长期适配 | 治理风险 | 决策 |
| --- | --- | ---: | ---: | ---: | --- |
| A. 直接 fork | 以 Open WebUI 前后端作为产品底座并持续改造 | 高 | 低 | 高 | 拒绝 |
| B. 并列部署 | 将 Open WebUI 作为独立聊天应用，通过 iframe/链接/薄适配接入 | 中 | 中低 | 高：形成第二事实源 | 暂不采用 |
| C. 独立 no-copy Shell | 锁版本研究行为，在现有 Vue + FLAi 合同上重新实现 | 中 | 高 | 低 | **推荐** |
| D. 先做原生 macOS | 立即用 SwiftUI/AppKit 重写完整桌面工作台 | 低 | 中高 | 中：过早分裂前端 | 后续阶段 |

路线 C 的代价是需要自己实现交互细节；收益是事实、权限、证据、签发和离线供应链仍由 FLAi-OS
控制，而且 Kimi 可以在新原型目录中独立打磨体验，不与 Codex 的生产合同工作重叠。

## 4. 可吸收的设计模式

可以在不复制实现代码或品牌资产的前提下，研究并重新表达：

- 左侧紧凑的工作区与最近任务导航；
- 中央连续任务流，而不是传统后台表单堆叠；
- 输入框与执行队列的连贯体验；
- 生成中状态、停止、继续和恢复；
- 右侧 Artifact / Preview / Focus Surface；
- 对话内文件、引用和工具结果的渐进披露；
- 离线部署需要显式预下载资源的运维意识；
- 快捷键、响应式布局和 reduced-motion 行为。

ChatGPT Desktop 可作为“聊天与工作切换、统一最近项目、跨设备连续性”的体验参照；Claude
Desktop/Cowork 可作为“Artifact 独立预览、工作文件夹和持续执行”的体验参照。它们都是体验基准，
不是 FLAi-OS 的接口或事实合同。

## 5. 不得吸收的运行语义

以下内容不能进入 Workspace Shell：

- Open WebUI 自有用户、会话、聊天、权限或数据库成为 FLAi-OS 事实源；
- `localStorage.token`、Open WebUI `/api/v1`、Socket.IO 事件协议成为生产接口；
- 服务端消息触发浏览器 `new Function(...)` 或任意 JavaScript 执行；
- Workspace Tools 的进程内任意 Python 执行模型；
- 未绑定 Artifact digest、classification、ACL 和 source witness 的预览内容；
- UI 仅凭本地乐观状态显示 REAL、绿色完成或真人签发；
- 未经审核的 Open WebUI 品牌、图标、文案、源码片段或 CSS 直接复制；
- Open WebUI 构建脚本在构建期从 PyPI 等外部源动态选择“最新”包；
- 自动跟随上游 `main`、未固定 commit 的依赖或未经摘要校验的离线资产。

## 6. 代码与供应链发现

### 6.1 技术栈和耦合

审计版本使用 Svelte 5、SvelteKit、Vite、Tailwind、Socket.IO 与 Open WebUI 自有 API/Store。FLAi-OS
当前是 Vue 3、Vite 和 Element Plus。核心页面不是可抽离的无状态组件：

- `src/lib/components/chat/Chat.svelte` 约 3,400 行，并直接依赖大量 store、API、Socket 和聊天持久化；
- `src/lib/components/chat/MessageInput.svelte` 超过 2,000 行；
- Sidebar、Artifacts 和 Chat Controls 同样绑定其内部状态模型；
- `Chat.svelte` 的 `execute` 事件路径可调用 `new Function`，与 FLAi-OS 的沙箱和审批边界不兼容。

因此，“只拿 UI”在工程上并不是低成本复制，而会把 Open WebUI 的状态机和信任假设一起带入。

### 6.2 构建确定性

审计版本的前端 build 会调用 `scripts/prepare-pyodide.js`。该脚本可查询 PyPI 最新版本并下载
wheel，部分失败路径记录日志后继续。对于需要签名离线包、可复现构建和 fail-closed 的 FLAi-OS，
这种行为不能原样进入发布流水线。

### 6.3 许可证与品牌

该快照是上游声明的多许可证组合：历史材料依贡献时间保留 MIT 或 BSD 3-Clause 等先前许可，
后续贡献适用当前 Open WebUI License；具体文件归属仍须逐文件 provenance 核验。当前 Open WebUI
License 的品牌条款对修改、移除、遮挡或替换 Open WebUI 品牌设置了条件，包括滚动 30 天内总用户
不超过 50、取得书面许可或持有企业许可等路径。FLAi-OS 早期 20–30 人试点可能落入其中一个例外，
但扩容、统计口径、分发方式和白标目标会带来持续合规负担。

因此：

- 本项目不依赖“永远少于 50 人”作为架构前提；
- 不把历史 BSD 版本视为当前功能的无风险替代；
- 如未来确需复制或分发上游实现，必须由法务/采购对具体版本、用户口径、品牌和企业许可单独评审。

“独立重实现（no-copy）”在本文中只表示：实现线程不复制上游代码或资产，并遵循冻结的行为规格。
它不是对版权或许可证风险的法律结论，也不宣称满足任何特定法域下的严格 clean-room 程序。
本节是工程风险提示，不是法律意见。

## 7. 上游参考账本

- License 文档：<https://docs.openwebui.com/license/>
- 仓库 LICENSE：<https://github.com/open-webui/open-webui/blob/main/LICENSE>
- Enterprise：<https://docs.openwebui.com/enterprise/>
- Artifacts：<https://docs.openwebui.com/features/chat-conversations/chat-features/code-execution/artifacts/>
- Message Queue：<https://docs.openwebui.com/features/chat-conversations/chat-features/message-queue/>
- Offline Mode：<https://docs.openwebui.com/tutorials/maintenance/offline-mode/>
- ChatGPT macOS release notes：<https://help.openai.com/en/articles/9703738-desktop-app-release-notes>
- ChatGPT release notes：<https://help.openai.com/en/articles/6825453-chatgpt-release-notes>
- Claude Artifacts：<https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them>
- Claude Cowork surfaces：<https://support.claude.com/en/articles/15520349-use-claude-cowork-on-web-desktop-and-mobile>

## 8. 更新规则

Open WebUI 参考仓库不作为 submodule、package dependency、构建输入或运行依赖提交到 FLAi-OS。
需要复审新版本时，必须：

1. 在 repo 外新建只读临时 clone；
2. 固定 tag、commit、tree 和关键文件摘要；
3. 记录签名验证状态；
4. 重新审查许可证、构建联网行为、任意代码执行、认证和 API 耦合；
5. 只形成差异报告，不自动回灌代码；
6. 由 human owner 决定是否更新参考基线。
