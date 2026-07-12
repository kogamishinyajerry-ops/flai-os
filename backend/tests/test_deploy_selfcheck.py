"""部署自检门探针单测（PM 战略审 top：模型网关配置检查 + 库身份 + worker 代际）。

只测纯函数/可注入 _http_get 的探针；全链实机三幕在 review-record（无 worker/
全 PASS/库指纹不符）。本文件保证 check_model_gateway_config 的 fail-closed 语义
进 verify_all 常驻 gate——否则「门探不到模型未配」这个修复本身会静默腐烂。
"""

from __future__ import annotations

import json

from scripts import deploy_selfcheck


def _fake_health(monkeypatch, payload: dict) -> None:
    def fake_get(url: str):
        return 200, json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(deploy_selfcheck, "_http_get", fake_get)


def test_model_gateway_config_pass_when_all_three_set(monkeypatch) -> None:
    _fake_health(monkeypatch, {
        "status": "ok",
        "llm_base_url_set": True,
        "llm_api_key_set": True,
        "llm_model_reasoning_set": True,
    })
    c = deploy_selfcheck.check_model_gateway_config("http://x")
    assert c.ok is True


def test_model_gateway_config_fails_when_any_missing(monkeypatch) -> None:
    for missing_key in ("llm_base_url_set", "llm_api_key_set", "llm_model_reasoning_set"):
        payload = {
            "status": "ok",
            "llm_base_url_set": True,
            "llm_api_key_set": True,
            "llm_model_reasoning_set": True,
        }
        payload[missing_key] = False
        _fake_health(monkeypatch, payload)
        c = deploy_selfcheck.check_model_gateway_config("http://x")
        assert c.ok is False, f"{missing_key}=False 必须 FAIL（否则门放行未配模型的假绿）"
        assert "503" in c.detail or "首条消息" in c.detail


def test_model_gateway_config_fails_when_flag_truthy_but_not_true(monkeypatch) -> None:
    """is True 纪律：布尔位是字符串 'true'/1 等 truthy 值也判 FAIL（不认 truthy）。"""
    _fake_health(monkeypatch, {
        "status": "ok",
        "llm_base_url_set": 1,
        "llm_api_key_set": "true",
        "llm_model_reasoning_set": True,
    })
    c = deploy_selfcheck.check_model_gateway_config("http://x")
    assert c.ok is False


def test_model_gateway_config_fails_when_health_unreachable(monkeypatch) -> None:
    def boom(url: str):
        raise OSError("connection refused")

    monkeypatch.setattr(deploy_selfcheck, "_http_get", boom)
    c = deploy_selfcheck.check_model_gateway_config("http://x")
    assert c.ok is False
