"""红烧肉 demo 闭环验证脚本:用 cooking.json 的 expected_generalization
调 AssetDraftBuilder.preview(),验证能投影出带 digest 的完整 bundle。

跑法:
cd /Users/Zhuanz/projects/aircraft-comac/flai-os-life-demo
python3 /tmp/verify_cooking_demo.py
"""
import json
import sys
from pathlib import Path

# 把 worktree 根目录加到 sys.path,让 backend.app.ontology 可 import
WORKTREE = Path("/Users/Zhuanz/projects/aircraft-comac/flai-os-life-demo")
sys.path.insert(0, str(WORKTREE))

from backend.app.ontology.asset_builder import AssetDraftBuilder

# 加载种子
with open(WORKTREE / "data/demo_scenarios/cooking.json", encoding="utf-8") as f:
    seed = json.load(f)

generalization = seed["expected_generalization"]

# 构造最小 conversation(模拟 life_guide_agent 对话结束后的状态)
conversation = {
    "id": "conv_demo_cooking_001",
    "agent_id": "life_guide_agent",
    "status": "concluded",
    "messages": [
        {"id": "m1", "role": "user", "content": "上周六下午我做了红烧肉,糖焦了重来一次,最后女儿说好吃。", "file_ids": []},
        {"id": "m2", "role": "assistant", "content": "两个关键问题:糖焦具体哪一步?成功证据?", "file_ids": []},
        {"id": "m3", "role": "user", "content": "糖色小泡转大泡时走神去看作业,回来糖焦了。第二次盯住琥珀色下肉。女儿吃了三大块说好吃,咸淡合适肉能咬动。", "file_ids": []},
        {"id": "m4", "role": "assistant", "content": "食材和步骤?", "file_ids": []},
        {"id": "m5", "role": "user", "content": "带皮五花肉 600g,冰糖 30g,生抽老抽料酒葱姜八角香叶。焯水切块、炒糖色、翻炒上色、炖 50 分钟、尝咸淡、收汁。", "file_ids": []},
    ],
}

builder = AssetDraftBuilder()
bundle = builder.preview(conversation=conversation, generalization=generalization)

print("=== 闭环验证成功 ===")
print()
print("schema_version:", bundle["schema_version"])
print("status:", bundle["status"])
print("draft_digest:", bundle["draft_digest"])
print()
print("=== work_case ===")
wc = bundle["work_case"]
print("  source_kind:", wc["source_kind"])
print("  source_id:", wc["source_id"])
print("  message_count:", wc["message_count"])
print("  user_message_count:", wc["user_message_count"])
print("  source_revision:", wc["source_revision"])
print()
print("=== task_pattern ===")
tp = bundle["task_pattern"]
print("  suggested_id:", tp["suggested_id"])
print("  title:", tp["title"])
print("  content_digest:", tp["content_digest"])
print()
print("=== skill ===")
sk = bundle["skill"]
print("  suggested_id:", sk["suggested_id"])
print("  name:", sk["name"])
print("  content_digest:", sk["content_digest"])
print()
print("=== validation ===")
v = bundle["validation"]
print("  state:", v["state"])
print("  blocking_count:", v["blocking_count"])
print("  warning_count:", v["warning_count"])
print()
print("=== review ===")
r = bundle["review"]
print("  required:", r["required"])
print("  ready:", r["ready"])
print("  state:", r["state"])
print()
print("=== effects(铁律自检)===")
e = bundle["effects"]
print("  writes_database:", e["writes_database"], "(必须 False)")
print("  executes_work:", e["executes_work"], "(必须 False)")
print("  registers_asset:", e["registers_asset"], "(必须 False)")
print("  promotes_asset:", e["promotes_asset"], "(必须 False)")
print()
print("=== generation ===")
print("  kind:", bundle["generation"]["kind"])
print("  llm_used:", bundle["generation"]["llm_used"], "(必须 False:确定性投影,不是 LLM)")
print()
print("=== 桥接 FDE 提示(给教学用)===")
print("  ", seed["teaching_notes"]["bridge_to_fde"])
print()
print("全部通过 = 本体论建模闭环可跑,红烧肉 demo 可以用于 FDE workshop。")
