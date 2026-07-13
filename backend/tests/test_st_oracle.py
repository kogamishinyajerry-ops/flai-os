"""st_oracle 校准测试：对充分发展的 good-run-01 golden（t=150）验证
确定性 Strouhal / Cd 计算落在 agent-cfd-live 实测 St≈0.16734 量级，
且未起振/数据不足时不编造 St（Goodhart 防御）。

自足：用 FLAi-OS 侧 parser + 本仓 golden 夹具，零跨仓依赖。
"""
from pathlib import Path

from backend.app.cfd.st_oracle import strouhal_from_cl, cd_mean_tail
from backend.app.cfd.cfd_log_parser import parse_force_coeffs

GOLDEN = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cfd_good_run"
          / "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat")


def _load():
    fc = parse_force_coeffs(GOLDEN.read_text(errors="replace"))
    return fc["t"], fc["cl"], fc["cd"]


def test_strouhal_matches_williamson_band():
    t, cl, cd = _load()
    r = strouhal_from_cl(t, cl, D=1.0, U=1.0)
    assert r["converged"] is True
    assert r["n_cycles"] >= 3
    # agent-cfd-live 实测 0.16734；容差覆盖 zero-crossing 法与 FFT 法的量级差
    assert 0.15 < r["st"] < 0.185, f"St 偏离量级：{r['st']}"


def test_cd_mean_matches_band():
    t, cl, cd = _load()
    assert 1.0 < cd_mean_tail(cd) < 1.8


def test_flat_cl_not_converged_no_fake_st():
    # 未起振（常值 Cl，>=20 点绕过样本门）→ 不得编造 St（Goodhart 防御）
    r = strouhal_from_cl(list(range(30)), [0.5] * 30)
    assert r["converged"] is False
    assert r["st"] is None


def test_too_few_samples_not_converged():
    r = strouhal_from_cl([0.0, 1.0, 2.0, 3.0], [0.5, 0.5, 0.5, 0.5])
    assert r["converged"] is False
    assert r["st"] is None
