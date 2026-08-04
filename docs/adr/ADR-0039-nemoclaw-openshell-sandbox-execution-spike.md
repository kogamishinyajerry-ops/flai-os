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

结论(按 codex 评审修正,严格区分已证与未证):

- **已证:推理链路全宿主回环,无外网依赖。** 断网窗口内沙箱 agent 经 `inference.local` → 网关 → auth proxy → 回环 Ollama 正常作答;该路径每一跳都是 loopback/私网,不含任何外部依赖;
- **未证:断网窗口内沙箱无残余外网路径。** 实验设计有缺陷——iptables 规则为保 lima DNS 放行了 `198.18.0.0/15`,而验证二证实沙箱出网走的正是 lima 的 198.18.x NAT 路径;宿主机裸 curl 失败只证明宿主机协议栈被断,**不证明沙箱隔离**。原生复测时必须补一笔:断网窗口内从沙箱内部发起越网 curl,应失败且有据可查;

**首次部署后的推理运行期可以全离线**(以"已证"为限)。但首次部署必须联网(沙箱镜像 2.19GB + 模型 6.59GB + Node/OpenShell/Ollama 安装包),内网落地需要离线预置管线(建议并入 M11 离线打包立项)。模型对 tool-call 的兼容性:NemoClaw onboarding 会验证结构化 tool call 并拒绝不达标模型,该门必须保留进 FLAi-OS。

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
- 根因(**第一轮推断错误,第二轮已修正**):当时归因为 lima hostResolver 绕过执法点;第二轮(tart/vz NAT)复测证明 198.18.x 假 IP 是 **OpenShell 自己的 DNS 拦截**,两种 VM 栈都会出现,真实机制见附录 B——执法只覆盖 proxy-aware 流量,直连路径在两套环境都不设防。

**结论(第二轮复测后修订,取代原"原生裸金属复测"表述)**:语义层值得吸收;执行层经第二轮金丝雀复测定性为 **"proxy-only 执法"**——协作流量(走 `HTTP_PROXY`)deny-by-default 为真且有 OCSF DENIED 审计;非协作流量(直连/裸 IP)零强制零审计,且在 VM 承载 Docker 下被 NAT 栈掩盖成"一切正常"(详见附录 B)。**"policy Effective ≠ policy enforced"已在两套独立环境实证**——FLAi-OS 任何吸收决策都必须以负向金丝雀测试为验收门,不得采信策略状态字段。裸金属复测仍值得做(预期:直连假 IP 会无路可走而死,但裸 IP 直连泄露大概率依然成立),但已不构成当前决策的阻塞项。

## 验证三:Linux 内网形态兼容性 —— **可落地,但部署面有 8 个实测坑**

在 Ubuntu 24.04.4(官方 P0 路径)上完成全管线,途中踩坑 8 个,全部有修复或变通:

| # | 坑 | 性质 | 修复 |
|---|---|---|---|
| 1 | 容器 DNS 解析失败(colima stub-resolv.conf 悬空) | 环境 | 重写 resolv.conf 指向 lima resolver(官方指引 issue #2101 是 systemd-resolved 方案) |
| 2 | CLI 装入 nvm bin 但 PATH 未持久化,`--resume` 找不到 nemoclaw | 产品缺陷 | 手动 export PATH |
| 3 | `lsof` 缺失 → 网关端口所有权检查误报"未知监听"并拒起 | **产品缺陷**(最小镜像必现;报错文案误导为"root 进程") | apt install lsof |
| 4 | systemd --user 网关服务不带 docker 附加组,连不上 docker.sock | 产品缺陷(docker group 标准配置的 Linux 主机上应普遍复现) | docker.socket SocketGroup 改为主组 |
| 5 | 网关强制 bind 127.0.0.1,沙箱容器跨网桥不可达(issue #5513 同类) | 产品缺陷,**但触发条件比预想窄**(第二轮修正:tart VM 上网关在 docker 驱动就绪时自行绑定了 172.18.0.1 第二监听,问题未复现;第一轮的诱因实为"网关首次启动时 docker 访问未就绪(#4),算不出桥接回调地址") | iptables DNAT + 网桥 route_localnet=1 |
| 6 | socat 转发替代方案被所有权守卫拒绝(8080 多出非网关监听) | 守卫行为正确(反证守卫是真守卫) | 改用方案 5 |
| 7 | 6.14GB 模型下载需显式授权,非交互需 NEMOCLAW_YES=1 | 纪律行为(正面) | 加 env |
| 8 | Mac 侧 grep\|tee\|tail 管道下游停读,VM 内进程 pipe_write 阻塞假死 3 小时 | spike 自身操作失误 | VM 内 nohup 直写日志 |
| 9 | (第二轮)官方 ollama install.sh 拉取 `ollama-linux-arm64.tgz` 404;vz NAT 下 GitHub/ollama.com 大文件反复断流(curl 18/28) | 环境+上游缺陷 | Mac 侧下载后注入 / `curl -C - --retry` 断点续传 |
| 10 | (第二轮)7.7GB RAM **无 swap** 时 9B 模型加载被 oom-kill,探针把快速失败(exit 52)当永久不可用、直接 abort 不重试 | **产品缺陷**(探针竞态;其前置文档其实写了"<8GB 内存配 8GB swap",但"正好 8GB"边界条件未覆盖) | 加 8GB swap;curl 重试包装渡过竞态 |

另两条环境事实:

- **Landlock(第二轮已实证 ABI 可用)**:第一轮 colima kernel 6.8 未暴露 `/sys/kernel/security/landlock`(仅观察,路径缺失非有效判据);第二轮 tart VM kernel 7.0 上 OCSF 日志实证 `Applying Landlock filesystem sandbox [abi:V2 compat:BestEffort] rules_applied:13`——**Landlock ABI V2 真实生效**。内网目标机逐台核验必须用 ABI 探针 `landlock_create_ruleset(..., LANDLOCK_CREATE_RULESET_VERSION)`,不得用路径检查;
- lima 默认把 macOS `/Users` 挂进 VM——"VM 隔离"≠与宿主文件系统隔离,凭证类操作需注意。

**alpha 状态再确认**:官方自述 early preview(2026-03 起),版本间 breaking,明示勿用于生产。本次 spike 的 8 坑中 #2–#5 均为产品侧缺陷,与 alpha 定位相符;"Linux+Docker P0 Tested"标签在 docker-group 标准配置与 VM 承载 Docker 两类常见形态下均有未覆盖缺陷。

## 决策(第二轮证据后修订,待 owner 裁决)

**吸收语义,组件暂不吸收,分三层:**

1. **吸收(语义与模式,立即可做,零外部依赖)**:egress 策略模型(deny-by-default 基线 + binary/method/path 粒度 + preset/tier + operator 审批流 + OPA 评估 + OCSF 审计记录 + 策略内容寻址版本化)、hardening 清单(ulimit/capability/工具剔除/构建期版本断言)、推理面架构(执行面只见 `inference.local`,外部推理必经网关)、凭证不落盘模式、lkg 安装器工艺、构建即审计作风。
2. **组件:OpenShell 暂不吸收为 `SandboxedExecutionPort` 实现**。决定性证据(附录 B):其 egress 执法是 **proxy-only**——只约束尊重 `HTTP_PROXY` 的协作进程;对不协作进程(直连/裸 IP)在两套独立 VM 环境实测零强制、零审计,且失败被 VM NAT 栈掩盖。涉密场景引入一个"显示 Effective 但实际不设防"的沙箱,比没有沙箱更危险(假绿死罪)。替代路径:用成熟原语(docker run `--network` 隔离/allowlist 代理、cap-drop ALL、read-only+tmpfs、ulimit、digest 钉版)自建薄执行层(预估数百行),金丝雀负向测试纳入 verify_all;OpenShell 待其脱离 alpha 且补齐 netfilter 层后重新评估。
3. **不吸收**:OpenClaw/Hermes/DeepAgents 运行时、blueprint 代码、NVIDIA 云推理默认路径、把 NemoClaw 当"现成企业级成熟品"的预期本身。

**主权层不让渡**(与 ADR-0031 一致):contracts 契约本体、十态状态机、人签发 oneOf 形式化、资产/技能包治理链、mock/未核诚实语义、信任色五槽、E0–E3 评测分级、verify_all 离线验证。NemoClaw 的 approval gate 是运行时可放宽配置(thread opt-in auto-approval),不能替代 FLAi-OS 的结构级人签发;两者并存时以 FLAi-OS 为准。

## 风险与边界

- alpha 跟随成本:版本间 breaking,每次升级需重跑金丝雀与安装验收;
- 首次部署外网依赖:镜像/模型/二进制需离线预置管线(并入 M11);
- Landlock 内核依赖逐台核验;
- 内网 x86_64 与 arm64 差异未测(NIM 镜像部分无 arm64 manifest,官方自认);
- 向 NVIDIA 反馈清单(若继续推进):lsof 缺失误报(#3)、systemd user 服务 docker 组(#4)、VM 承载 Docker 的 bind 拓扑(#5,附 issue #5513)、本 spike 的 egress 执法绕过现象(待原生复测确认后上报)。

## 附录 A:复现 runbook(按 codex 评审补齐)

**不可变标识(全量,未截断)**

- NemoClaw v0.0.97(lkg 安装器,2026-08-03)/ OpenShell 0.0.85 / Ollama 0.32.5 / Docker 29.5.2 / kernel 6.8.0-117-generic(Ubuntu 24.04.4 aarch64,colima 0.9 default 实例 4C/8G/80G)
- 模型:`qwen3.5:9b`,6,594,474,711 字节,digest `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`
- 沙箱镜像:`nemoclaw-sandbox-local` sha256:`c96940ab0a147c04127267a2abb3488fcf44d21663c8c3e04c84b1fa9be5acc0`(2.19GB);`ghcr.io/nvidia/nemoclaw/sandbox-base` sha256:`a2c7da00bbf60a564f68e1138c50d01a557525b565a810c9eab3294705f337ce`(1.82GB)
- 策略:v3,hash sha256 `81f6922a090f69d107d0cea964dfb48cc90f6ea641a2c6f99d8aa1c73f2ae11a`,Status=Effective,仅激活 `local-inference` preset

**安装命令(VM 内,逐一执行)**

```bash
sudo apt-get install -y zstd binutils curl git ca-certificates jq lsof socat iptables
export NEMOCLAW_NON_INTERACTIVE=1 NEMOCLAW_YES=1 NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 \
       NEMOCLAW_AGENT=openclaw NEMOCLAW_PROVIDER=ollama NEMOCLAW_MODEL=qwen3.5:9b \
       NEMOCLAW_SANDBOX_NAME=spike-claw NEMOCLAW_POLICY_TIER=restricted \
       NEMOCLAW_WEB_SEARCH_PROVIDER=none NEMOCLAW_IGNORE_RUNTIME_RESOURCES=1 \
       NO_PROXY=localhost,127.0.0.1,inference.local,::1
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash   # 失败后用 nemoclaw onboard --resume 断点续跑
```

**环境修复(按踩坑顺序,# 对应验证三表格)**

```bash
# #1 容器 DNS(stub-resolv.conf 悬空)
sudo rm /etc/resolv.conf && printf 'nameserver 192.168.5.3\nnameserver 8.8.8.8\n' | sudo tee /etc/resolv.conf
# #4 systemd --user 服务无 docker 附加组
printf '[Socket]\nSocketGroup=lima\n' | sudo tee /etc/systemd/system/docker.socket.d/10-group.conf
sudo systemctl daemon-reload && sudo systemctl restart docker.socket docker
# #5 网关 loopback bind,容器跨桥不可达(DNAT 方案;socat 方案会被所有权守卫拒绝)
sudo sysctl -w net.ipv4.conf.all.route_localnet=1
sudo sysctl -w net.ipv4.conf.<openshell-docker 网桥 iface>.route_localnet=1
sudo iptables -t nat -A PREROUTING -d 172.18.0.1 -p tcp --dport 8080 -j DNAT --to-destination 127.0.0.1:8080
```

**验证命令**

```bash
# 推理基线(沙箱内;NODE_EXTRA_CA_CERTS 指向 OpenShell CA bundle 是必需的,见验证三坑表之外的 TLS 发现)
docker exec -u sandbox -e HOME=/sandbox -e NODE_EXTRA_CA_CERTS=/etc/openshell-tls/ca-bundle.pem \
  <sandbox 容器> openclaw agent --agent main --local --session-id t1 -m "<prompt>"
# 断网(注意:本 runbook 的 198.18/15 放行正是 codex 指出的设计缺陷,复测时应改为不放行并补沙箱内越网 curl)
sudo iptables -A OUTPUT -o lo -j ACCEPT
sudo iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT
sudo iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT
sudo iptables -A OUTPUT -d 172.16.0.0/12 -j ACCEPT
sudo iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT
sudo iptables -A OUTPUT -d 198.18.0.0/15 -j ACCEPT   # ← 缺陷所在,复测删除
sudo iptables -A OUTPUT -d 169.254.0.0/16 -j ACCEPT
sudo iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A OUTPUT -j DROP
# egress 金丝雀(沙箱内,Restricted 下应被拒且有 OCSF DENIED 记录;本 spike 实测返回 200 且无记录)
docker exec -u sandbox -e HOME=/sandbox <sandbox 容器> \
  curl -s --noproxy "*" --max-time 8 -o /dev/null -w "%{http_code}\n" https://registry.npmjs.org/
```

**遗留证据**:spike VM 已销毁;Mac 侧 `/tmp/nemoclaw-spike/` 留有各轮 install/onboard 日志(未脱敏入库,重启即失)。另有一项本文未展开的发现:onboarding 期间沙箱 `NODE_EXTRA_CA_CERTS` 默认指向不存在的 `corporate-ca.pem`,导致 agent fetch 报 `SELF_SIGNED_CERT_IN_CHAIN`,需显式指向 `/etc/openshell-tls/ca-bundle.pem`——疑似镜像烘焙 CA 与网关重建后证书不一致,原生复测时应观察是否复现。

## 附录 B:第二轮复测(tart VM / vz NAT,2026-08-04)

**动机**:第一轮(colima/lima)的金丝雀显示 egress 未执法,根因推断为"lima fake-IP NAT 绕过"。为排除 lima 变量,用 tart(Apple Virtualization.framework,vz NAT,与 lima 完全不同的网络栈)重建环境复测。

**环境**:tart 2.32.1,`ghcr.io/cirruslabs/ubuntu:24.04`(arm64),4 vCPU / 7.7GiB + 8GiB swap / 54GiB,kernel 7.0.0-28-generic;NemoClaw v0.0.97 / OpenShell 0.0.85 / Ollama 0.32.5 / 同 digest 的 qwen3.5:9b;Restricted tier,策略 v3,hash 与第一轮相同(81f6922a090f…)。onboarding 完成,"OpenClaw is ready"。

**金丝雀结果(决定性)**:

| 测试 | 结果 | 含义 |
|---|---|---|
| 沙箱内经代理(`HTTP_PROXY=10.200.0.1:3128`)curl npm / example.com | **拒绝**(connect 失败) | proxy 路 deny-by-default 为真 |
| OCSF 审计 | 有 `DENIED -(0) -> example.com:443 [engine:opa]` 等 2 条,reason 含"failed to resolve peer binary … in /proc/net/tcp" | OPA 引擎按进程 binary 归属判定;归属解析失败也 fail-closed 拒绝——执法与审计在 proxy 路上都是真的 |
| 沙箱内**绕过代理**(`--noproxy "*"`)curl npm / github / example.com | **200,真实上游内容,真实公共 CA 证书**(issuer: Cloudflare TLS Issuing ECC CA 3,非 OpenShell MITM CA) | 直连路径零执法 |
| 沙箱内裸 IP 直连 `https://1.1.1.1/` | **301**(Cloudflare 真实响应) | 连 DNS 拦截都不需要的出网路径同样开放 |
| 沙箱 netns 内 netfilter | iptables nat/filter 全空(仅 docker 的 DNS 规则);198.18.x 假 IP 无任何接口绑定;唯一监听是 supervisor 的 3128 代理 | 沙箱网络命名空间内**没有任何 netfilter 级强制** |
| OCSF 审计覆盖面 | 全部直连/裸 IP 流量零记录 | 未代理流量连审计都不经过 |

**机制定性(修正第一轮根因推断)**:`198.18.0.0/15` 假 IP 是 **OpenShell 自己的 DNS 拦截**输出(两套环境同一批假 IP 可证),不是 lima 特有。但 198.18/15 恰好也是 lima(slirp)与 Apple vz NAT 的内部假 IP 段——VM NAT 栈会把发往该段的流量按自己的映射转发到真实目的地,于是"执法空洞"在 VM 承载 Docker 下被掩盖为连接成功。裸金属上直连假 IP 预期无路可走(非协作工具直接失败),但**裸 IP 直连泄露在任何环境都成立**(不经过 DNS 拦截,沙箱内又无 netfilter)。

**其他第二轮证据**:

- 坑 #5(网关 loopback 跨桥不可达)**未复现**:本网关自行绑定 127.0.0.1 + 172.18.0.1 双监听。修正第一轮定性:触发条件是"网关首次启动时 docker 驱动未就绪",不是"VM 承载 Docker 必现";
- Landlock **ABI V2 实证生效**(kernel 7.0,OCSF 日志 `rules_applied:13`);
- 新坑 #9(官方 install.sh 资产名 404 / vz NAT 大文件断流)、#10(7.7GB 无 swap → 模型加载 oom-kill;探针把快速失败当永久不可用直接 abort,不重试)——见验证三坑表;
- 排障副产物:auth proxy(0.0.0.0:11435,Bearer token,timingSafeEqual 按字节比较防长度侧信道、401 无健康检查豁免,issue #3338)与所有权守卫的源码阅读再次确认其安全语义实现得相当认真——**该批评的是执法覆盖面,不是实现态度**。

**遗留证据**:canary VM(tart)销毁前状态可经附录 A runbook + 本附录命令复现;Mac 侧 `/tmp/nemoclaw-spike/` 留有两轮日志(重启即失)。
