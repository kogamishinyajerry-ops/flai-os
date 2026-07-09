# ADR-0006: Kernel V0.1 全新建仓，COMACAgentPlatform 降级为资产库

- 状态：已接受（owner 拍板，2026-07-08）
- 背景：已有 COMACAgentPlatform 仓（约 2.8k 测试、9 业务模块、TrustGate/HMAC 审计链等
  重治理机制），但其架构承载的是「自组织 AI 工程团队」旧范式，目录形态与任务书 §5
  的内核结构不兼容；owner 痛点=架构混乱、进度难管控、难多人协作。
- 决策：FLAi-OS Kernel V0.1 在 `flai-os/` 全新初始化，逐字落实任务书 §5 结构；
  COMACAgentPlatform 转为**资产库**——工具适配器（OpenFOAM/CalculiX/CAD 等）、
  FTA/控制逻辑模块业务逻辑、脱敏 fixture 在 M4/M5 按需收编（收编地图=该仓
  `docs/architecture/FLAI-OS-V1-RESTRUCTURE.md` §2/§3.3 的 8 路盘点结果）。
- 理由：①任务书明令「按结构初始化项目」且内核要求轻（SQLite/轮询 Job Runner/轻
  Runtime），在厚重现仓里做减法比新建做加法成本高一个量级；②多人协作需要新人
  10 分钟看懂的仓，现仓做不到；③现仓资产不丢——原地保留、按图收编。
- 替代方案：现仓在位重构（被否：目录形态永远对不上任务书）；同仓双轨（被否：
  两代并存边界更乱）。
- 影响与风险：收编时需重新走本仓契约校验与测试（原仓测试不自动继承）；
  两仓短期并存，以本仓为唯一开发主线，原仓只读取材。
