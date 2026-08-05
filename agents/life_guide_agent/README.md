# life_guide_agent

> 本体论教学 demo 的对话入口 agent。**这不是生产 Agent,是 L1 教学工具。**

## 这是什么

生活场景建模主持人。工程师讲一段真实生活经历(做饭/旅行/装修/训练),主持人在
同一对话里引导识别 Work Case、投影 Generalization,产出待审 Asset Candidate。

## 为什么有它

`guide_agent` 是工程任务的编排官(把需求路由到 cfd/fea/性能盘专家),**不产出
资产候选**。`AssetBuilderDrawer.vue` 是字段表单,ADR-0033 已判退役。

本体论建模需要一个"会话优先 + 投影候选"的入口——这就是 life_guide_agent。
详见 `docs/design/ONTOLOGY-MODELING-MULTI-AGENT.md` 的 L1 设计。

## 三个比喻(贯穿所有对话)

1. **老张审报告** = 人审唯一签发权(主持人只能投影候选,不能签发)
2. **妈妈菜谱方子 v3** = 内容寻址 digest(改一个字就不是同一张纸)
3. **装修队长工具箱** = 工具白名单 + fail-closed(不认识的东西默认拒绝)

## 边界(诚实边界)

- **不签发、不注册、不晋级**:只能投影候选,签发权在工程师手里
- **只处理生活场景**:工程任务走 guide_agent
- **Skill Package 进 quarantine 隔离区**:不进 agents/ Registry,不进
  reuse_eligible 全局复用池(避免污染生产池,见 fork-2 审查报告 R3)
- **demo 不证明 FDE 价值**:只证明本体论建模闭环可跑 + 工程师能看懂

## 跑法

```bash
cd /Users/Zhuanz/projects/aircraft-comac/flai-os-life-demo
python scripts/run_demo_scenario.py cooking   # 红烧肉 demo(待实现)
```

## 相关文件

- `agent.yaml` —— Agent Package 契约(domain=generic, profile=fast)
- `prompt.md` —— 主持人系统提示(三比喻 + 四步 + 铁律 + 输出格式)
- `workflow.py` —— run() 入口,调 AssetDraftBuilder.preview() 算 digest
- `input_schema.json` / `output_schema.json` —— IO 契约
