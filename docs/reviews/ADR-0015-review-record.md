# ADR-0015 Knowledge 内核服务（Wave 1）审查记录

> 收编 COMAC_FDE ingest/retrieve 为内核检索服务 + default-deny 三层门 + 共享装配。
> 本记录存档四道验证环的真实证据（宪法：声明 ≤ 证据；无档案=按零分计）。

## 验证环总览

| 环 | 执行者 | 裁决 | 处置 |
|---|---|---|---|
| 设计审（Mode A，实现前） | loop-auditor | FLAG 12/20，5 findings + d9 | 全部落地（下详） |
| lane 自证 | 4 实现 lane | 各自 witness 全绿 + 单点 tamper | 主控逐一亲跑复验 + golden 反编造抽检 |
| 收口 tamper（T1-T7） | 主控 | 全部咬合 | 下详 |
| 异源反方审（fresh-context） | 敌意审查 agent | **APPROVE，P1/P2/P3 零 findings** | 观察 c（负 top_k）已顺手修复+witness |
| 收口复测（Mode C） | loop-auditor | BLOCK→d5 未提交/审查缺档 | commit 885d92f + 本文件处置 |
| 复验（Mode C 终裁） | loop-auditor | **APPROVE 19/20 🟢闭环成熟** | d4 1→2（异源审有文件级证据）、d5 0→2（SHA 锚定+远程同步）；审计员独立 worktree 重跑验证计数链（58f8755=318 passed、4709d30 纯净=324+66=390）逐位自洽 |
| Codex 异源治理审 | — | **悬置**：codex 二进制 2026-07-09 起损坏（M7 已记环境债） | 恢复后补跑 `codex review --commit <本次 SHA>` |

## Mode A findings 处置

1. **F1 双装配路径漂移**（main.py 与 runner 各自手写 scan+sync）→ `backend/app/bootstrap.py`
   共享 `assemble()`（scan→scope scan→reconcile→sync_to_db 顺序钉死一处）；双路径
   witness = `backend/tests/test_knowledge_bootstrap.py`（含「deregister 先于 sync_to_db」
   的 DB 层 witness）。Mode C 独立 tamper（monkeypatch reconcile 为 no-op）实证真咬。
2. **F2 收口 tamper 无场景清单** → T1-T7 清单执行（下节）+ 本存档。
3. **F3 「出处由构造保证」过强** → `Chunk.__post_init__` + `KnowledgeHit.__post_init__`
   非空校验落到类型层；docstring 明注「防漏填/空串，不防恶意伪造」。
4. **F4 密级门边界声明不足** → ADR-0015 决策 4 + docs/06 §3 + README #17②：
   「visibility 在 V0.1 运行时未被任何端点强制，只约束注册期声明一致性」。
5. **F5 interactive 挂载点缺失未声明** → ADR-0015 后果节 + README #17①：Wave 1 仅
   job 模式，interactive 需另立 ADR。
6. **d9 oracle 维护** → golden 再生成脚本入仓 `backend/tests/gen_bm25_golden.py`
   （记录 jieba 0.42.1；语料字面量与测试逐字同源）。

## 收口 tamper 记录（隔离 worktree，逐条 revert→红→restore→绿）

| # | 篡改 | 结果（精确身份） |
|---|---|---|
| T1 | `_KnowledgeContext.search` 白名单检查 → `if False` | e2e 越权 witness 1 failed（3 中恰 1）；还原 3 passed |
| T2 | 密级门 restricted 放行 department_trial | 恰 3 红：`test_gate_restricted_denies_department_trial` + bootstrap 双路径两 witness；还原绿 |
| T3 | reconcile 未注册 scope 检查置空 | 恰 2 红：scopes reconcile witness + e2e violator witness；还原绿 |
| T4 | scope.yaml 密级活改（restricted↔public_internal） | 双向翻转：restricted 下 violator 拒注册（记录 1 条）→改 public 后现身（0 条）→证明门读活真值非缓存 |
| T5 | 绕过 context 直调 KnowledgeService | 在场边界 witness（test_knowledge_service.py:242 区）：直调成功=信任边界如 docstring 宣称，白名单只在 context 层 |
| T6 | 路径逃逸门 → `if False` | 恰 1 红：`test_resolve_relative_escape_rejected`（逃逸目标真实存在，排除存在性门背锅）；还原绿 |
| T7 | `Chunk.__post_init__` 置空 | 恰 1 红：空出处 witness；还原绿 |

lane 侧另有 4 组自证 tamper（utf-8-sig 剥离/epsilon 地板/逃逸门/缓存判据+出处四钥），
各 lane 报告中有红绿计数，主控亲跑复验其测试文件全绿。

## 异源反方审（fresh-context，补偿 codex 悬置）

- 裁决 **APPROVE，零 findings**。独立执行 4 组 tamper（密级门 return None／逃逸门
  `if False`／bm25 eps 改 clamp-0／运行时白名单 `if False`），各自 witness 精确变红后复原。
- golden 独立重生成：`rank-bm25==0.2.2` 真跑输出与冻结常量逐位一致（G1 1.282790/
  1.863115/0.655176；G2 [-0.434865,-0.471962]；G3 1.721739）。
- 越权面排查：API 面/conversation 面/workflow 可达对象/симlink 摊平（resolve 后
  is_relative_to）全封闭；path_or_uri_env 不做逃逸检查=部署方信任边界内的既定设计。
- 事故披露与复核：审查中曾误 `git checkout` 回退未提交的 runtime.py 后按 diff 重建；
  主控以事故前已知良品副本逐字节 diff 确认无损。
- 三条非阻塞观察：a) 混入不支持格式整 scope 拒检索（既定 fail-closed，README #17⑤）；
  b) env 路线无逃逸检查（既定信任边界）；c) 负 top_k 负切片——**已修**：`top_k<1`
  显式 ValueError + witness（test_search_rejects_nonpositive_top_k）。

## 测试证据（全部真跑）

- 基线（改动前，HEAD=58f8755 全仓）：318 passed。
- 隔离 worktree（HEAD+仅本次改动）：383 passed → HEAD=4709d30 重验 390 passed。
- 主工作区（含 M8 在途未提交改动）：Mode C 审计员独立跑 398 passed / 0 failed。
- 并发归因存档：开发期间主工作区曾现 6 个 m6/m7 红——三点 worktree 实验
  （纯 HEAD 绿 / HEAD+M8 未提交 guide 文件恰 6 红 / HEAD+仅本次改动全绿）证明
  属 M8 编排官化在途改动（后随 4709d30 提交自愈），与本次改动无关。

## 残差（显式标注）

- Codex 异源治理审悬置（二进制损坏），恢复后补跑；反方 fresh-context 审为补偿。
- 真实语料/业务价值未验证：本地仅合成语料，DECLARED-NOT-VERIFIED 纪律不变，
  卡 EAR/M4 内网闸门。
- 调用期主体鉴权不存在（V0.1 全局无鉴权，README #14/#17②）；restricted 真语料
  上内网前鉴权层是硬前置。
