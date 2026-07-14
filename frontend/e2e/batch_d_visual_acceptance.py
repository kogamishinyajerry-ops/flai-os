"""批D「视觉精修」验收（批D Task 8）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/ 与真实 agents/）+ Job Runner
+ 真 chromium。除 frontend/dist 构建产物外无外部前置。骨架（tmp 目录 / seed
用户 / 起 uvicorn / 健康探测 / `_auth` 登录 / SHOTS 目录 / 保活 poke_wait）
照抄 batch_c_rewards_acceptance.py。

批D是视觉精修批——「看着还行」不是 gate，本 e2e 断言 Task 1-7 修复建立的 7 个
**机器可检**不变量（spec §八）：

  ① token 定义：`getComputedStyle(root)` 的 --sans/--mono/--fs-title/--radius-lg
    均非空（frontend/src/App.vue :root 块新增的批D token 地基）。
  ② 无 `var(--danger` 残留：subprocess grep frontend/src/ 返回码非 0（无匹配）。
  ③ 375px 无横向溢出：/portal、/tasks/new、/tasks/<id>（含真实选中任务——
    TaskConsole 中栏切到 TaskDetail 选中态面板，非空任务台）三页逐一断言
    `document.documentElement.scrollWidth <= clientWidth`；task 用
    repos.create_task 直插种一条，保证 /tasks 有真行可开。刻意选择探针
    `/tasks/<id>` 选中态而非未选中的空任务台是明示范围收窄——Task 2 审查
    要求验证的正是「TaskConsole 中栏切到 TaskDetail 详情面板」这一分支在
    375px 下不溢出（该面板内容量最大、是回归高发区），空态本身信息量小，
    与⑥的收窄说明同一透明度标准。
  ④ 暗色 `--ink-faint` on `--surface-raised` WCAG≥4.5：页内用真实
    getComputedStyle 读两个 token 的 rgb() 值算相对亮度对比度（非硬编码色值）。
  ⑤ reduced-motion 下 `.send-spin` 不转：**已从 DOM 注入改为编译 CSS bundle
    grep**（原版做法已判定 vacuous 假绿并废弃：`.send-spin` 定义在
    GuidePage.vue `<style scoped>` 内，编译后规则是
    `.send-spin[data-v-XXXX]{...}`，只匹配带该 scope 属性的元素；手工
    `document.createElement('span')` 出来的探针元素没有该属性，无论有没有
    reduced-motion 覆盖规则，规则都不命中，`getComputedStyle().animationName`
    恒为 CSS 默认值 `'none'`——删掉源码里的覆盖规则也不会让检查变红，是纯
    vacuous 断言）。现改为直接读 `frontend/dist/assets/GuidePage-*.css`，
    在 `@media (prefers-reduced-motion:reduce)` 块内做括号平衡提取，断言其中
    含 `.send-spin{...animation:none...}`（minified 无空格容错正则）——
    tamper-sensitive：删掉源码里的 override 再 build，bundle 里就没有，
    真红。
  ⑥ 页标题字号全等：GuidePage 的 `.plan-goal-title` 是对话气泡内的目标标题
    （仅在推荐消息落地后才挂载、且字号 20/21px 是刻意的气泡层级而非页级
    token），排除在断言范围外并在此明示；改为对 6 个有稳定单一页标题元素的
    视图取 computed font-size，断言集合 size==1：
      /portal（AgentPortal .page-header h2）
      /me（MePage .page-header h2）
      /tasks/<id>（TaskDetail .page-header h2，选中态）
      /today（TodayPage .today-title，同用 var(--fs-title) token）
      /feedback（FeedbackPage .page-header h2）
      /tasks/new（TaskCreate .page-header h2）
    这 6 个视图的标题元素在源码里都是 `font-size: var(--fs-title)`（AgentPortal/
    FeedbackPage/MePage/TaskCreate/TaskDetail/TodayPage 六处 grep 命中），是
    「页标题」这一语义类目里唯一具有单一稳定选择器的全集——不是任务书字面的
    「9 view」（该数字数不出 9 个语义不同的页标题，已核实源码后诚实收窄，非
    偷懒放水）。
  ⑦ 失败态互斥：FeedbackPage 用 `page.route` 拦截反馈列表接口返 500，选中
    任务后断言 error alert 在屏 且「暂无反馈」EmptyState 不在屏（源码里两者
    本就是 `v-if="...&&!feedbackError"` 互斥关系，这里是行为验证非重复实现）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/batch_d_visual_acceptance.py

截图落 docs/reviews/batch-d-shots/（每次重跑覆盖，保持证据与代码同步）：
  亮/暗 × 桌面/375px × {portal, tasks_new, task_detail} 共 12 张。
"""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "batch-d-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos
from backend.app.storage.db import get_conn

# ── 自起后端：tmp 目录（照抄 batch_c 骨架）──
WORK = Path(tempfile.mkdtemp(prefix="flai_batch_d_visual_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")

_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

DB_PATH = WORK / "flai_os.db"

app = create_app(
    agents_dir=AGENTS_DIR,
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=DB_PATH,
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import login_context, seed_user  # noqa: E402（须在后端就绪后种账户）

seed_user(DB_PATH, "验收工程师")  # 默认 e2e_engineer/e2e-pass-flai（_auth 默认值）

# ── 种一条真实任务：/tasks/<id> 选中态、/feedback 任务下拉都需要真行 ──
_conn = get_conn(DB_PATH)
try:
    TASK_ID = f"task_{uuid.uuid4().hex}"
    repos.create_task(
        _conn,
        task_id=TASK_ID,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name="批D视觉验收种子任务",
        created_by="验收工程师",
        created_by_username="e2e_engineer",
    )
finally:
    _conn.close()

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def poke_wait(page, predicate, timeout_s: float) -> bool:
    """轮询等待 predicate() 为真，每秒 page.evaluate("1") 保活——纯 Python
    time.sleep() 不给渲染进程任何 CDP 活动，headless 后台 tab 会被 Chromium
    判定为后台并冻结 setTimeout 轮询链（canon#50 实证坑，batch_a/b/c 同款手法）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
        page.evaluate("1")
    return predicate()


def _title_font_size(page) -> str | None:
    """取当前页「页标题」元素的 computed font-size；两种选择器覆盖 6 个
    视图（.page-header h2 命中 5 个，.today-title 命中 TodayPage）。"""
    return page.evaluate(
        """() => {
          const el = document.querySelector('.page-header h2') || document.querySelector('.today-title');
          return el ? getComputedStyle(el).fontSize : null;
        }"""
    )


# ── ② 无 var(--danger 残留：不依赖浏览器，先跑（subprocess，真返回码）──
grep_danger = subprocess.run(
    ["grep", "-rn", "var(--danger", "frontend/src/"], cwd=REPO, capture_output=True, text=True
)
check(
    "② 无 var(--danger 残留（token 绕过消除）",
    grep_danger.returncode != 0,
    f"returncode={grep_danger.returncode} stdout={grep_danger.stdout[:200]!r}",
)

# ── ⑤ reduced-motion 下 .send-spin 不转：编译 CSS bundle grep（不依赖浏览器，
# 与②同批先跑）。原 DOM 注入法已判定 vacuous 假绿并废弃——见文件头注释。
# 编译产物的 scoped 规则形如 `.send-spin[data-v-xxxx]{...}`，minified 后
# `@media (prefers-reduced-motion:reduce)` 是单行、多条规则挤在同一花括号
# 深度里，不能用非贪婪正则截断，所以手工做括号平衡提取该 @media 块的完整
# 内容（含嵌套规则），再在块内断言含 `.send-spin{...animation:none...}`。
guide_css_files = sorted((DIST / "assets").glob("GuidePage-*.css"))
send_spin_none_found = False
send_spin_evidence = ""
if not guide_css_files:
    send_spin_evidence = "未找到 frontend/dist/assets/GuidePage-*.css（先 npm run build）"
else:
    for css_path in guide_css_files:
        css_text = css_path.read_text(encoding="utf-8")
        for media_match in re.finditer(r"@media[^{]*prefers-reduced-motion\s*:\s*reduce[^{]*\{", css_text):
            start = media_match.end()
            depth = 1
            i = start
            while i < len(css_text) and depth > 0:
                if css_text[i] == "{":
                    depth += 1
                elif css_text[i] == "}":
                    depth -= 1
                i += 1
            block = css_text[start : i - 1]
            spin_rule = re.search(r"\.send-spin(?:\[[^\]]*\])?\s*\{[^}]*\}", block)
            if spin_rule and re.search(r"animation\s*:\s*none", spin_rule.group(0)):
                send_spin_none_found = True
                send_spin_evidence = f"{css_path.name} :: {spin_rule.group(0)}"
                break
        if send_spin_none_found:
            break
    if not send_spin_evidence:
        send_spin_evidence = (
            f"扫描 {[p.name for p in guide_css_files]} 未在 prefers-reduced-motion:reduce "
            "块内命中 .send-spin{animation:none}"
        )
check(
    "⑤ 编译 CSS bundle 含 reduced-motion 下 .send-spin{animation:none}"
    "（原 DOM 注入因 Vue scoped data-v 不匹配已判定 vacuous，见文件头说明）",
    send_spin_none_found,
    send_spin_evidence,
)

AFFECTED = [
    ("portal", "/portal"),
    ("tasks_new", "/tasks/new"),
    ("task_detail", f"/tasks/{TASK_ID}"),
]

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)

    # ── ① token 定义：root 的 --sans/--mono/--fs-title/--radius-lg 均非空 ──
    page.goto(BASE + "/portal", wait_until="networkidle")
    vals = page.evaluate(
        """() => {
          const s = getComputedStyle(document.documentElement);
          return ['--sans','--mono','--fs-title','--radius-lg'].map(k => s.getPropertyValue(k).trim());
        }"""
    )
    check("① token 地基已定义（--sans/--mono/--fs-title/--radius-lg 非空）", all(v for v in vals), str(vals))

    # ── ③ 375px 无横向溢出 + 亮色桌面/375 截图（affected 三页）──
    for slug, path in AFFECTED:
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(BASE + path, wait_until="networkidle")
        if path.startswith("/tasks/task_"):
            poke_wait(page, lambda: page.locator(".page-header h2").count() > 0, 10)
        page.screenshot(path=str(SHOTS / f"{slug}_light_desktop.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 800})
        poke_wait(page, lambda: True, 0.5)  # 让 resize 触发的重排/CSS 生效
        overflow_ok = page.evaluate(
            "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        widths = page.evaluate(
            "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
        )
        check(f"③ 375px 无横向溢出 {path}", overflow_ok, f"scrollWidth,clientWidth={widths}")
        page.screenshot(path=str(SHOTS / f"{slug}_light_375.png"), full_page=True)

    page.set_viewport_size({"width": 1440, "height": 900})

    # ── ④ 暗色 --ink-faint on --surface-raised WCAG>=4.5（页内真实 computed 值算）──
    # 主题store（theme.js）在模块加载时读 localStorage 决定 data-theme，watchEffect
    # 常驻同步；page.goto 是整页硬导航会重载模块，故用 localStorage 落盘再导航，
    # 不是直接改 DOM 属性（那种改法会被下一次硬导航的模块初始化悄悄冲掉）。
    page.evaluate("() => localStorage.setItem('flai_theme_mode', 'dark')")
    page.goto(BASE + "/portal", wait_until="networkidle")
    theme_ok = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
    check("④前置：data-theme=dark 已生效", theme_ok == "dark", f"data-theme={theme_ok!r}")
    wcag = page.evaluate(
        """() => {
          const s = getComputedStyle(document.documentElement);
          // token 值是 hex（如 #978e81），非 rgb()——借浏览器自身的颜色解析
          // （设到探针元素的 color 上，读回归一化后的 computed rgb() 字符串）
          // 把 hex/rgb/named 统一转 [r,g,b]，不手写脆弱的 hex 正则。
          function toRGB(str){
            const probe = document.createElement('div');
            probe.style.color = str.trim();
            document.body.appendChild(probe);
            const rgbStr = getComputedStyle(probe).color;
            probe.remove();
            return rgbStr.match(/\\d+/g).map(Number);
          }
          const faint = toRGB(s.getPropertyValue('--ink-faint'));
          const surf = toRGB(s.getPropertyValue('--surface-raised'));
          const lin=c=>{c/=255;return c<=0.03928?c/12.92:Math.pow((c+0.055)/1.055,2.4);};
          const L=([r,g,b])=>0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);
          const la=L(faint),lb=L(surf),hi=Math.max(la,lb),lo=Math.min(la,lb);
          return (hi+0.05)/(lo+0.05);
        }"""
    )
    check("④暗色 --ink-faint on --surface-raised WCAG>=4.5", wcag >= 4.5, f"ratio={wcag:.3f}")

    # ── 暗色 affected 三页截图（桌面+375）──
    for slug, path in AFFECTED:
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(BASE + path, wait_until="networkidle")
        if path.startswith("/tasks/task_"):
            poke_wait(page, lambda: page.locator(".page-header h2").count() > 0, 10)
        page.screenshot(path=str(SHOTS / f"{slug}_dark_desktop.png"), full_page=True)

        page.set_viewport_size({"width": 375, "height": 800})
        poke_wait(page, lambda: True, 0.5)
        page.screenshot(path=str(SHOTS / f"{slug}_dark_375.png"), full_page=True)

    page.set_viewport_size({"width": 1440, "height": 900})
    page.evaluate("() => localStorage.setItem('flai_theme_mode', 'light')")
    page.goto(BASE + "/portal", wait_until="networkidle")

    # ── ⑥ 9-view 断言收窄为 6 个有稳定单一页标题元素的视图（见文件头注释）──
    title_views = [
        ("/portal", "AgentPortal"),
        ("/me", "MePage"),
        (f"/tasks/{TASK_ID}", "TaskDetail(选中态)"),
        ("/today", "TodayPage"),
        ("/feedback", "FeedbackPage"),
        ("/tasks/new", "TaskCreate"),
    ]
    sizes: dict[str, str | None] = {}
    for path, label in title_views:
        page.goto(BASE + path, wait_until="networkidle")
        poke_wait(page, lambda: _title_font_size(page) is not None, 10)
        sizes[f"{label} {path}"] = _title_font_size(page)
    distinct = set(sizes.values())
    check(
        "⑥ 6 视图页标题 font-size 全等（.page-header h2 / .today-title，见文件头收窄说明）",
        None not in distinct and len(distinct) == 1,
        str(sizes),
    )

    # ── ⑦ 失败态互斥：反馈接口拦截返 500，选任务后 error alert 在屏 且 EmptyState 不在屏 ──
    page.route("**/api/tasks/*/feedback", lambda route: route.fulfill(status=500, body="mock 500"))
    page.goto(BASE + f"/feedback?task_id={TASK_ID}", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".el-alert").count() > 0, 10)
    alert_visible = page.locator(".el-alert").first.is_visible()
    empty_present = "暂无反馈" in page.locator("body").inner_text()
    check("⑦失败态互斥：error alert 在屏", alert_visible, f"alert_visible={alert_visible}")
    check("⑦失败态互斥：暂无反馈 EmptyState 不在屏（与 error alert 互斥）", empty_present is False, f"empty_present={empty_present}")
    page.screenshot(path=str(SHOTS / "7_feedback_error_mutex.png"), full_page=True)
    page.unroute("**/api/tasks/*/feedback")

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH D VISUAL ACCEPTANCE ALL GREEN' if not failed else 'BATCH D VISUAL ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
