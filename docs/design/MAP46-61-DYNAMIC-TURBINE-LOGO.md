# MAP46-61 动态涡轮标识设计稿（prototype · 票 #61）

> 状态：**已定稿（owner 2026-08-06 逐项交互裁 Q1-Q6，结果见 §六末「定稿结果」）**，施工另立票。
> 本文件 + `map46-61-dynamic-turbine/` 预览稿 + `docs/reviews/map46-61-turbine-shots/`
> 截图为全部产出；零产品代码改动。
> 依据：#46 批 2 裁量点④⑩（2026-08-06 定槌）：主标识=花瓣（涡轮叶片+转轴寓意）升级动态涡轮标识，
> 转速随任务状态/复杂度的**确定性信号**调节（完成一轮回答→静止；新请求/难任务→高速）；要「更有辨识度」。
> 读法约定（互审 F6）：文中行号锚=对 origin/main @ cffbef5 **仓库现状的复核描述**（非施工证据）；
> §二~§六 为**提案目标线**，二者不混。

## 一、现状基线（origin/main @ cffbef5 复核）

- 标识四套并立（#57 B2）：侧栏/hero 同源花瓣 PNG（`App.vue:16` 30px、`GuidePage.vue:9` 38px、
  `:75/:514` 26px 消息 mark、`LifeScenarioPicker.vue:12` 34px）→ `components/artwork/FlaiBloom.vue:13`
  → `assets/flai-bloom.png`（clay 螺旋花，256×256，11,125 B）；登录门 `WelcomeGate.vue:49`
  welcome-badge.png 工牌插画（氛围位，B2 口径不作标识）；favicon F 方块（`public/favicon.svg:9-10`，
  `:2` 注释虚标「与侧栏同源」——不符，随施工修正）；样张 emoji 第四套（B5 代际差已挂账）。
- 已有动态先例（现行=**单档恒速**，无分档实现；分档是本票提案，互审 F1）：`FlaiBloom.vue:46-54`
  generating 态整枚旋转 3.6s/圈 linear infinite；绑定面两处，均为请求在途确定性信号——
  `GuidePage.vue:77` 绑逐消息 `m.streaming`（流式中）、`:513-514` 静态 `state="generating"`
  绑 `sending && !hasStreamingAssistant`（已发送待首包）；reduced-motion 降级块 `FlaiBloom.vue:56-62` 已在。
- bundle 实测（本 worktree 同基线 `npm run build` + `check-bundle-budget.mjs`）：
  GuidePage 路由闭包 JS gzip **206,057 B / 225,280 B（余 19,223 B ≈ 18.8 KiB）**；
  入口同步 JS gzip 136,309 B（余 ~87 KiB）；入口 CSS gzip 20,592 B / 40 KiB。

## 二、档位定义（三档，速度值=候选，Q2 裁）

| 档 | 语义 | 转速候选 | 观感 |
|---|---|---|---|
| 静止 idle | 完成一轮回答、平台无活 | 0（真静止，无残动） | 与现行静态完全一致 |
| 慢速 slow | 后台有任务在转，但非本会话直接请求 | 8s/圈 | 余光可辨的「活着」，不抓注意力 |
| 高速 fast | 本会话请求在途（流式进行中） | 1.4s/圈 | 明确可读的「正在为你运转」 |

- 现行 generating 3.6s/圈保留为对照参考（预览稿可切）；三档外是否加中速档随 Q3 信号方案 ii 定。
- 换档过渡：WAAPI `playbackRate` 缓变（~0.4s 缓启/缓停，涡轮惯性感，无相位跳变）——预览稿已按此演示；
  直切（CSS animation-duration 切换）为备选（Q6 裁）。两者均原生零依赖。
- 诚实地板：静止档零残动；任何档位不暗示不存在的活动；信号消失必须回落（MOTION-SYSTEM 硬约束②）。

## 三、形态方案（Q1 裁；预览稿可交互体验）

预览入口：`docs/design/map46-61-dynamic-turbine/index.html`（三案并排 × 三档）；
单案详稿 `scheme-a/b/c-*.html`（含落点 mock、reduced-motion 对照）。截图见 §七。

### 方案甲 · 原花提速（保守基线）
- 形态：flai-bloom.png 一个像素不动，仅把 generating 单档扩成三档。
- 辨识度：形态零变化，强化仅靠「会动」本身——三案中满足度最低。
- 体积账：零变化（PNG 11.1 KB 保留）。实现面：FlaiBloom.vue 只改档位，工作量最小。
- 风险：favicon 虚标注释与四套并立维持现状（B2 不收口）。

### 方案乙 · SVG 涡轮重绘
- 形态：现行花瓣 → 六叶螺旋涡轮（逗号瓣、旋向沿用），中心加**转轴轴孔毂**（evenodd 透明孔，
  随底色）读出「涡轮叶片+转轴」寓意；SVG 任意尺寸锐利（PNG 256px 放大发虚）。
- 辨识度：轴孔毂 + 叶形精修 + 全尺寸锐利；favicon 可同源静态替换（16px 可读性预览稿已验）。
- 体积账：叶片 path ≈0.4 KB + 标记 ≈0.3 KB（gzip <0.5 KB，进 FlaiBloom.vue 所在 entry chunk）；
  flai-bloom.png 11.1 KB 退役——**净省约 10 KB 资产**，GuidePage 闭包 18.8 KiB 余量零消耗。
- 实现面：FlaiBloom.vue 内联 SVG 化，state prop 扩三档（idle/slow/fast），现行 generating
  调用点（GuidePage :77/:514）映射到哪档由 §四定。
- 风险：描稿与 PNG 观感有微差（预览稿即底版），施工票逐尺寸目检；暗色主题下轴孔=透底，已核可读。

### 方案丙 · 涡轮 + 高速尾迹
- 形态：乙的形态 + 高速档两层滞后残影（-20°/-40°，opacity .22/.10）——速度不只靠转速，
  形态本身长「运动模糊」；三档形态差异最大，30px 小尺寸可读。
- 诚实地板：尾迹只在高速信号在时浮现，无信号无残影；reduced-motion 永不渲染（`opacity:0 !important` 兜底）。
- 体积账：乙 +2 组滞后叶片（≈0.2 KB）。实现注意：尾迹组须实 DOM 直写（`<use>` 克隆不吃页内 CSS 类，预览稿已实证）。
- 风险：残影+高转速叠加的视觉「炫」度需 owner 目检拍板（慢速/静止档与乙完全一致）。

## 四、转速信号映射表（确定性信号，同 R-C 纪律；Q3/Q4 裁）

可用确定性信号（现状已有，零新采集）：

| 信号 | 出处 | 口径 |
|---|---|---|
| 本会话流式/请求在途 | `GuidePage.vue:77` `m.streaming`、`:831` anyStreaming | 逐消息布尔，实时 |
| 任务工作态 | `utils/format.js:33` `TASK_WORK_STATES={running,validating,parsing,analyzing}` | 全站统一口径，liveFeed tasks channel 5s 轮询（`StatusDock.vue:48` 同数据） |
| 待签计数 | `StatusDock.vue:49` waiting_review 过滤 | 同上轮询 |
| 排队/新建 | `taskJourney.js:156` queued/created | 同 channel |

候选映射（三选一，也可组合微调——owner 裁）：

| 方案 | 静止 | 慢速 | 高速 | 说明 |
|---|---|---|---|---|
| i（最简） | 无信号 | ≥1 任务在 TASK_WORK_STATES 或 queued（后台在转） | 本会话请求在途（sending/流式） | 三档干净；「难任务」不做区分（复杂度无确定性代理，R-C 不越线） |
| ii（难度分档） | 同 i | 同 i | 流式在途 **且** 本卡召集成员任务 ≥2 在工作态；单任务流式落中速 3.6s（现行观感） | 四档（含中速）；以成员任务计数作「难」的确定性代理（计数信号，非模型自评） |
| iii（队列敏感） | 同 i | 工作态 ≥1 | 流式在途 或 queued≥1（排队积压升高速） | 把队列积压纳入；queued 语义偏「等待」而非「运转」，观感有歧义风险 |

分落点绑定（Q4 裁）：

| 落点 | 绑定候选 | 说明 |
|---|---|---|
| 侧栏 brand 30px | A=只绑全局任务态（静止/慢速两档，liveFeed 已有数据，零新链路）；B=三档全绑（流式信号需从 GuidePage 提升为模块级单例，~20 行 store） | A 最稳；B 表达力全但多一个共享信号源 |
| hero 38px | 仅空态展示=恒静态（空态无信号，诚实地板）；进入会话 hero 即消失 | 建议不绑 |
| 消息 ai-mark 26px | 沿用现行 `m.streaming` 绑定 → 高速（或方案 ii 下的中速） | 现行行为已在线上，观感连续 |
| 登录门 | 未登录无任务信号=恒静态；是否进标识（替换/共存于工牌氛围位）随 Q5 | B2 口径工牌=氛围非标识 |
| favicon | **建议保持静态**（乙/丙形态同源换图 + 修 `:2` 虚标注释）；动态 favicon=canvas 逐帧重绘，性能/噪音成本不值，如要=单独裁 | 换图不动 clay 语义 |

## 五、红线与纪律对照（逐条自查）

- 信任色锁五槽：三案全 clay `#c15f3c` 单色 + 中性暖阶，零新增色；旋转=活性与「clay=正在发生」同源。✓
- 诚实地板：静止档零残动；尾迹/高速只绑真实在途信号，信号消失回落。✓
- MOTION-SYSTEM 六条：动画只 transform/opacity；reduced-motion=静态（每稿自带媒体查询块 + 预览模拟开关，
  真实 `reduced_motion="reduce"` 上下文实测：点高速 currentTime 恒 0）；换档 ramp=瞬时 rAF（<0.5s 自清理，
  硬约束⑤瞬时例外同型）；常驻旋转=WAAPI transform 动画（合成层驱动，不占主线程 rAF 循环——单页常驻 rAF
  预算零新增，互审 F3 澄清）；零第三方依赖（CSS/WAAPI 原生）。✓
- e2e 契约：本票零产品代码，选择器/DOM 零触碰。✓
- 折叠保 DOM / #51 词表 / 双名制 / 「二所」副标：不触碰。✓
- favicon：换图不动 clay 语义；不动工牌氛围位定性。✓

## 六、给 owner 的逐项选择题（HITL 不代答）

- **Q1 形态**：甲（原花提速，形态零变化、工作量最小）/ 乙（SVG 涡轮重绘，轴孔毂读出「转轴」、favicon 可同源、PNG 退役净省 ~10 KB）/ 丙（乙形态+高速尾迹，三档形态差异最大）；
  丙可拆「乙先行、尾迹后补」两阶段。
- **Q2 档位速度**：静止 0 / 慢速 8s / 高速 1.4s（候选值，可微调）；是否保留中速 3.6s 档（随 Q3-ii）。
- **Q3 信号映射**：i（最简三档）/ ii（难度分档，成员任务数≥2 代理「难」）/ iii（队列敏感）。
- **Q4 侧栏 brand 绑定**：A（全局任务态两档，零新链路）/ B（三档全绑，流式信号提升模块级）。
- **Q5 落点范围**：侧栏+hero+ai-mark（现行三位）外——登录门进不进标识？favicon 同源静态换图做不做（含虚标注释修正）？
- **Q6 换档过渡**：WAAPI 缓启缓停 ~0.4s（预览稿演示版）/ 直切。

### 定稿结果（owner 2026-08-06 逐项交互裁，#61 票内留痕）

- **Q1=甲（原花提速）**：flai-bloom.png 保留，仅把单档扩成三档；乙/丙稿留档不施工。
- **Q2=静止 0 / 慢速 8s/圈 / 高速 1.4s/圈**；不设中速档。
- **Q3=i（最简三档）**：≥1 任务在 TASK_WORK_STATES 或 queued → 慢速；本会话请求在途（sending/流式）→ 高速；无信号 → 静止。
- **Q4=A（侧栏全局两档）**：侧栏 brand 只绑全局任务态（静止/慢速），liveFeed 已有数据零新链路；高速只在会话内落点出现。
- **Q5a=登录门进静态花瓣标识**（恒静态，未登录无信号；工牌插画氛围位定性不动）。
- **Q5b=favicon 花瓣重绘**（Q1=甲无 SVG 源图，施工时以花瓣出图；`favicon.svg:2` 虚标注释随施工修正；clay 语义不动）。
- **Q6=直切（CSS animation-duration 切换）**：不用 WAAPI ramp；换档瞬间相位跳变接受。

## 七、验证记录与证据边界

- 截图（`docs/reviews/map46-61-turbine-shots/`）：overview-idle/slow/fast（三案×三档定帧）、
  overview-fast-frame1/2（高速两帧连拍，相位差=动态实证，字节级不同已核）、overview-reduced
  （模拟降级=静态）、scheme-a/b/c 整页、scheme-b-reduced-real（真实 reduced-motion 上下文：
  点高速 currentTime 恒 0、gear 回落 idle，Playwright 实证）。
- 预览稿素材全内联（PNG base64/SVG 直写，互审 F4 后零仓库相对路径），任意位置 `file://` 可开、
  零依赖、零网络；reduced-motion 静态兜底双通道（JS 停转 + CSS `!important` 硬停，互审 F2）。
  截图用本机 Playwright chromium 148。
- bundle 数字为本 worktree（=origin/main @ cffbef5）实测，非 CI 摘录。
- **边界**：未起全栈体验栈（静态预览足以承载设计裁决）；SVG 描稿为底版非终稿（施工票精修+
  逐尺寸/暗色目检）；Windows 低真机未验（M4 线已有挂账同型）；方案丙残影参数（-20°/-40°、.22/.10）
  为候选初值，定稿时可调。
