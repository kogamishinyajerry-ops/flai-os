"""performance_disk_mock 适配器（mock=true，诚实标注，宪法第五条）。

**本文件的全部公式是纯虚构的代数函数**：常数为随手挑的整数，不来自任何
真实性能盘程序/手册/试验数据，输出无任何工程意义——存在的唯一目的是给
平台批量调用链路一个确定性（同输入必同输出）的假负载。M4 用 mock=false
的真实工具包替换（切换 tool id，绝不原地翻牌本包的 mock 字段，docs/03 §3）。

失败注入（README/tool.yaml 已声明）：altitude_m > 15000 → status=failed
「超出 mock 包线」——这是刻意内置的单 case 失败路径，供批量 Agent 的
容错逻辑与测试使用；15000 这个数字同样是虚构的，不对应任何真实包线。
"""

from __future__ import annotations

from typing import Any

_MOCK_ENVELOPE_ALTITUDE_M = 15000.0


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context  # V0.1 未用
    params = payload.get("params") or {}
    altitude_m = float(params["altitude_m"])
    mach = float(params["mach"])
    power_kw = float(params["power_kw"])
    bleed = float(params.get("bleed_flow_kgps", 0.0))

    if altitude_m > _MOCK_ENVELOPE_ALTITUDE_M:
        return {
            "status": "failed",
            "mock": True,
            "error_message": (
                f"超出 mock 包线：altitude_m={altitude_m:g} > {_MOCK_ENVELOPE_ALTITUDE_M:g}"
                "（虚构包线，内置失败注入，见 README）"
            ),
        }

    # ↓↓↓ 纯虚构公式（deterministic：纯 params 代数，无随机/无时间依赖）↓↓↓
    shaft_power_kw = power_kw * (1.0 - 0.6 * altitude_m / 15000.0) * (1.0 + 0.25 * mach) - 5.0 * bleed
    fuel_flow_kgps = 0.00008 * max(shaft_power_kw, 0.0) + 0.005 * (1.0 + mach)
    egt_c = 380.0 + 0.03 * power_kw + 120.0 * mach - 0.004 * altitude_m + 2.0 * bleed
    # ↑↑↑ 以上常数均为随手虚构，与任何真实机器无关 ↑↑↑

    return {
        "status": "success",
        "mock": True,
        "outputs": {
            "shaft_power_kw": round(shaft_power_kw, 4),
            "fuel_flow_kgps": round(fuel_flow_kgps, 6),
            "egt_c": round(egt_c, 3),
        },
    }
