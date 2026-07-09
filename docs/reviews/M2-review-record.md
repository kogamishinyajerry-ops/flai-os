# M2 收口审查记录（可追溯存档）

> 与 M1-review-record.md 同一存档纪律：原始发现落盘可独立核验，处置以
> commit 为准。M2 主体 = commit 7aaf866（五页 UI + Feedback API + 静态托管）。

## 反方审查 R1（异构 subagent 十问，2026-07-09，结论 CHANGES_REQUIRED）

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P1 | 「六条验收全绿+截图存档」声明在**仓库内无可复核证据**（走查脚本与截图只存在于会话临时目录）——声明力度 > 证据等级 | 修：走查脚本重写为自包含可重跑版入仓 `frontend/e2e/m2_acceptance.py`（自起后端+tmp 目录+自跑 runner），截图入仓 `docs/reviews/m2-acceptance-shots/`，本记录建档 |
| 2 | P1 | waiting_review 人工放行 UI（宪法「人是唯一签发者」的界面落点）**零验证覆盖**——hello_agent 永不产生该状态 | 修：验收脚本内置 review_agent 场景（tmp 复制 hello_agent 置 requires_human_review=true），真浏览器走「进入 waiting_review→具名批准→completed+review_approved 上时间轴」全链 |
| 3 | P2 | TaskDetail 在 waiting_review 停止轮询且无手动刷新，跨会话审批不刷新 | 修：加「刷新」按钮（轮询停止语义保留并注释说明） |
| 4 | P2 | TaskCreate agent 列表加载失败只有瞬时 toast，与其余四页持久 alert 不一致 | 修：持久 el-alert |
| 5 | P2 | bundle >500kB / 零前端单测 / feedback message 无上限——均未声明为已知边界 | 修：README「V0.1 已知限制」段 |
| 6 | P3 | spa_fallback `/api` 守卫大小写敏感，`/API/x` 回 index.html 而非 404 | 修：lower() 判定+测试 |
| 7 | P3 | TaskDetail 轮询无退避/上限 | 记债（README 已知限制段），agent 变长耗时（M3+）再议 |

十问中过关项（有证据）：前端错误路径诚实（持久 alert+ApiError.detail 原文）、
API 契约前后端零漂移（逐字段核对）、XSS 面干净（全仓 0 处 v-html/innerHTML）、
静态托管穿越防护扎实（resolve 前缀+三探针实测）、十态枚举与状态机逐一一致、
201/201 后端测试真绿。

## 86gs 治理审（异源 Codex，`codex review --commit 7aaf866`，2026-07-09）

**P1 零**。P2×2：

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P2 | TaskCreate 选中即上传，移除/弃页/创建失败均留孤儿文件且无清理路径 | 修：改提交时上传（孤儿窗口收窄到 createTask 失败一种）；残余窗口记 M3 GC 债 |
| 2 | P2 | `repos.list_tasks` 硬顶 100 条，>100 任务后历史页与反馈选择器静默截断 | 修：limit/offset 参数化（API 上限 500+越界 422）+ 历史页「加载更多」+ 反馈选择器诚实提示 |

## 验收证据（可重跑）

```bash
cd frontend && npm run build && cd ..
uv run --no-project --with playwright --with uvicorn --with fastapi \
  --with jsonschema --with pyyaml --with httpx --with python-multipart \
  --with "pydantic>2" python frontend/e2e/m2_acceptance.py
```

覆盖 §12.3 六条 + 历史页/SPA 深链刷新 + waiting_review 人工放行全链；
截图产物 `docs/reviews/m2-acceptance-shots/`（重跑覆盖，与代码同步）。
最终走查结果与测试计数见 M2 收口 commit message。
