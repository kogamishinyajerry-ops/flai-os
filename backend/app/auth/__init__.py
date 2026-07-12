"""鉴权模块（ADR-0019/M11-B1）：本地账户 + 服务端会话。

- passwords.py  PBKDF2 哈希/校验（stdlib，无新依赖——内网离线装包硬约束）
- service.py    用户/会话 CRUD + verify_credentials（SSO 适配缝的唯一替换点）
- 强制点（default-deny 中间件）在 main.py：新增路由默认落在门内。
"""
