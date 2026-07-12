# M11-C3 离线发布包双分支预案

> 状态：**预案，不盲做**。两个分支的取舍取决于 M4 对接方回复
> （`docs/M4-UNLOCK-REQUEST.md` 已问：内网机器 Python 环境与安装限制、
> 有无内部 pip 镜像）。回复到位前只锁定方案与风险，不产出完整发布包——
> 在错误假设上打出来的包是白做。
>
> 配套：部署后验收统一走 `scripts/deploy_selfcheck.py`（M11-C2 自检门，
> 全 PASS 才算部署完成）。`scripts/package_release.*` 在决策门落锤前保持
> 诚实占位（NOT-IMPLEMENTED）。

## 0. 共同底座（两分支都要，与镜像有无无关）

| 件 | 说明 |
|---|---|
| `frontend/dist/` 预构建 | **在外网开发机构建后入包**。内网不装 node——FastAPI 检测到 dist 即静态托管（`config.FRONTEND_DIST_DIR`），这是既定架构而非新决策 |
| 源码树 | backend/ + agents/ + tools_impl/ + contracts/ + scripts/ + docs/（不含 data/、tests 可选） |
| 初始化三步 | `init_db` → `user_admin.py create <首账户>`（ADR-0019 D9：库空=全员锁门外，有意 fail-closed）→ 启动服务 |
| 验收 | `deploy_selfcheck` 8 项全 PASS |
| 备份纪律 | `backup_restore.py` 随包（M11-B3），恢复即吊销全部会话 |

**打包前置事实（必须先从 M4 回复拿到，缺一不打包）：**
1. 目标 OS 与位数（现有 .ps1 脚本按 Windows 预留，但未确认）；
2. 目标 Python 版本（决定 wheel 的 ABI 标签，猜错=整包报废）；
3. 有无内部 pip 镜像及其覆盖面（决定走分支 A 还是 B）。

## 分支 A：内网有 pip 镜像

**形态**：源码包 + `requirements.lock`（含精确版本与 hash），内网执行
`pip install -r requirements.lock -i <内网镜像>`。

- 产出物小（不含 wheels），Python 小版本差异由镜像侧解决。
- 前提核验：镜像必须覆盖全部依赖（fastapi/uvicorn/pydantic>2/jsonschema/
  pyyaml/python-multipart/httpx/openpyxl/jieba）。**拿到镜像地址后先跑一次
  依赖清单比对再打包**——缺一个包就地降级到分支 B，不现场找替代。
- 风险：镜像同名包版本被内网方钉死在旧版 → 以 lock 文件为准提出例外申请，
  不静默降版本（pydantic v1/v2 这类断代差异会直接炸）。

## 分支 B：内网无 pip 镜像（wheelhouse 全离线）

**形态**：源码包 + `wheels/` 目录（全部依赖的二进制 wheel），内网执行
`pip install --no-index --find-links=wheels -r requirements.lock`。

- 产出物自足，内网零外联。
- **硬前提：wheel 平台标签必须匹配目标机**。在 macOS 开发机直接
  `pip download` 得到的是 macOS wheel，拷到 Windows/Linux 内网机=整包不可装。
  必须 `pip download --platform <目标平台> --python-version <目标版本>
  --only-binary=:all:`，或在与目标同 OS 同 Python 的机器/容器里下载。
- 风险：个别依赖无预编译 wheel（纯源码 sdist）→ 内网机无编译工具链即失败。
  当前依赖清单里 jieba 是纯 Python（安全），其余主流包均有官方 wheel；
  打包时用 `--only-binary=:all:` 强制暴露此类问题在外网侧，不带进内网。
- pip 自身版本差异：老 Python 自带 pip 可能不认新 wheel 标签，包里附带
  `pip`/`setuptools`/`wheel` 三件的 wheel 一并离线升级。

## 决策门

```
M4 回复到位？ ──否──→ 维持占位，不打包（本预案即交付物）
      │是
  有 pip 镜像且覆盖全部依赖？ ──是──→ 分支 A
      │否
  能拿到目标 OS/Python 精确版本？ ──是──→ 分支 B
      │否
  升级 M4-UNLOCK-REQUEST 追问（缺版本信息的 wheelhouse 是抽奖不是工程）
```

落锤后把 `package_release.sh/.ps1` 从占位改为所选分支的真实现，并在
verify_all 之外补「打包产物在干净目录可完成初始化三步 + selfcheck 全 PASS」
的打包验收（外网侧模拟，不等内网窗口）。
