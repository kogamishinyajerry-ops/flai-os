# 范式 Phase 2a/2b 对抗审记录（对话轴闭环 + 骨架手术）

> 起因：owner 判定前三批（状态坞/盖章/问候）仍是「老样子」——根因=改的全是
> 装饰层，骨架还是「侧栏+页面+表格」管理后台。深度讨论轮（三张 gpt-image-1
> 示意图=`../design/paradigm-phase2-sketches/` + AskUserQuestion）后 owner
> 拍板：双 Surface 方向 / 先 2a 再 2b / 门户降级 composer 选择器。

## Phase 2a（对话轴闭环）审查

- **双镜头 APPROVE×2**。落修 2 真 P2：①回流落地窗口——GuidePage 挂载期间
  先渲染可交互空态 hero，会话恢复在途发言会误建新会话 → restoring 门控
  （hero 不渲染+send 早退）；②回流分支/锚点行零 e2e 覆盖 → 探针升格为第 6
  套 e2e `m9_guide_loop_acceptance.py`（9 断言，自起后端+stub gateway+DB
  夹具），「零跳页」从代码走读升格为可重跑实证。
- 2 条核验结论确认契约零触碰（WorkbenchSession 路径无 back=chat/门户直建
  不误回流）。formatSize 双份 → 抽 `formatFileSize` utils SSOT（含 GB 档）。
- Codex 异源审超时（1800s 无响应）→ post-merge 补审队列（纯前端非安全边界）。

## Phase 2b（骨架手术）审查

双镜头：regression APPROVE（1P2+3P3）/ trust CHANGES_REQUIRED（2P2+3P3），
**8 条全落修**：

| 级 | Finding | 修法 |
|----|---------|------|
| P2（回归） | TaskDetail 轮询缺 disposed 守卫——任务台 :key 重建把「切任务」变高频交互，卸载竞态下死实例闭包武装僵尸轮询 | disposed 标志 + onUnmounted 置位（与 TaskConsole 模式对齐） |
| P2（信任） | Agent 选择器 :key="a.agent_id" 用错字段（API 投影是 id）——全部 undefined 撞键 | :key="a.id"，与 AgentPortal/QuickSwitcher 既有用法对齐 |
| P2（信任） | 门户降级后唯一入口是无文字纯图标，可发现性弱于旧导航 | hero 提示行加「输入框左侧 ◎ 可浏览全部可用 Agent」 |
| P3×5 | 选择器错误态「· 0」双重信号 / 空态缺 variant=action / WorkbenchSession 返回钮术语漂移 / App.vue「三入口」注释陈旧 / EmptyState 注释引用已删文件 | 全部按 lens 建议落修 |
| P3（回归·历史债） | 「到席灯 completed 不给绿」新旧断言都只查可见性——**声明超出证据** | m8_workbench 补颜色级断言：`to_have_css("background-color", "rgb(107,98,89)")`（--ink-soft），信任色锁首次被 e2e 真咬合 |

## e2e 契约重立清单（与骨架同批原子交付）

- `m8_workbench_acceptance.py` 全文重写：①导航恰双入口 ②/workbench 重定向+
  任务台列表+诚实脚注 ②'高亮归属 ②''到席灯颜色真咬合 ③点行→/tasks/:id 中栏
  叙事流 ④高亮保持 ⑤/portal 深链不失联（7 断言）。
- `m8_collab_chain` ⑦：工作台首页 sess-card → redirect+会话入对话侧栏+成员
  任务入列。
- `m6` ①：「智能导引」锚（原命中已删导航项）→ hero 主标题锚。
- m2/m8_orchestrator/m9 零改动存活（TaskDetail 复用保全部详情契约；m2 附加
  断言 /tasks 页 hello_agent 由任务台左栏天然满足）。

## 收口验证

- `bash scripts/verify_all.sh` 八步全绿（build + 全量 pytest + 6 套 e2e，
  m8_workbench 7 断言 + m9 9 断言），失败（无）。
- 实机目检截图：双入口侧栏 / 任务台空态 / 三栏选中态（左列表+中叙事流含
  盖章与产物+右来源面板）。
