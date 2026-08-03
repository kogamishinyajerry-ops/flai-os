# ADR-0039:NemoClaw/OpenShell 作为沙箱执行底座的吸收决策(spike 证据)

> 状态:草案(Proposed;spike 已完成,证据齐,待 owner 裁决)
> 日期:2026-08-03(spike 执行),2026-08-04(成文)
> 作者:Kimi K3
> 关联:docs/NEXT-STEPS-ONTOLOGY.md;ADR-0031(只读投影);宪法§六(槽位原则)
> 证据:spike 环境为 colima VM(已销毁),install/onboard 各轮日志未入库;关键数字与结论已抄入本文,可凭本文列出的版本与命令复现

## 背景

FLAi-OS 的工具执行面在进程内运行,无容器隔离、无出网(egress)门禁、无进程/句柄限额。owner 裁决做隔离 spike,验证三件事后决定是否吸收 NemoClaw/OpenShell 作为沙箱执行底座候选。本 ADR 不讨论迁移 agent 运行时(已裁决不迁移:FLAi-OS Agent 是确定性工程包,OpenClaw/Hermes 自主聊天体形态会溶解本体)。

## spike 环境(如实声明)

- macOS 26.5.2(arm64)→ colima `default` 实例:Ubuntu 24.04.4 LTS aarch64,4 vCPU / 7.7GiB + 8GiB swap / docker 盘 93GiB,kernel 6.8.0-117-generic。
- 软件版本:NemoClaw v0.0.97 / OpenShell 0.0.85 / Ollama 0.32.5 / qwen3.5:9b(6.59GB,digest 6488c96f…)/ 沙箱镜像 sha256:c96940ab…(2.19GB)。
- 配置刻意贴近内网:provider=Local Ollama、POLICY_TIER=restricted、web search=none。
- **与内网差异(结论外推前必读)**:①arm64 vs 内网 x86_64(待确认);②colima/lima 是 VM 承载 Docker,与裸金属 Linux 网络路径不同(本 spike 最大的结论限定词);③安装期有外网。

## 验证一:全离线本地推理能否跑通 —— **通过(实测)**

实测过程:onboarding 完成后,在 VM 用 iptables OUTPUT 链切断全部非公网段出口(放行 lo/127/10/172.16/192.168/198.18/169.254),先验证宿主机裸连接已死(`curl --noproxy "*" https://registry.npmjs.org/` → exit 6),然后:

- 沙箱内 agent 经完整链路(沙箱 → `inference.local` → OpenShell 网关 mTLS 路由 → auth proxy :11435 → Ollama :11434 → qwen3.5:9b)回答提问:**正常返回**(status=200,SSE 流,35–96s/题,4 vCPU CPU 推理);
- 宿主机直查 Ollama `/api/generate` 同样正常;
- 推理面架构:沙箱只能看到 `inference.local`,流量天然不出宿主;Ollama 被 `OLLAMA_HOST=127.0.0.1:11434` 锁在回环,NemoClaw 再加一层 :11435 代理。

结论:**首次部署后的运行期可以全离线**。但首次部署必须联网(沙箱镜像 2.19GB + 模型 6.59GB + Node/OpenShell/Ollama 安装包),内网落地需要离线预置管线(建议并入 M11 离线打包立项)。模型对 tool-call 的兼容性:NemoClaw onboarding 会验证结构化 tool call 并拒绝不达标模型,该门必须保留进 FLAi-OS。

## 验证二:sandbox / egress 最小配置面 —— **语义真实,执行为假(本环境),必须复测**

**正面证据(设计语义为真)**:

- deny-by-default 策略模型:基线仅 5 条端点规则,按 binary+method+path 粒度,TLS:443;三档 tier(Restricted=仅基线);未列名目标应被拦截并转 operator TUI 审批;
- 实测 Restricted 下发后 `policy list` 仅 `local-inference` 一条激活,其余 27 条 preset 全部关闭;策略有版本(v3)、内容寻址 hash(sha256 81f6922a090f…)、Status=Effective——策略对象本身的纪律与 FLAi-OS 同级;
- 网关认证边界为真:mTLS `require_client_auth=true` + JWT,无客户端证书直连被拒;
- hardening 清单为真:镜像剔除 gcc/make/netcat、ulimit nproc=512/nofile=65536、降 capabilities(可用 `NEMOCLAW_REQUIRE_CAP_DROP=1` 改 fail-closed)、构建期逐包版本断言 + `html/parser.py` sha256 校验 + 清单文件 root:root 444;
- 文件系统:/sandbox、/tmp 可写,系统路径只读,专用 sandbox 用户。

**负面证据(执行链断裂,本环境)**:

- 策略 v3 显示 Effective,但沙箱内 `curl https://registry.npmjs.org/react/latest` 和 `https://github.com/` **均返回 200 且为真实上游内容**——deny-by-default 未执行;
- 沙箱的 OCSF 审计日志只有 `ALLOWED inference.local:443`,**被放行的 npm/github 连接完全无记录**——"策略显示生效、实际未执行、审计无记录"三连;
- 根因(合理推断,未完全钉死):沙箱 DNS 走 docker 内嵌解析器(127.0.0.11)→ lima hostResolver(192.168.5.3)返回 198.18.x 假 IP,流量经 lima NAT 直接出宿主,未经 supervisor 的 10.200.0.1:3128 代理;即 colima/lima 的 DNS/NAT 路径绕过了 OpenShell 依赖 DNS 拦截的执法点。spike 期间为修容器 DNS 曾向 docker daemon.json 写入公共 DNS,可能加重了绕过。

**结论与硬性要求**:语义层值得吸收;执行层**必须在原生 Linux x86_64 裸金属上复测"金丝雀出网"用例**(Restricted 下沙箱 curl 外网应被拒且 OCSF 有 DENIED 记录)。复测通过才可把 OpenShell 列为实现候选;复测若仍 fail-open,则不吸收其运行时,仅借鉴策略模型。**无论复测结果如何,"policy Effective ≠ policy enforced"已在本次 spike 实证——FLAi-OS 若吸收,验收门必须包含负向金丝雀测试,不得采信策略状态字段。**

## 验证三:Linux 内网形态兼容性 —— **可落地,但部署面有 8 个实测坑**

在 Ubuntu 24.04.4(官方 P0 路径)上完成全管线,途中踩坑 8 个,全部有修复或变通:

| # | 坑 | 性质 | 修复 |
|---|---|---|---|
| 1 | 容器 DNS 解析失败(colima stub-resolv.conf 悬空) | 环境 | 重写 resolv.conf 指向 lima resolver(官方指引 issue #2101 是 systemd-resolved 方案) |
| 2 | CLI 装入 nvm bin 但 PATH 未持久化,`--resume` 找不到 nemoclaw | 产品缺陷 | 手动 export PATH |
| 3 | `lsof` 缺失 → 网关端口所有权检查误报"未知监听"并拒起 | **产品缺陷**(最小镜像必现;报错文案误导为"root 进程") | apt install lsof |
| 4 | systemd --user 网关服务不带 docker 附加组,连不上 docker.sock | 产品缺陷(docker group 标准配置的 Linux 主机上应普遍复现) | docker.socket SocketGroup 改为主组 |
| 5 | 网关强制 bind 127.0.0.1,沙箱容器跨网桥不可达(issue #5513 同类,WSL/VM 承载 Docker 必现) | **产品缺陷**(官方未修;0.0.0.0 被显式禁止) | iptables DNAT + 网桥 route_localnet=1 |
| 6 | socat 转发替代方案被所有权守卫拒绝(8080 多出非网关监听) | 守卫行为正确(反证守卫是真守卫) | 改用方案 5 |
| 7 | 6.14GB 模型下载需显式授权,非交互需 NEMOCLAW_YES=1 | 纪律行为(正面) | 加 env |
| 8 | Mac 侧 grep\|tee\|tail 管道下游停读,VM 内进程 pipe_write 阻塞假死 3 小时 | spike 自身操作失误 | VM 内 nohup 直写日志 |

另两条环境事实:

- **Landlock 不可用**:该 kernel 6.8 未暴露 `/sys/kernel/security/landlock`,沙箱文件系统约束静默降级为 DAC-only。内网目标机必须逐台核验(≥5.13 且开启 LSM),否则"系统路径只读"只剩 POSIX 权限;
- lima 默认把 macOS `/Users` 挂进 VM——"VM 隔离"≠与宿主文件系统隔离,凭证类操作需注意。

**alpha 状态再确认**:官方自述 early preview(2026-03 起),版本间 breaking,明示勿用于生产。本次 spike 的 8 坑中 #2–#5 均为产品侧缺陷,与 alpha 定位相符;"Linux+Docker P0 Tested"标签在 docker-group 标准配置与 VM 承载 Docker 两类常见形态下均有未覆盖缺陷。

## 决策(草稿,待 owner 裁决)

**有条件吸收,分三层:**

1. **吸收(语义与模式)**:egress 策略模型(deny-by-default 基线 + binary/method/path 粒度 + preset/tier + operator 审批流)、hardening 清单(ulimit/capability/工具剔除/构建期版本断言)、推理面架构(沙箱只见 inference.local,外部推理必经网关)、凭证不落盘模式、lkg 安装器工艺。
2. **候选(组件,需过两道门)**:OpenShell 作为 `SandboxedExecutionPort` 的第一实现候选。两道门:①**原生 Linux x86_64 复测金丝雀出网**(验证二);②契约先行——在 FLAi-OS `contracts/` 定义 `SandboxedExecutionPort` 接口(fail-closed 未接入分支),OpenShell 仅是端口的一种实现,任何时候可摘除。
3. **不吸收**:OpenClaw/Hermes/DeepAgents 运行时、blueprint 代码、NVIDIA 云推理默认路径、把 NemoClaw 当"现成企业级成熟品"的预期本身。

**主权层不让渡**(与 ADR-0031 一致):contracts 契约本体、十态状态机、人签发 oneOf 形式化、资产/技能包治理链、mock/未核诚实语义、信任色五槽、E0–E3 评测分级、verify_all 离线验证。NemoClaw 的 approval gate 是运行时可放宽配置(thread opt-in auto-approval),不能替代 FLAi-OS 的结构级人签发;两者并存时以 FLAi-OS 为准。

## 风险与边界

- alpha 跟随成本:版本间 breaking,每次升级需重跑金丝雀与安装验收;
- 首次部署外网依赖:镜像/模型/二进制需离线预置管线(并入 M11);
- Landlock 内核依赖逐台核验;
- 内网 x86_64 与 arm64 差异未测(NIM 镜像部分无 arm64 manifest,官方自认);
- 向 NVIDIA 反馈清单(若继续推进):lsof 缺失误报(#3)、systemd user 服务 docker 组(#4)、VM 承载 Docker 的 bind 拓扑(#5,附 issue #5513)、本 spike 的 egress 执法绕过现象(待原生复测确认后上报)。
