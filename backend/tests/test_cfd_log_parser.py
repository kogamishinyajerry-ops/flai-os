"""FLAi-OS 侧 cfd_log_parser 负例（Codex R2-P2 两条）：
流式半写行不得撕裂 t/cd/cl 长度；发散 run 的 nan/inf 不得透传。
（正常路径由 test_st_oracle 的 golden 全链覆盖。）
"""
from backend.app.cfd.cfd_log_parser import parse_force_coeffs, parse_residuals

_HEADER = "# Time         \tCm             \tCd             \tCl             \n"


def test_partial_last_row_does_not_tear_lengths():
    # 模拟流式读到最后一行只写了一半（Cl 列 token 截断成非法 float）
    text = (_HEADER
            + "0.02\t0.001\t1.5\t0.10\n"
            + "0.04\t0.001\t1.4\t0.12\n"
            + "0.06\t0.001\t1.3\t0.1e")  # 半写 token
    fc = parse_force_coeffs(text)
    assert len(fc["t"]) == len(fc["cd"]) == len(fc["cl"]) == 2  # 半行整行丢弃，不撕裂


def test_nan_inf_rows_rejected():
    text = (_HEADER
            + "0.02\t0.001\t1.5\t0.10\n"
            + "0.04\t0.001\tnan\t0.12\n"
            + "0.06\t0.001\t1.3\tinf\n"
            + "0.08\t0.001\t1.2\t0.11\n")
    fc = parse_force_coeffs(text)
    assert fc["t"] == [0.02, 0.08]  # nan/inf 行整行拒
    assert all(v == v for v in fc["cd"] + fc["cl"])  # 无 NaN 透传（NaN != NaN）


def test_truncated_half_written_tokens_do_not_crash():
    # Codex R2-P2：solver 在写读方在读——末行可截断成 regex 能中但 float() 炸
    # 的半个数（`1e-`）。半写行按不完整跳过，绝不炸穿整次解析。
    text = ("Time = 1\n"
            "smoothSolver:  Solving for Ux, Initial residual = 0.001, ok\n"
            "Time = 2\n"
            "GAMG:  Solving for p, Initial residual = 1e-\n")
    steps = parse_residuals(text)
    assert len(steps) == 2
    assert steps[0]["resid"]["Ux"] == 0.001
    assert "p" not in steps[1]["resid"]  # 半写残差按缺失，不炸不编


def test_truncated_time_line_does_not_open_step():
    text = "Time = 1\nGAMG:  Solving for p, Initial residual = 0.01\nTime = 1e\n"
    steps = parse_residuals(text)
    assert len(steps) == 1
    assert steps[0]["resid"]["p"] == 0.01
