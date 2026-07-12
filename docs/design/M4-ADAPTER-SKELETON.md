# M4 真实性能盘 Adapter 接口骨架（占位设计，非定案）

> M11-C1 产物：让 M4 落地日只剩「填空」。**本骨架刻意不落 tools_impl/ 真实
> 包目录**——registry 会扫描注册，占位 tool 进白名单=污染。M4 侦察确认调用
> 形态后照此落地。所有「假设」段在 day1 侦察（docs/M4_intranet_day1_recon_
> checklist.md）中逐项证实/证伪后才转代码。

## 接缝对齐（与 mock 三件套等位替换）

真实 adapter 只替换 `performance_disk_mock` 一件；`excel_case_parser`（入）
与 `excel_summary_writer`（出）不动——它们对接的是平台侧 Excel 契约，与
性能盘无关。performance_disk_agent 的 workflow.py 只改 tools 白名单一行
（mock → real），批量语义/单 case 隔离/samples 沉淀全部复用。

```text
tools_impl/performance_disk_real/
  tool.yaml          # id: performance_disk_real；mock: false；版本从 0.1.0
  adapter.py         # 见下方接口
  README.md          # 调用形态/环境依赖/超时口径（侦察后填）
  eval_cases/        # 至少：正常 case + 超包线 case + 工具不可用 case
```

## adapter.py 接口（与 mock 同签名，运行时零改）

```python
def run(payload: dict) -> dict:
    """payload: {"case_id": str, "inputs": {altitude_m, mach, power_kw, ...}}

    返回（与 mock 契约逐字段等位，消费方 workflow 不感知真假切换）：
      成功 {"status": "success", "outputs": {...按入参清单定}, "mock": False}
      失败 {"status": "failed", "error_message": "<真实工具原话+分类>", "mock": False}

    纪律：
    - 超时必须有硬上限（侦察 Q：一次计算耗时量级），超时=failed 不挂死 worker；
    - 真实工具的 stdout/stderr 原样进 tool_runs 留痕，绝不清洗后冒充结构化；
    - 数值不做任何"合理性修正"——工具说什么就是什么，判断权在工程师。
    """
```

## 调用形态四分支（侦察后择一，其余删除）

| 形态 | 落地方式 | 风险预判 |
|---|---|---|
| CLI 可执行 | subprocess + 超时 + 工作目录隔离 | 中文路径/编码（GBK vs UTF-8） |
| COM/DLL | pywin32 仅 Windows 分支；平台侧加 sys.platform 门 | 许可证/单实例互斥 |
| Excel 宏 | 判否倾向：改走「生成输入册→人工跑→回传结果册」半自动流 | 全自动化不可行时的诚实降级 |
| 内部 HTTP 服务 | httpx 直连+重试；最理想形态 | 大概率不存在，别指望 |

## 已定的平台侧前置（不等侦察）

- 输入文件经 File Store 完整性闸消费（file_integrity 已建）；
- 任务超时/中断恢复：worker 启动恢复中断执行态已建（R4 批）；
- 数据分级标记轴（M11-B2）先行——真实样本落库当天就有 sensitive 标记可用。
