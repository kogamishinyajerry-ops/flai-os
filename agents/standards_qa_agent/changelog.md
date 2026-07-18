# standards_qa_agent 变更记录

## 0.1.1（2026-07-18）

- Codex 治理审 R1/R2/retro 修复：anyOf 拒 findings/refusals 双空；确定性目录白名单（条款/实例分轴）+ 双源宣称核形 + 规范展示形归一——
  越界出处整轮降级拒答，命中后 source_ref 归一重写为目录规范形（伪造注解不落库不上屏）。
- finish_reason 白名单：非 stop（length/content_filter 等）即便 JSON 可解析也降级拒答。
- 拒答 reason 改用校验器元数据（字段路径+约束名）构造，绝不引用被拒实例值；拒答
  payload 出门前自过 output_schema。
- 改动类型：workflow / schema。

## 0.1.0（2026-07-17）

- 初版：新增 standards_qa 专长、L1 有用性章程、standard_clause/type_case 双依据纪律与 internal 密级上限。
- 新增 interactive workflow；在 P0-N2 约束下不声明 tools，保持 knowledge.enabled=false。
- 新增 findings/refusals 输出契约、条款+机型实例双依据 case 与超范围拒答 case。
- 语料边界：仅含合成目录级索引，条款/实例正文未接入，所有依据 resolved=false。
- 改动类型：prompt / workflow / schema / eval / docs。
