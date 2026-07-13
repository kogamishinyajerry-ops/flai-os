# cfd_solve_launch tamper 咬合实证（2026-07-13）

对象：`tools_impl/cfd_solve_launch/adapter.py`（allow_shell_command 安全边界）。
方法：逐一注伤 → 跑 `tools_impl/cfd_solve_launch/tests/` → 必红 → md5 byte-identical
还原（`b07feef1f3acbc023b9e5609c43a5f41`）→ 全绿（8 passed）。

| # | 注伤 | 咬合测试 | 结果 |
|---|------|----------|------|
| ① | 铺算例前注入 `docker exec … rm -rf` 清旧 run（违反 bind-mount 铁律） | `test_never_deletes_anything` | RED ✓ |
| ② | `_RUN_ID_RE.match` 改恒真（放行目录穿越） | `test_run_id_traversal_rejected` | RED ✓ |
| ②b | `_CASE_WHITELIST` 检查改恒真（放行注入 case） | `test_case_whitelist_only` | RED ✓ |
| ③ | config 三元检查改恒真（绕过 fail-closed） | `test_config_missing_fail_closed` | RED ✓ |

## 过程发现（tamper 的真实价值）

首轮 tamper② **没咬**：原 `test_run_id_traversal_rejected` 只断言
`status=="failed"`，正则被绕过后测试靠「后续步骤碰巧失败」（未 mock 的真
docker mesh 步失败）仍然通过——通过路径错误，且入参非法路径真触了 subprocess。

修正（提交内测试即修后版）：入参拒绝类测试统一 `_forbid_subprocess`
（任何 subprocess 调用直接 AssertionError——拒绝必须先于拼路径/执行）+
断言 `error_message` 指明具体拒绝原因 + traversal case 断言 case_root
零路径副作用。修后重放 tamper②/②b 均必咬。

教训（对齐 canon「假绿是唯一死罪」）：fail-closed 测试只断言 failed 不够，
必须钉死**失败原因**与**零副作用**，否则 tamper 可被任意后续失败冒充。
