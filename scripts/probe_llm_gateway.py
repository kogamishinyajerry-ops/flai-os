"""M4 内网首日 LLM 协议探针：只打印原始观测，不写模型调用记录。"""

from __future__ import annotations

import os

import httpx

REQUIRED_ENV_VARS = (
    "FLAI_LLM_BASE_URL",
    "FLAI_LLM_API_KEY",
    "FLAI_LLM_MODEL_REASONING",
)
OBSERVATION_FOOTER = "以上为原始观测；是否符合 OpenAI 兼容协议由人判断"


def _print_unobserved_response(exc: Exception) -> None:
    print("HTTP status：未观测")
    print("Content-Type：未观测")
    print("body 前 500 字符：未观测")
    print("JSON 可解析?：未观测")
    print("有无 choices[0].message.content：未观测")
    print("有无 usage 字段：未观测")
    print(f"请求异常类型：{type(exc).__name__}")
    print(OBSERVATION_FOOTER)


def main() -> int:
    values = {name: os.environ.get(name) for name in REQUIRED_ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        print("缺少以下环境变量：")
        for name in missing:
            print(f"- {name}")
        return 2

    fast_model = os.environ.get("FLAI_LLM_MODEL_FAST")
    endpoint = f"{values['FLAI_LLM_BASE_URL'].rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {values['FLAI_LLM_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": values["FLAI_LLM_MODEL_REASONING"],
        "messages": [{"role": "user", "content": "ping"}],
    }

    print(f"FLAI_LLM_MODEL_FAST 是否设置：{bool(fast_model)}")
    try:
        response = httpx.post(endpoint, headers=headers, json=payload, timeout=15.0)
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        _print_unobserved_response(exc)
        return 1

    body_prefix = response.text[:500]
    try:
        decoded = response.json()
        json_parseable = True
    except ValueError:
        decoded = None
        json_parseable = False

    has_content = (
        isinstance(decoded, dict)
        and isinstance(decoded.get("choices"), list)
        and len(decoded["choices"]) > 0
        and isinstance(decoded["choices"][0], dict)
        and isinstance(decoded["choices"][0].get("message"), dict)
        and "content" in decoded["choices"][0]["message"]
    )
    has_usage = isinstance(decoded, dict) and "usage" in decoded

    print(f"HTTP status：{response.status_code}")
    print(f"Content-Type：{response.headers.get('Content-Type', '未提供')}")
    print("body 前 500 字符：")
    print(body_prefix)
    print(f"JSON 可解析?：{json_parseable}")
    print(f"有无 choices[0].message.content：{has_content}")
    print(f"有无 usage 字段：{has_usage}")
    print(OBSERVATION_FOOTER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
