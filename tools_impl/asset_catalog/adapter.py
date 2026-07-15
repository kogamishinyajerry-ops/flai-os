"""asset_catalog 工具:资产清单读取 + 确定性关键词初筛(ADR-0028)。

设计边界:
- 纯确定性:子串命中计分 + (score 降序, id 字典序) 稳定排序——同输入必同
  输出。不分词、不做语义:中文无依赖分词器,子串匹配对短关键词(ECM/性能盘/
  故障树)足够;语义补漏是 Agent 层 LLM 在候选集内的事,不在本工具。
- fail-closed:清单文件缺失/YAML 畸形/顶层结构错/条目缺必填字段/status 或
  kind 非法 → status=failed 并给出定位信息。绝不返回空 assets 冒充"清单里
  没有资产"——「无法读到家底」和「家底里没有」是两个必须区分的事实
  (canon:fail-closed 于无法验证,而非仅验证到违规)。
- 清单路径:环境变量 FLAI_ASSET_CATALOG_PATH 优先(测试注入畸形样本用),
  缺省仓内 data/assets/assets.yaml。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG = _REPO_ROOT / "data" / "assets" / "assets.yaml"

_VALID_STATUS = frozenset({"live", "validated", "demo", "scaffold", "planned"})
_VALID_KIND = frozenset({"platform_agent", "external_project", "methodology"})
_REQUIRED_FIELDS = ("id", "name", "status", "kind", "keywords", "honest_note")

_DEFAULT_TOP_K = 6


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": message}


def _catalog_path() -> Path:
    override = os.environ.get("FLAI_ASSET_CATALOG_PATH")
    if override is not None and override.strip() != "":
        return Path(override)
    return _DEFAULT_CATALOG


def _load_catalog() -> tuple[dict[str, Any] | None, str | None]:
    """返回 (catalog, None) 或 (None, 错误信息)。所有校验集中在此。"""
    path = _catalog_path()
    if path.is_file() is False:
        return None, f"资产清单不存在:{path}(家底不可读≠家底为空,拒绝继续)"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # 畸形 YAML 定位到解析器原话
        return None, f"资产清单 YAML 解析失败:{exc}"
    if isinstance(raw, dict) is False:
        return None, "资产清单顶层必须是映射(version/updated/assets)"
    assets = raw.get("assets")
    if isinstance(assets, list) is False or len(assets) == 0:
        return None, "资产清单 assets 必须是非空列表"
    seen_ids: set[str] = set()
    for index, item in enumerate(assets):
        if isinstance(item, dict) is False:
            return None, f"资产条目 #{index} 不是映射"
        for field in _REQUIRED_FIELDS:
            value = item.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                return None, f"资产条目 #{index}(id={item.get('id', '?')})缺必填字段 {field}"
        if item["status"] not in _VALID_STATUS:
            return None, (
                f"资产 {item['id']} status 非法:{item['status']}"
                f"(合法值 {sorted(_VALID_STATUS)})"
            )
        if item["kind"] not in _VALID_KIND:
            return None, f"资产 {item['id']} kind 非法:{item['kind']}"
        if isinstance(item["keywords"], list) is False or len(item["keywords"]) == 0:
            return None, f"资产 {item['id']} keywords 必须是非空列表"
        if item["id"] in seen_ids:
            return None, f"资产 id 重复:{item['id']}"
        seen_ids.add(item["id"])
    return raw, None


def _public_fields(item: dict[str, Any]) -> dict[str, Any]:
    """透出给 Agent/评估卡的字段子集(与 tool.yaml output_schema 对齐)。"""
    return {
        "id": item["id"],
        "name": item["name"],
        "status": item["status"],
        "kind": item["kind"],
        "capabilities": list(item.get("capabilities", [])),
        "scenarios": str(item.get("scenarios", "")),
        "honest_note": item["honest_note"],
    }


def _match_one(text: str, item: dict[str, Any]) -> tuple[int, list[str]]:
    """确定性计分:keywords + capabilities 去重后逐个做子串命中,1 词 1 分。

    大小写归一(ECM/ecm 同词);命中词按原词序去重记录,供评估卡透出
    「为什么筛中」——初筛必须可解释,黑分数会让人工复核无从下手。
    """
    lowered = text.lower()
    matched: list[str] = []
    seen: set[str] = set()
    for word in list(item["keywords"]) + list(item.get("capabilities", [])):
        token = str(word).strip()
        key = token.lower()
        if token == "" or key in seen:
            continue
        seen.add(key)
        if key in lowered:
            matched.append(token)
    return len(matched), matched


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    action = payload.get("action")
    catalog, error = _load_catalog()
    if catalog is None:
        return _fail(error or "资产清单加载失败")

    assets: list[dict[str, Any]] = catalog["assets"]
    base = {
        "status": "success",
        "catalog_version": int(catalog.get("version", 0)),
        "catalog_updated": str(catalog.get("updated", "")),
    }

    if action == "list":
        return {**base, "assets": [_public_fields(a) for a in assets]}

    if action == "match":
        text = payload.get("text")
        if isinstance(text, str) is False or text.strip() == "":
            return _fail("match 需要非空 text")
        top_k_raw = payload.get("top_k", _DEFAULT_TOP_K)
        if isinstance(top_k_raw, bool) is True or isinstance(top_k_raw, int) is False:
            return _fail(f"top_k 必须是整数,收到 {top_k_raw!r}")
        top_k = top_k_raw
        scored: list[dict[str, Any]] = []
        for item in assets:
            score, matched = _match_one(text, item)
            if score > 0:
                entry = _public_fields(item)
                entry["score"] = score
                entry["matched_keywords"] = matched
                scored.append(entry)
        # 稳定确定性排序:分数降序,同分按 id 字典序(canon:order-dependent
        # 结果是隐形不可复现源,tie-break 必须显式)。
        scored.sort(key=lambda e: (-e["score"], e["id"]))
        return {**base, "assets": scored[:top_k]}

    return _fail(f"未知 action:{action!r}")
