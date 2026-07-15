# asset_catalog —— 资产清单读取与确定性初筛

读 `data/assets/assets.yaml`(资产清单 SSOT,ADR-0028),两个 action:

- `list`:全量资产(评估外的盘点用途);
- `match`:需求文本对 keywords/capabilities 子串命中计分,`(-score, id)` 稳定
  排序取 top_k(缺省 6)——纯确定性,同输入必同输出,语义补漏是 Agent 层
  LLM 在候选集内的事。

fail-closed:清单缺失/YAML 畸形/字段缺失/status·kind 非法/id 重复 → `status=failed`
并给定位信息,绝不返回空清单冒充"没有资产"(「家底不可读」≠「家底为空」)。

`FLAI_ASSET_CATALOG_PATH` 环境变量可重定向清单路径(测试注入畸形样本用)。

维护清单的纪律见 assets.yaml 文件头注释:status 如实(宪法第五条)、
honest_note 写清「不能说成什么」、涉外供应商产品一律泛化表述。
