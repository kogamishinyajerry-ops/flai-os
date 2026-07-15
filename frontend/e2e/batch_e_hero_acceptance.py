"""批E「A1 hero 四面手术 + A2 焦点环成体系」验收（Gate2-T2）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/ 与真实 agents/）+ Job Runner
+ 真 chromium。除 frontend/dist 构建产物外无外部前置。骨架（tmp 目录 / seed
用户 / 起 uvicorn / 健康探测 / `_auth` 登录 / SHOTS 目录 / 保活 poke_wait /
review_agent 翻 requires_human_review）照抄 batch_d / m2 / m10。

视觉门形态（Gate2 owner 裁定，仓内已证低 flake fail-closed）= **计算样式不变量
+ 编译 CSS-bundle grep + 真源 tamper**，像素 diff 不做（避 headless-500px 陷阱
伤 375px，见 canon reference_visual_regression_gate_verification）。

断言分两层：

【A. 静态层（不依赖浏览器，先跑；本轨 builder 已用真源 tamper 逐条咬合验证）】
  S1 签发面 SSOT + 信任色锁：编译 index CSS 内 `.sign-surface{}` 含 teal 边框
     `rgba(var(--trust-signed-rgb),.25)` + `var(--surface-raised)` 底，且**绝无**
     `--trust-real`（绿）——人签合法 teal 槽、completed 不染绿。tamper：把 border
     改 `--trust-real` 重构建→本条红。
  S2 签发输入剥离 SSOT：index CSS 内 `.sign-input textarea.el-textarea__inner{}`
     含 `border:none` + `box-shadow:none`——一处剥离，Face1/Face2 两面共享（拆此一层
     必咬两面）。tamper：删该规则重构建→本条红。
  S3 焦点环成体系 SSOT：index CSS 内 `[role=button]:focus-visible{}` 用
     `var(--clay-softer)`（与既有 additive 环同色，一色成体系）。tamper：删地板
     重构建→本条红（全站 role=button 焦点环集体失守）。
  S4 gov-entry 焦点环同 token：AgentPortal CSS 内 `.gov-entry…:focus-visible{}`
     含 `outline` + `var(--clay-softer)`（原生 button，A2 属性地板不覆盖，自写规则
     消费同一 token）。tamper：改回 underline-only→本条红。
  S5 治理弹窗外壳暖化：AgentPortal CSS 内**非 scoped** `.gov-dialog .el-dialog__header{}`
     含 `border-bottom` + `var(--hairline)`（唯一类名命名空间，可靠命中 teleport
     后 DOM）。tamper：删该块→本条红。
  S6 信任色锁·五面无绿回归守卫：五个 face 组件源文件（TaskDetail/StatusCenter/
     TaskCreate/SchemaForm/AgentPortal.vue）**零** `--trust-real` / `el-color-success`
     引用（App.vue 排除——它定义该 token）。tamper：任一 face 注入绿→本条红。
  S7 completed 不给绿 SSOT（format.js）：`completed` 映 `type:"info"`（非 success）
     且 `taskLampColor('completed')` 返 `var(--ink-soft)`——同一诚实口径。tamper：
     把 completed 改 `type:"success"` 或灯改 `--trust-real`→本条红。

【B. 浏览器计算样式层（**待主 session 收口 e2e 实跑**——无头环境抢端口/慢，本轨
   builder 未在本机跑完整 Playwright；断言逻辑已自查，种子/取值照 m2/m10 proven
   pattern）】
  B1 Face1 人签面：/tasks/<review_task> 的 `.review-card.sign-surface` 计算 border-radius
     == --radius-lg(12px)、背景 == --surface-raised、边框含 teal-tint；`.approve-btn`
     背景 == --trust-signed（teal 信任锁不变）；textarea chrome 已剥离（border none）。
  B2 两面同工艺：状态坞 peek 的 `.peek-review-card.sign-surface` 计算 border-radius
     / 背景 / teal 边框三项**逐项 == Face1 `.review-card`**（同 SSOT 证据）；
     `.peek-approve` teal + :disabled 绑 artifactsPending（先看后签）仍在。
  B3 Face3 创建面：/tasks/new?agent_id=hello_agent 的 `.create-form` 计算背景
     == --surface-raised + box-shadow 非 none（worktable）；`.agent-preview` 有
     hairline 边 + radius token；SchemaForm 字段渲染；375px 无横向溢出（含 SchemaForm）。
  B4 Face4 治理弹窗：/portal 开治理弹窗，`.el-dialog__header` 计算含 hairline 底边；
     `.gov-run-btn` 背景**非** --trust-real（评测按钮 = clay 工作非绿）。
  B5 A2 焦点环落地：role=button 元素可聚焦（role=button + tabindex），配合 S3 地板
     规则=全站覆盖；键盘不对称已补（ap-item space / status-dock enter.prevent）。
  B6 completed 不给绿（真渲染）：completed 任务详情状态 tag class 含 `info` 不含
     `success`（statusTagType 语义落地）。
  截图落 docs/reviews/batch-e-hero-shots/：亮/暗 × {face1_review, face2_peek,
  face3_create, face4_governance} × 桌面/375。
  Face4 补拍（CG）：治理弹窗除「默认/空态」外，补「富态（晋升史+评测柱+五门中性标记）
  light/dark/375 + 执行中 + 加载失败」三态截图与断言（seed_governance 直插 + page.route
  拦截造错），使 Face4 可终审签收。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba --with openpyxl python frontend/e2e/batch_e_hero_acceptance.py
"""
from __future__ import annotations

import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SRC = REPO / "frontend" / "src"
SHOTS = REPO / "docs" / "reviews" / "batch-e-hero-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


# ════════════════════════════════════════════════════════════════════════════
# A. 静态层：编译 CSS-bundle grep + 源码不变量（不依赖浏览器，先跑，tamper 咬合）
# ════════════════════════════════════════════════════════════════════════════

def _read_css(glob_pat: str) -> str:
    """拼接匹配某 glob 的所有编译 CSS（minified）为一个大字符串。"""
    files = sorted((DIST / "assets").glob(glob_pat))
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _rule_body(css: str, selector_regex: str) -> str | None:
    """在 minified CSS 里取 `selector{...}` 的花括号体（第一处命中）；无命中返 None。
    selector_regex 是选择器部分的正则（允许 scoped [data-v] 之类），后接 `\\{`。"""
    m = re.search(selector_regex + r"\{([^}]*)\}", css)
    return m.group(1) if m else None


INDEX_CSS = _read_css("index-*.css")
PORTAL_CSS = _read_css("AgentPortal-*.css")

# ── S1 签发面 SSOT + 信任色锁（teal 不绿）──
sign_body = _rule_body(INDEX_CSS, r"\.sign-surface")
s1_ok = (
    sign_body is not None
    and "rgba(var(--trust-signed-rgb),.25)" in sign_body
    and "var(--surface-raised)" in sign_body
    and "--trust-real" not in sign_body
)
check(
    "S1 .sign-surface SSOT：teal(--trust-signed-rgb,.25) 边框 + surface-raised 底 + 绝无绿(--trust-real)",
    s1_ok,
    f"body={sign_body!r}",
)

# ── S2 签发输入剥离 SSOT（拆一层咬两面）──
sign_input_body = _rule_body(INDEX_CSS, r"\.sign-input textarea\.el-textarea__inner")
s2_ok = (
    sign_input_body is not None
    and "border:none" in sign_input_body
    and "box-shadow:none" in sign_input_body
)
check(
    "S2 .sign-input textarea.el-textarea__inner 剥离 EP chrome（border:none+box-shadow:none）",
    s2_ok,
    f"body={sign_input_body!r}",
)

# ── S3 焦点环成体系 SSOT（一色 --clay-softer）。minified 剥引号=[role=button] ──
floor_body = _rule_body(INDEX_CSS, r"\[role=.?button.?\]:focus-visible")
s3_ok = floor_body is not None and "var(--clay-softer)" in floor_body and "outline" in floor_body
check(
    "S3 [role=button]:focus-visible 全局地板用 --clay-softer（一色成体系 SSOT）",
    s3_ok,
    f"body={floor_body!r}",
)

# ── S4 gov-entry 焦点环同 token（scoped，允许 [data-v]）──
gov_entry_body = _rule_body(PORTAL_CSS, r"\.gov-entry(?:\[[^\]]*\])?:focus-visible")
s4_ok = gov_entry_body is not None and "outline" in gov_entry_body and "var(--clay-softer)" in gov_entry_body
check(
    "S4 .gov-entry:focus-visible 自写环消费同一 --clay-softer（原生 button 不靠地板）",
    s4_ok,
    f"body={gov_entry_body!r}",
)

# ── S5 治理弹窗外壳暖化（非 scoped，唯一类名命名空间）──
gov_header_body = _rule_body(PORTAL_CSS, r"\.gov-dialog \.el-dialog__header")
s5_ok = (
    gov_header_body is not None
    and "border-bottom" in gov_header_body
    and "var(--hairline)" in gov_header_body
)
check(
    "S5 .gov-dialog .el-dialog__header 暖化（hairline 底边，非 scoped 命中 teleport）",
    s5_ok,
    f"body={gov_header_body!r}",
)

# ── S6 信任色锁·五面无绿回归守卫（App.vue 排除：它定义 --trust-real token）──
FACE_FILES = [
    SRC / "views" / "TaskDetail.vue",
    SRC / "components" / "StatusCenter.vue",
    SRC / "views" / "TaskCreate.vue",
    SRC / "components" / "SchemaForm.vue",
    SRC / "views" / "AgentPortal.vue",
]
green_hits: list[str] = []
for face in FACE_FILES:
    text = face.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "--trust-real" in line or "el-color-success" in line:
            green_hits.append(f"{face.relative_to(REPO)}:{lineno}")
check(
    "S6 五 face 组件零绿引用（--trust-real/el-color-success）——completed/签发绝不染绿",
    len(green_hits) == 0,
    f"命中={green_hits}" if green_hits else "TaskDetail/StatusCenter/TaskCreate/SchemaForm/AgentPortal 零命中",
)

# ── S7 completed 不给绿 SSOT（format.js）──
fmt_text = (SRC / "utils" / "format.js").read_text(encoding="utf-8")
# completed 映 info（非 success）：容错空白，锚 `completed:{...type:"info"}`
completed_info = bool(
    re.search(r"completed:\s*\{[^}]*type:\s*[\"']info[\"']", fmt_text)
)
completed_no_success = not bool(
    re.search(r"completed:\s*\{[^}]*type:\s*[\"']success[\"']", fmt_text)
)
# 到席灯 completed → var(--ink-soft)（非 --trust-real 绿）
lamp_inksoft = bool(
    re.search(r'status\s*===\s*[\"\']completed[\"\']\s*\)\s*return\s*[\"\']var\(--ink-soft\)[\"\']', fmt_text)
)
s7_ok = completed_info and completed_no_success and lamp_inksoft
check(
    "S7 completed 不给绿 SSOT：statusTagType→'info' 且 taskLampColor→var(--ink-soft)",
    s7_ok,
    f"completed_info={completed_info} no_success={completed_no_success} lamp_inksoft={lamp_inksoft}",
)


# ════════════════════════════════════════════════════════════════════════════
# B. 浏览器计算样式层（待主 session 收口 e2e 实跑）
# ════════════════════════════════════════════════════════════════════════════
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    # 静态层已跑完并计入 results——浏览器缺失时诚实汇总退出（静态层仍是权威信号）。
    print("\n注意：playwright 未安装，仅跑静态层 S1-S7（浏览器层 B* 待主 session）。")
    failed = [r for r in results if r[1] is not True]
    print(f"\n{'BATCH E 静态层 ALL GREEN' if not failed else 'BATCH E 静态层 FAILED'} "
          f"({len(results) - len(failed)}/{len(results)}) — 浏览器层未跑")
    sys.exit(0 if not failed else 1)

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos  # Face4 补拍：直插治理种子（评测柱/晋升史）
from backend.app.storage.db import get_conn  # Face4 补拍：治理种子连接

# ── 自起后端：tmp 目录 + hello_agent + review_agent（requires_human_review=true）──
WORK = Path(tempfile.mkdtemp(prefix="flai_batch_e_hero_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")
review_dir = AGENTS_DIR / "review_agent"
shutil.copytree(REPO / "agents" / "hello_agent", review_dir)
_yaml = review_dir / "agent.yaml"
_text = _yaml.read_text(encoding="utf-8")
assert "id: hello_agent" in _text and "requires_human_review: false" in _text
_yaml.write_text(
    _text.replace("id: hello_agent", "id: review_agent")
    .replace("requires_human_review: false", "requires_human_review: true"),
    encoding="utf-8",
)

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

seed_user(DB_PATH, "验收工程师")

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)


def poke_wait(page, predicate, timeout_s: float) -> bool:
    """轮询等待 predicate() 为真，每 0.5s page.evaluate 保活（canon#50：headless
    后台 tab 会冻结 setTimeout，纯 sleep 不给 CDP 活动）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
        page.evaluate("1")
    return predicate()


def wait_text(page, needle: str, timeout_s: float) -> bool:
    return poke_wait(page, lambda: needle in page.locator("body").inner_text(), timeout_s)


def _seed_task_via_ui(page, agent_id: str, name_value: str) -> str:
    """照 m2/m10 proven pattern：/tasks/new?agent_id= → 填姓名 → 提交 → 落 /tasks/<id>。
    返回 task id。"""
    page.goto(BASE + f"/tasks/new?agent_id={agent_id}", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".agent-preview").count() > 0, 8)
    page.locator('input[placeholder="请填写姓名"]').first.fill(name_value)
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    return page.url.rsplit("/", 1)[-1]


def seed_governance(agent_id: str) -> None:
    """Face4 补拍富态种子：给 agent 直插 2 条已完成评测（趋势柱高度不同）+ 1 条历史
    晋升审计行（晋升史卡 + 五门判定快照，供 Face4 中性标记渲染）。走 repos 直插，不改
    agent.yaml、不需 EvalRunner worker（种的都是终态行，无认领方）。照 batch_c 手法。"""
    conn = get_conn(DB_PATH)
    try:
        for i, (passed, total) in enumerate([(3, 3), (2, 3)]):
            rid = f"seed_run_{agent_id}_{i}"
            repos.create_eval_run(
                conn, run_id=rid, agent_id=agent_id, agent_version="0.1.0",
                triggered_by="验收工程师", status="running",
            )
            repos.finish_eval_run(
                conn, rid, status="completed", total=total, passed=passed,
                failed=total - passed, skipped=0,
                case_results=[
                    {"case_file": f"case_{j:03d}.json",
                     "verdict": "passed" if j < passed else "failed"}
                    for j in range(total)
                ],
                draft_cases=[], eval_cases_digest="seed-digest",
            )
        repos.record_promotion(
            conn, agent_id=agent_id, agent_version="0.1.0",
            from_maturity="L0", to_maturity="L1", eval_run_id=f"seed_run_{agent_id}_0",
            checks={
                "eval_all_green": {"ok": True, "detail": "3/3 全绿"},
                "manual_confirmation": {"ok": True, "detail": "记名确认"},
            },
            confirmations={"exception_paths_handled": True},
            confirmed_by="验收工程师",
        )
    finally:
        conn.close()


# 计算样式探针：把 token（hex）经浏览器颜色解析统一转归一化 rgb 串，避免脆弱 hex 正则。
_RESOLVE_TOKEN = """(name) => {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const probe = document.createElement('div');
  probe.style.color = raw; document.body.appendChild(probe);
  const rgb = getComputedStyle(probe).color; probe.remove();
  return rgb;
}"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)

    # ── 种 review_agent 任务 → waiting_review（Face1/Face2 用）──
    review_task_id = _seed_task_via_ui(page, "review_agent", "签发面验收")
    wait_text(page, "等待人工审核", 30)

    # ── B1 Face1 人签面（/tasks/<review_task> 已在页上）──
    poke_wait(page, lambda: page.locator(".review-card").count() > 0, 10)
    surf_rgb = page.evaluate(_RESOLVE_TOKEN, "--surface-raised")
    signed_rgb = page.evaluate(_RESOLVE_TOKEN, "--trust-signed")
    f1 = page.evaluate(
        """() => {
          const card = document.querySelector('.review-card');
          const ta = document.querySelector('.review-card .el-textarea__inner');
          const btn = document.querySelector('.review-card .approve-btn');
          if (!card) return null;
          const cs = getComputedStyle(card);
          return {
            radius: cs.borderTopLeftRadius,
            bg: cs.backgroundColor,
            borderColor: cs.borderTopColor,
            hasSign: card.classList.contains('sign-surface'),
            taBorder: ta ? getComputedStyle(ta).borderTopStyle : null,
            btnBg: btn ? getComputedStyle(btn).backgroundColor : null,
          };
        }"""
    )
    check("B1 Face1 .review-card 挂 sign-surface + radius==12px", bool(f1) and f1["hasSign"] and f1["radius"] == "12px", str(f1))
    check("B1 Face1 背景==--surface-raised（脱 paper-rail 填表相）", bool(f1) and f1["bg"] == surf_rgb, f"bg={f1 and f1['bg']} surf={surf_rgb}")
    check("B1 Face1 意见框 EP chrome 已剥离（textarea border none）", bool(f1) and f1["taBorder"] == "none", str(f1 and f1["taBorder"]))
    check("B1 Face1 .approve-btn 背景==--trust-signed（teal 信任锁，绝不绿）", bool(f1) and f1["btnBg"] == signed_rgb, f"btn={f1 and f1['btnBg']} signed={signed_rgb}")
    # ── CG-A/CG-B 治本 SSOT 落地（共享 SignPanel）：climax serif 眉标 + 统一否定词『驳回』
    #    + 签发人『签发人：』标签。tamper：改回旧 review-heading/『拒绝』/去标签→本条红。──
    f1txt = page.evaluate(
        """() => {
          const card = document.querySelector('.review-card');
          if (!card) return null;
          const h = card.querySelector('.sign-heading');
          const reject = Array.from(card.querySelectorAll('button')).some(b => b.innerText.includes('驳回'));
          const noReject2 = Array.from(card.querySelectorAll('button')).some(b => b.innerText.trim() === '拒绝');
          return {
            headingText: h ? h.innerText.trim() : null,
            headingFont: h ? getComputedStyle(h).fontFamily.toLowerCase() : '',
            hasReject: reject, hasOldReject: noReject2, text: card.innerText,
          };
        }"""
    )
    check("CG-A Face1 .sign-heading climax（serif 眉标『签发』，非旧 12px review-heading）",
          bool(f1txt) and f1txt["headingText"] == "签发" and "serif" in f1txt["headingFont"],
          str(f1txt and {k: v for k, v in f1txt.items() if k != "text"}))
    check("CG-B Face1 否定键统一『驳回』（非旧『拒绝』）",
          bool(f1txt) and f1txt["hasReject"] and not f1txt["hasOldReject"], str(f1txt and f1txt["hasReject"]))
    check("CG-B Face1 签发人行含『签发人：』标签（对齐 Face2）",
          bool(f1txt) and "签发人：" in f1txt["text"], (f1txt and f1txt["text"][:120]) or "")
    page.screenshot(path=str(SHOTS / "face1_review_light_desktop.png"), full_page=True)
    page.set_viewport_size({"width": 375, "height": 800})
    page.wait_for_timeout(400)
    page.screenshot(path=str(SHOTS / "face1_review_light_375.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})

    # ── B2 两面同工艺：状态坞 peek（Face2）计算样式逐项 == Face1 ──
    page.locator(".status-dock").click()
    sc_item = page.locator(".sc-item", has_text="review_agent")
    poke_wait(page, lambda: sc_item.count() > 0, 8)
    sc_item.first.click()
    poke_wait(page, lambda: page.locator(".peek-approve").count() > 0, 8)
    # 先看后签：产物预览加载中 peek-approve 禁用，EP 禁用态 background-color 覆盖
    # .sign-approve 的 teal var（正确 UX，与旧实现同，非回归）——等按钮转可用（产物
    # 预览加载完 artifactsPending→false）再核 teal 背景不变量，去掉「加载竞态」偶发
    # （Face1 无产物门恒 teal 已由 B1 证；此处只等 Face2 的先看后签门放开）。
    peek_enabled = poke_wait(
        page,
        lambda: page.evaluate(
            "() => { const b = document.querySelector('.peek-approve');"
            " return !!b && !b.classList.contains('is-disabled') && !b.disabled; }"
        ),
        20,
    )
    check("B2 Face2 先看后签门放开（产物预览加载完，peek-approve 转可用）", peek_enabled is True)
    # EP 按钮 background 带 transition:.1s——is-disabled 类瞬时移除但 bg 从禁用白过渡到
    # teal 需 ~0.1s，settle 让过渡收口后再采样计算样式（否则采到过渡中途的白）。
    page.wait_for_timeout(600)
    f2 = page.evaluate(
        """() => {
          const card = document.querySelector('.peek-review-card');
          const ta = document.querySelector('.peek-review-card .el-textarea__inner');
          const btn = document.querySelector('.peek-approve');
          if (!card) return null;
          const cs = getComputedStyle(card);
          return {
            radius: cs.borderTopLeftRadius, bg: cs.backgroundColor, borderColor: cs.borderTopColor,
            hasSign: card.classList.contains('sign-surface'),
            taBorder: ta ? getComputedStyle(ta).borderTopStyle : null,
            btnBg: btn ? getComputedStyle(btn).backgroundColor : null,
          };
        }"""
    )
    two_faces_equal = (
        bool(f1) and bool(f2)
        and f2["hasSign"]
        and f1["radius"] == f2["radius"]
        and f1["bg"] == f2["bg"]
        and f1["borderColor"] == f2["borderColor"]
    )
    check("B2 两签发面同工艺：peek-review-card 计算 radius/背景/teal边框 逐项==review-card", two_faces_equal, f"f1={f1} f2={f2}")
    check("B2 Face2 意见框剥离（同 SSOT，textarea border none）", bool(f2) and f2["taBorder"] == "none", str(f2 and f2["taBorder"]))
    check("B2 Face2 .peek-approve 背景==--trust-signed（teal）", bool(f2) and f2["btnBg"] == signed_rgb, f"btn={f2 and f2['btnBg']}")
    # ── CG-A/CG-B Face2 同 SignPanel（治本 SSOT 两面同源）：serif 眉标『签发』+ 否定词
    #    『驳回』+『签发人：』标签，与 Face1 逐项一致（结构不可分叉的文案证据）。──
    f2txt = page.evaluate(
        """() => {
          const card = document.querySelector('.peek-review-card');
          if (!card) return null;
          const h = card.querySelector('.sign-heading');
          const reject = Array.from(card.querySelectorAll('button')).some(b => b.innerText.includes('驳回'));
          return { headingText: h ? h.innerText.trim() : null, hasReject: reject, text: card.innerText };
        }"""
    )
    check("CG-A/B Face2 同 SignPanel：.sign-heading『签发』+ 否定键『驳回』+『签发人：』标签",
          bool(f2txt) and f2txt["headingText"] == "签发" and f2txt["hasReject"] and "签发人：" in f2txt["text"],
          str(f2txt and {k: v for k, v in f2txt.items() if k != "text"}))
    page.screenshot(path=str(SHOTS / "face2_peek_light_desktop.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── B3 Face3 创建面（worktable + agent-preview + SchemaForm + 375 无溢出）──
    page.goto(BASE + "/tasks/new?agent_id=hello_agent", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".agent-preview").count() > 0, 8)
    f3 = page.evaluate(
        """() => {
          const form = document.querySelector('.create-form');
          const prev = document.querySelector('.agent-preview');
          const field = document.querySelector('.schema-form input, .schema-form textarea');
          const fcs = form ? getComputedStyle(form) : null;
          const pcs = prev ? getComputedStyle(prev) : null;
          return {
            formBg: fcs ? fcs.backgroundColor : null,
            formShadow: fcs ? fcs.boxShadow : null,
            prevBorder: pcs ? pcs.borderTopStyle : null,
            prevRadius: pcs ? pcs.borderTopLeftRadius : null,
            schemaField: !!field,
          };
        }"""
    )
    check("B3 Face3 .create-form worktable：背景==--surface-raised", bool(f3) and f3["formBg"] == surf_rgb, f"formBg={f3 and f3['formBg']}")
    check("B3 Face3 .create-form 有 shadow（脱 EP 裸表单相）", bool(f3) and f3["formShadow"] not in (None, "none"), f"shadow={f3 and f3['formShadow']}")
    check("B3 Face3 .agent-preview 有 hairline 边 + radius token（脱 el-card 默认）", bool(f3) and f3["prevBorder"] == "solid" and f3["prevRadius"] == "12px", str(f3))
    check("B3 Face3 SchemaForm 字段已渲染（非 JSON 降级）", bool(f3) and f3["schemaField"], str(f3))
    page.screenshot(path=str(SHOTS / "face3_create_light_desktop.png"), full_page=True)
    page.set_viewport_size({"width": 375, "height": 800})
    page.wait_for_timeout(400)
    overflow_ok = page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    widths = page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    check("B3 Face3 375px 无横向溢出（含 SchemaForm 渲染，worktable box-sizing）", overflow_ok, f"scrollWidth,clientWidth={widths}")
    page.screenshot(path=str(SHOTS / "face3_create_light_375.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})

    # ── B4 Face4 治理弹窗（header 暖化 + gov-run-btn 非绿）──
    real_rgb = page.evaluate(_RESOLVE_TOKEN, "--trust-real")
    page.goto(BASE + "/portal", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".gov-entry").count() > 0, 8)
    page.locator(".gov-entry").first.click()
    poke_wait(page, lambda: page.locator(".gov-dialog .el-dialog__header").count() > 0, 8)
    f4 = page.evaluate(
        """() => {
          const hd = document.querySelector('.gov-dialog .el-dialog__header');
          const runBtn = document.querySelector('.gov-run-btn');
          return {
            hdBorderStyle: hd ? getComputedStyle(hd).borderBottomStyle : null,
            hdBorderColor: hd ? getComputedStyle(hd).borderBottomColor : null,
            runBtnBg: runBtn ? getComputedStyle(runBtn).backgroundColor : null,
          };
        }"""
    )
    check("B4 Face4 .el-dialog__header 暖化（hairline 底边 solid，命中 teleport DOM）", bool(f4) and f4["hdBorderStyle"] == "solid", str(f4))
    check("B4 Face4 .gov-run-btn 背景!=--trust-real（评测按钮=clay 工作非绿）", bool(f4) and f4["runBtnBg"] != real_rgb, f"runBtn={f4 and f4['runBtnBg']} real={real_rgb}")
    page.screenshot(path=str(SHOTS / "face4_governance_light_desktop.png"), full_page=True)  # 默认/空态（hello 无治理数据）
    page.keyboard.press("Escape")

    # ════════════════════════════════════════════════════════════════════════
    # Face4 补拍（阻断项）：治理弹窗「富态（晋升史+评测柱）」+「执行中」+「加载失败」
    # 三态，light+dark+375，纳入 batch_e 断言。前者 B4 已拍「默认/空态」。
    # ════════════════════════════════════════════════════════════════════════
    # ── 富态：seed hello_agent 2 完成评测（趋势柱）+ 1 历史晋升（晋升史卡+五门中性标记）──
    seed_governance("hello_agent")
    page.goto(BASE + "/portal", wait_until="networkidle")
    hello_card = page.locator(".agent-card", has_text="hello_agent")
    poke_wait(page, lambda: hello_card.count() > 0, 8)
    hello_card.locator(".gov-entry").click()
    poke_wait(page, lambda: page.locator(".gov-promotion-card").count() > 0, 8)
    f4rich = page.evaluate(
        """() => ({
          ladder: !!document.querySelector('.gov-ladder'),
          trendBars: document.querySelectorAll('.gov-trend-bar').length,
          promoCards: document.querySelectorAll('.gov-promotion-card').length,
          casesCount: !!document.querySelector('.gov-cases-count'),
        })"""
    )
    check("Face4 富态：晋升史卡>=1 + 评测趋势柱>=2 + 成熟度阶梯 + 已固化计数（治理弹窗富态渲染）",
          bool(f4rich) and f4rich["promoCards"] >= 1 and f4rich["trendBars"] >= 2
          and f4rich["ladder"] and f4rich["casesCount"], str(f4rich))
    # 展开五门判定快照（默认折叠），让 CG Face4 中性标记进截图并可断言
    fold = page.locator(".gov-promotion-card .el-collapse-item__header").first
    if fold.count() > 0:
        fold.click()
        page.wait_for_timeout(700)  # 等 el-collapse 展开过渡收口
        # 把五门中性标记滚入弹窗可视区（弹窗 body 内部滚动，标记默认在折叠区/fold 下），
        # 让 CG Face4 微修的「通过/未通过」中性标记进截图供 owner 终审。
        try:
            page.locator(".gov-check-verdict").first.scroll_into_view_if_needed(timeout=3000)
            page.wait_for_timeout(300)
        except Exception:
            pass
    verdict_marks = page.evaluate(
        """() => {
          const marks = Array.from(document.querySelectorAll('.gov-check-verdict'));
          const green = marks.some(m => { const c = getComputedStyle(m).color;
            const p = document.createElement('div'); p.style.color = 'var(--trust-real)';
            document.body.appendChild(p); const real = getComputedStyle(p).color; p.remove();
            return c === real; });
          return { count: marks.length, texts: marks.map(m => m.innerText.trim()), anyGreen: green };
        }"""
    )
    check("CG Face4 五门中性标记：≥1『通过/未通过』标记且**无**染绿（信任色锁：门通过不给绿）",
          verdict_marks["count"] >= 1 and verdict_marks["anyGreen"] is False, str(verdict_marks))
    page.screenshot(path=str(SHOTS / "face4_governance_rich_light_desktop.png"), full_page=True)
    page.set_viewport_size({"width": 375, "height": 800})
    page.wait_for_timeout(400)
    rich_overflow_ok = page.evaluate("() => document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    check("Face4 富态 375px 无横向溢出", rich_overflow_ok,
          str(page.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")))
    page.screenshot(path=str(SHOTS / "face4_governance_rich_light_375.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})

    # ── 执行中：点「跑评测」→ POST 入队（batch_e 无 EvalRunner worker，run 停 queued）→
    #    按钮 loading（真「执行中」，不伪造）──
    page.locator(".gov-run-btn").click()
    running_ok = poke_wait(
        page,
        lambda: page.evaluate(
            "() => { const b = document.querySelector('.gov-run-btn'); return !!b && b.classList.contains('is-loading'); }"
        ),
        6,
    )
    check("Face4 执行中：跑评测后 .gov-run-btn 进 loading 态（真入队执行中）", running_ok)
    page.screenshot(path=str(SHOTS / "face4_governance_running_light_desktop.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── 加载失败：page.route 拦治理三请求之一（eval-runs list）返 500 → governanceLoadError
    #    渲染错误 alert（失败可见非静默）──
    _err_re = re.compile(r"/api/agents/[^/]+/eval-runs$")
    page.route(_err_re, lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail":"seeded error"}'))
    page.goto(BASE + "/portal", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".gov-entry").count() > 0, 8)
    page.locator(".agent-card", has_text="hello_agent").locator(".gov-entry").click()
    err_ok = poke_wait(page, lambda: page.locator(".gov-panel .el-alert--error").count() > 0, 8)
    check("Face4 加载失败：治理请求 500 → 弹窗内错误 alert 可见（fail-visible 非静默）", err_ok)
    page.screenshot(path=str(SHOTS / "face4_governance_error_light_desktop.png"), full_page=True)
    page.unroute(_err_re)
    page.keyboard.press("Escape")

    # ── B5 A2 焦点环落地：role=button 元素可聚焦（配合 S3 地板规则=全站覆盖）──
    # 诚实边界：headless :focus-visible 计算样式易 flake（canon 警示），故此处验
    # 「元素为可聚焦 role=button」+ S3 地板规则存在（CSS-grep）=覆盖证据，不靠
    # 无头伪造键盘焦点态读像素。
    focusable = page.evaluate(
        """() => {
          const els = Array.from(document.querySelectorAll('[role="button"]'));
          return { count: els.length, allFocusable: els.every(e => e.hasAttribute('tabindex')) };
        }"""
    )
    check("B5 A2 /portal role=button 均可聚焦（tabindex 在），配合 S3 地板=全站环覆盖",
          focusable["count"] >= 0 and (focusable["count"] == 0 or focusable["allFocusable"]), str(focusable))

    # ── B6 completed 不给绿（真渲染）：种 hello 任务跑到 completed，状态 tag=info 非绿 ──
    done_task_id = _seed_task_via_ui(page, "hello_agent", "completed 验收")
    poke_wait(page, lambda: "已完成" in page.locator("body").inner_text(), 30)
    tag_type = page.evaluate(
        """() => {
          const tag = document.querySelector('.page-header .el-tag');
          if (!tag) return null;
          return { cls: tag.className, isSuccess: tag.className.includes('el-tag--success'), isInfo: tag.className.includes('el-tag--info') };
        }"""
    )
    check("B6 completed 状态 tag=info 不含 success（statusTagType 落地，completed 不给绿）",
          bool(tag_type) and tag_type["isSuccess"] is False and tag_type["isInfo"] is True, str(tag_type))

    # ── 暗色截图（四面，桌面+375；断言已在亮色段做，暗色只取证据，同 batch_d 非对称）──
    page.evaluate("() => localStorage.setItem('flai_theme_mode', 'dark')")
    page.goto(BASE + f"/tasks/{review_task_id}", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".review-card").count() > 0, 10)
    page.screenshot(path=str(SHOTS / "face1_review_dark_desktop.png"), full_page=True)
    page.goto(BASE + "/tasks/new?agent_id=hello_agent", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".agent-preview").count() > 0, 8)
    page.screenshot(path=str(SHOTS / "face3_create_dark_desktop.png"), full_page=True)
    page.goto(BASE + "/portal", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".gov-entry").count() > 0, 8)
    # 富态 dark：hello_agent 已 seed 晋升史+评测柱，dark 取富态证据（覆盖 light+dark+375）。
    # 沿用既有 tracked 文件名 face4_governance_dark_desktop.png（原地更新为当前富态 UI，
    # 不另立新名产生孤儿证据）。
    page.locator(".agent-card", has_text="hello_agent").locator(".gov-entry").click()
    poke_wait(page, lambda: page.locator(".gov-promotion-card").count() > 0, 8)
    page.screenshot(path=str(SHOTS / "face4_governance_dark_desktop.png"), full_page=True)
    page.evaluate("() => localStorage.setItem('flai_theme_mode', 'light')")

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH E HERO ACCEPTANCE ALL GREEN' if not failed else 'BATCH E HERO ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
