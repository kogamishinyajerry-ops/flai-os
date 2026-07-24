# Kimi Workspace Shell V1 — Six-P1 Minimal Redispatch

## Frozen envelope

- Work item: `flai-workspace-shell-kimi-001@5`
- Work item digest: `${WORK_ITEM_DIGEST}`
- Human owner: `JerryKogami`
- Owner authorization: `批准 @5 最小重派`
- Rework lineage: `@1` candidate → `@2` read-scope stop → `@3` temp-write stop → `@4` execution-protocol stop → `@5`
- Frozen base: `47d191cb4799ec57f4739b4d1c709f490481fe77`
- Branch: `codex/kimi-workspace-shell-v5`
- Worktree: `/private/tmp/flai-kimi-workspace-shell-v5.QjU0x6`
- Environment: `EXTERNAL_DEVELOPMENT`
- Fixtures: `SYNTHETIC_ONLY`
- Internal data access: `NONE`
- Internal runtime dependency: `NONE`
- Result class: `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`

You are the bounded implementation executor. You are not a human reviewer, CODEOWNER, merge owner, release
signer, production authority, or source of trusted FLAi facts. Close exactly the six P1 findings below. Do not
redesign the shell, fix P2 smells, add features, integrate OpenHands/Open WebUI, or change production interfaces.

## Mandatory preflight

Before any source read or edit, run these direct foreground commands:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
test -d frontend/node_modules
test "${WORKSPACE_SHELL_SHOTS:-}" = "/private/tmp/flai-kimi-workspace-shell-v5-evidence.mGixLe"
test -d "${WORKSPACE_SHELL_SHOTS}"
test -z "$(find "${WORKSPACE_SHELL_SHOTS}" -mindepth 1 -maxdepth 1 -print -quit)"
```

Stop and return `BLOCKED` unless:

- cwd is `/private/tmp/flai-kimi-workspace-shell-v5.QjU0x6`;
- branch is `codex/kimi-workspace-shell-v5`;
- HEAD is exactly `47d191cb4799ec57f4739b4d1c709f490481fe77`;
- the worktree is clean;
- `frontend/node_modules` already exists;
- `WORKSPACE_SHELL_SHOTS` is exactly the repo-external path above and is empty.

This must be a fresh session. Never resume, inspect, or reuse:

```text
session_2f449268-89fd-4104-bd95-fd7bd908557e
session_f55a6882-e7cb-4c8a-b465-04d0bba4d950
session_8029f845-0add-4038-87fe-9543983100a5
session_05f51f4a-867f-4b3f-848f-8b5c92554b3a
```

Never read from, copy from, or write to any `@2`, `@3`, or `@4` worktree, evidence directory, skills directory,
dispatch log, or session path.

## Exhaustive source-context allowlist

Your `Read`, `Search`, `Glob`, `Grep`, `rg`, `sed`, `cat`, or equivalent source-inspection operations may access
only the six owned files and the following immutable read-only inputs:

```text
docs/agents/kimi-k3-workspace-shell-pilot.md
docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md
frontend/src/prototypes/stage-c/stage-c.css
frontend/src/prototypes/stage-c/StageCWorkbenchPrototype.vue
frontend/src/prototypes/stage-c/observer-contract.js
frontend/src/prototypes/workspace-shell/fixtures.js
frontend/workspace-shell.html
frontend/src/prototypes/workspace-shell/main.js
frontend/package.json
frontend/package-lock.json
frontend/vite.config.js
scripts/verify_all.sh
```

There is no transitive-read, “helpful context”, repo-wide search, or inferred-path exception. The two entry files
added in `@3` are read-only bootstrap inputs, never write targets. Approved test/build processes may perform their
normal transitive runtime reads, but you must not use those processes to reveal or inspect any other source file.
Do not read coordinator artifacts, environment files, secrets, credentials, internal data, external repositories,
OpenHands, Open WebUI, or external URLs.

Read every owned file and the following directly relevant inputs before editing:

```text
docs/agents/kimi-k3-workspace-shell-pilot.md
docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md
frontend/src/prototypes/stage-c/stage-c.css
frontend/src/prototypes/stage-c/StageCWorkbenchPrototype.vue
frontend/src/prototypes/stage-c/observer-contract.js
frontend/src/prototypes/workspace-shell/fixtures.js
frontend/workspace-shell.html
frontend/src/prototypes/workspace-shell/main.js
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
```

## Exclusive source-write scope

Modify only:

```text
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
```

Do not create any other repository source file.

## Verification-runtime write scope

The only non-source writes permitted to executor commands are:

- ignored build output under `frontend/dist/**`, produced solely by the required `npm run build`;
- screenshot evidence under `/private/tmp/flai-kimi-workspace-shell-v5-evidence.mGixLe/**`, produced solely by
  the required workspace-shell visual E2E;
- local Git index/object/ref metadata produced solely by the required `git add` and `git commit` operations for
  the six owned source files; advancing the current branch through those required commits is allowed, while Git
  configuration, push, merge, rebase, tag and branch-management create/delete/switch/reset remain denied;
- ignored Vite dependency cache under `frontend/node_modules/.vite/**`, produced solely by the required
  workspace-shell E2E's fixed-loopback Vite server.

The exact approved `npm run build` and offline Playwright/Vite/Chromium verification processes may create their
unavoidable tool-internal lock/cache/profile/temporary state. This is not an executor-authored output channel.
You must never name, enumerate, glob, stat, read, grep, tail, poll, copy, cite, or reuse:

- any path under `~/.kimi-code/sessions/**`;
- any `*/agents/*/tasks/**` path;
- any tool-reported `output.log` or equivalent private result file;
- `/private/tmp/flai-kimi-workspace-shell-v5-dispatch.jsonl`, which is coordinator-owned.

If a tool reports that a result is available only through a task id, a later poll, or a private path, return
`BLOCKED`; do not inspect it. The existing E2E script may internally use `subprocess.DEVNULL` to discard Vite
child-process output; `/dev/null` does not persist a result and is not permission for executor shell redirection.

All other direct file writes are denied. In particular:

- do not use `>`, `>>`, `tee`, output-file options, or shell/process substitution to persist test, build, audit,
  grep, diff, coverage, trace, or command output;
- do not create `/tmp` logs, scratch files, result files, caches, copied source, patches, reports, or helper
  scripts;
- keep test/build/audit result capture on the current tool call's direct stdout/stderr only;
- every unit, E2E, build, or audit/verification command must be invoked directly and unpiped;
- for those commands, `|`, `|&`, `2>&1`, `head`, `tail`, output filtering, and pipefail-based alternatives are
  all denied; use a narrower direct focused command when output would otherwise be too large.

The coordinator's external dispatch log is outside your tool authority and is not an executor write permission.

### Mandatory pre-red harness safety repair

The owned E2E currently evaluates `tempfile.mkdtemp(...)` as the eager default argument to
`os.environ.get("WORKSPACE_SHELL_SHOTS", ...)`, so it creates an unauthorized
`/tmp/workspace-shell-shots-*` directory even when the fixed environment variable is present.

After completing every mandatory read and before invoking any E2E command:

1. make only the minimal owned-file change that evaluates the `mkdtemp` fallback lazily, solely when
   `WORKSPACE_SHELL_SHOTS` is actually absent;
2. preserve the manual fallback for an environment where the variable is genuinely absent;
3. ensure this frozen run, where the variable is fixed, creates no extra `workspace-shell-shots-*` directory;
4. then continue the test-first sequence for the six P1s.

This is the only behavior repair permitted before the synchronous red gate. It is an authorized test-harness
safety repair inside the existing E2E write target, not a seventh product P1.

## Six exact P1 fixes

### P1-1 — URL contract

- Use only `reality=REAL|MOCK|TEST|UNKNOWN`.
- Do not support `form` as an alias.
- Missing, empty, mixed-case, or invalid `reality` fails closed to `UNKNOWN`.
- Every positive E2E URL explicitly includes a legal `reality`.
- Add E2E checks proving:
  - `?reality=MOCK` renders MOCK;
  - `?reality=FAKE`, `?reality=`, `?reality=mock`, missing `reality`, and `?form=MOCK` render UNKNOWN.

### P1-2 — frozen DOM contract

Expose these exact `data-testid` values in their applicable states:

```text
workspace-shell
workspace-rail
continuous-work-surface
focus-surface
workspace-composer
action-glyph
reality-badge
execution-state
instruction-queue
delivery-state
```

Keep additional existing interaction selectors only where needed. Add an E2E assertion that enumerates the exact
ten-value contract across appropriate states; check conditional queue and delivery nodes where they exist.

### P1-3 — locked trust colors and semantics

Define and preserve:

- clay work `#b4562f`;
- REAL green `#1e7d46`;
- human-sign teal `#0e7c7b`;
- true-failure red `#b3352c`;
- unverified amber `#986810`.

The synthetic prototype never renders REAL green or human-sign teal, but those tokens remain defined and
unborrowed. `data-trust` may use only `work`, `terminal`, `fail`, or `unverified`; terminal is neutral ink, not a
sixth trust color. Remove `active`, `attention`, and `synthetic` as trust-slot values.

Synthetic REAL/MOCK/TEST display forms use `data-slot="unverified"` and expose the form only through
`data-reality-form`. Running uses clay work; waiting_review is static clay work; completed/cancelled are neutral
terminal; failed/permission-denied are red fail; missing/invalid/UNKNOWN are amber unverified.

Add computed-style/DOM checks:

- running is exactly `rgb(180, 86, 47)`;
- failed is exactly `rgb(179, 53, 44)`;
- UNKNOWN is exactly `rgb(152, 104, 16)`;
- completed is neither green nor clay;
- no synthetic page contains `data-slot=real` or `data-slot=sign`.

### P1-4 — invalid history

- Raw fixture events may contribute history only after the observer projection accepts the entire event set.
- If `snapshot.mode === "unknown"`, history is empty.
- Rejected event title, object, digest, witness, preview and step must not leak.
- Unit tests traverse all 96 fixtures plus `stale`; every projected unknown case asserts zero history generically,
  without a state-name special case.
- E2E proves `observation-invalid` has zero history rows and does not contain
  `正在处理：气动周报-草稿.docx`.

### P1-5 — cross-navigation network ledger

- Keep application API-attempt counters outside a document lifetime.
- Count denied fetch, XHR, WebSocket, EventSource, beacon and service-worker registration separately.
- Keep Playwright request routing as a second independent witness.
- Normal product interactions run in a clean context and prove zero application attempts and zero non-loopback
  requests.
- A separate negative-control context deliberately invokes one denied fetch on an early page, navigates, then
  proves the persistent ledger still reports exactly one fetch attempt.
- Vite HMR on fixed loopback may be separately disclosed but cannot share or erase application counters.

### P1-6 — Rail state consistency

- The selected Rail item derives from the same effective observer projection as center and Focus.
- Remove the selected item's static per-workflow completion label.
- Add a unit or E2E matrix across three workflows × eight frozen states proving selected Rail state/trust agrees
  with `execution-state`.
- Preserve explicit negative controls: `cfd:running` is not completed; `docx:completed` is neutral completed.
- Non-selected synthetic items may retain lightweight fixture labels but cannot override the selected item.

## Mandatory synchronous red gate

After the harness-only lazy-`mkdtemp` repair and after every focused unit/E2E assertion for P1-1 through P1-6 has
been authored:

1. Run `git diff --name-only 47d191cb4799ec57f4739b4d1c709f490481fe77` directly. Before red completion,
   the only changed files may be:

   ```text
   frontend/src/prototypes/workspace-shell/workspace-view.test.js
   frontend/e2e/workspace_shell_prototype_acceptance.py
   ```

2. Run this focused unit red command as one top-level foreground tool call:

   ```bash
   (cd frontend && node --test src/prototypes/workspace-shell/workspace-view.test.js)
   ```

3. Wait for that same tool call to return its final stdout/stderr and a final non-zero exit status.
4. Run this E2E red command as one top-level foreground tool call:

   ```bash
   WORKSPACE_SHELL_SHOTS="/private/tmp/flai-kimi-workspace-shell-v5-evidence.mGixLe" \
     UV_OFFLINE=1 uv run --offline --no-project --with playwright \
     python frontend/e2e/workspace_shell_prototype_acceptance.py
   ```

5. Wait for that same tool call to return its final stdout/stderr and a final non-zero exit status.
6. Using only those two direct tool responses, map at least one failing assertion to each exact finding:
   `WSK3-P1-URL-CONTRACT`, `WSK3-P1-DOM-CONTRACT`, `WSK3-P1-TRUST-COLORS`,
   `WSK3-P1-INVALID-HISTORY`, `WSK3-P1-NETWORK-LEDGER`, and `WSK3-P1-RAIL-STATE`.
7. Emit one assistant-stream checkpoint, never a file:

   ```text
   RED_GATE_COMPLETE
   unit_exit=<non-zero>
   e2e_exit=<non-zero>
   <six finding-to-failed-assertion mappings>
   ```

No edit to `WorkspaceShellPrototype.vue`, `workspace-view.js`, `workspace-shell.css`, or `NOTES.md` is permitted
until both foreground red calls have completed non-zero and `RED_GATE_COMPLETE` is emitted. A task id,
`RUNNING`/background status, or a result obtainable only by a later poll is not completion.

Do not use `&`, `nohup`, `disown`, `bg`, a tool background flag, or any executor-created concurrent task for
red tests, green tests, builds, or audits. The E2E script's own fixed-loopback Vite child process is the sole
exception because it is managed and joined by the foreground Python process. If a tool cannot keep either red
command foreground until final exit, return `BLOCKED`.

The red baseline is `@1` product behavior plus the authorized harness-only lazy-`mkdtemp` repair and the two
owned test files. A non-zero exit alone is insufficient unless the combined direct responses map all six P1s.
You may continue editing only the two test files and rerun both foreground commands if the mapping is incomplete.

After `RED_GATE_COMPLETE`, make the minimum implementation changes and rerun to green. Do not delete or weaken
an existing assertion, the 96-case matrix, an active negative control, or a fail-closed rule.

## Network, dependency and production boundary

- Do not run package installation, `npm install`, `npm ci`, pip, curl, wget, network discovery, or a browser
  against an external URL.
- Browser bootstrap is fixed loopback only.
- Do not change Vite input, package/lock files, entry HTML/main, Stage C, backend, API, router, store, Schema,
  authentication, ACL, classification, signing, delivery, ADRs, scripts, or production adapters.
- Default `npm run build` must emit `dist/index.html` and must not emit `dist/workspace-shell.html`.
- The UI must not create REAL, verified human-sign, production completion, or internal-release facts.

## Required executor verification

Run every command directly in the foreground. Do not pipe, redirect, filter, background, persist, or later poll
the result:

```bash
git merge-base --is-ancestor 47d191cb4799ec57f4739b4d1c709f490481fe77 HEAD
git diff --check
git status --porcelain=v1 --untracked-files=all
git diff --name-only 47d191cb4799ec57f4739b4d1c709f490481fe77
(cd frontend && node --test)
(cd frontend && npm run build)
test -f frontend/dist/index.html
test ! -e frontend/dist/workspace-shell.html
WORKSPACE_SHELL_SHOTS="/private/tmp/flai-kimi-workspace-shell-v5-evidence.mGixLe" \
  UV_OFFLINE=1 uv run --offline --no-project --with playwright \
  python frontend/e2e/workspace_shell_prototype_acceptance.py
```

Do not run `scripts/verify_all.sh`; Codex runs it later in a disposable verification worktree because it
regenerates tracked evidence outside your source-write scope.

## Stop conditions

Stop and return `BLOCKED` before the violating tool call or edit if:

- before both synchronous red commands return non-zero and `RED_GATE_COMPLETE` is emitted, any edit is desired
  outside the two owned test files, except the exact lazy-`mkdtemp` repair inside the E2E;
- a red, green, build or audit command would use a background shell construct, a tool background option, a
  pipeline, `2>&1`, output filtering, redirection, tee, later poll, task-output lookup or private result path;
- either red tool response is only a task id, `RUNNING`, or background acknowledgement rather than final output
  and exit status;
- either red command returns zero before all six negative-control mappings exist;
- a product implementation edit is desired while any executor-owned test process remains active;
- any path under `~/.kimi-code/sessions/**`, any `*/agents/*/tasks/**`, any `output.log`, or the coordinator outer
  dispatch log would be selected, inspected, copied, cited or reused;
- any `@2`, `@3`, or `@4` session, worktree, evidence, skills or dispatch-log path would be reused;
- a source-context read outside the exhaustive allowlist is desired;
- any source write outside the six owned files is required;
- any executor-authored direct non-source write outside the exact build, screenshot, Vite-cache or bounded local
  commit paths is desired;
- the E2E would create a `workspace-shell-shots-*` temporary directory despite the fixed screenshot environment;
- another writer changes an owned file;
- base, branch, worktree, dependency, screenshot-directory or clean-state preflight fails;
- a package install, new dependency, production interface, real API/data, secret, external URL, OpenHands,
  Open WebUI, or non-loopback implementation network is required;
- a P1 can pass only by weakening fail-closed, locked trust colors, synthetic labeling, human signoff, or a
  negative control;
- a required check fails for an attributable reason that cannot be fixed in scope;
- the 90-minute coordinator deadline or provider/account/billing limit is reached.

## Commit and DevelopmentHandoffV1

Make small commits on `codex/kimi-workspace-shell-v5`. Do not push, merge, open a PR, alter Git configuration,
or modify coordinator artifacts. End with a clean worktree, ignoring only the explicitly authorized generated
verification outputs.

Return a `DevelopmentHandoffV1` draft containing:

- work-item ref/digest and `rework_of`;
- new Kimi session ref and honest runtime identity/receipt status;
- base/final SHA, branch, commits, six-file list and patch SHA-256;
- `production_changed_interfaces: []`;
- exact prototype interface changes;
- synchronous red-before/green-after evidence for every P1;
- all verification results and screenshot path;
- synthetic-only/no-internal-data/no-runtime-dependency declarations;
- risks, unresolved issues, recommended next step and a deterministic handoff digest;
- `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`.

Do not fabricate `AssistantDispatchReceiptV1`. Do not label the result authoritative `RUNNING`,
`HANDOFF_SUBMITTED`, accepted, integrated, signed, pushed, merged, production-ready, or internally released.
