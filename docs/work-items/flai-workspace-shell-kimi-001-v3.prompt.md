# Kimi Workspace Shell V1 — Six-P1 Rework Dispatch

## Frozen envelope

- Work item: `flai-workspace-shell-kimi-001@3`
- Work item digest: `${WORK_ITEM_DIGEST}`
- Human owner: `JerryKogami`
- Owner authorization: `批准 @3 最小重派`
- Rework lineage: `@1` candidate → `@2` fail-closed/no source change → `@3`
- Frozen base: `47d191cb4799ec57f4739b4d1c709f490481fe77`
- Branch: `codex/kimi-workspace-shell-v3`
- Worktree: `/private/tmp/flai-kimi-workspace-shell-v3.MHDHC6`
- Environment: `EXTERNAL_DEVELOPMENT`
- Fixtures: `SYNTHETIC_ONLY`
- Internal data access: `NONE`
- Internal runtime dependency: `NONE`
- Result class: `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`

You are the bounded implementation executor. You are not a human reviewer, CODEOWNER, merge owner, release
signer, production authority, or source of trusted FLAi facts. Close exactly the six P1 findings below. Do not
redesign the shell, fix P2 smells, add features, integrate OpenHands/Open WebUI, or change production interfaces.

## Mandatory preflight

Before any source read or edit, run:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
test -d frontend/node_modules
test "${WORKSPACE_SHELL_SHOTS:-}" = "/private/tmp/flai-kimi-workspace-shell-v3-evidence.C5A3NE"
test -d "${WORKSPACE_SHELL_SHOTS}"
test -z "$(find "${WORKSPACE_SHELL_SHOTS}" -mindepth 1 -maxdepth 1 -print -quit)"
```

Stop and return `BLOCKED` unless:

- cwd is `/private/tmp/flai-kimi-workspace-shell-v3.MHDHC6`;
- branch is `codex/kimi-workspace-shell-v3`;
- HEAD is exactly `47d191cb4799ec57f4739b4d1c709f490481fe77`;
- the worktree is clean;
- `frontend/node_modules` already exists;
- `WORKSPACE_SHELL_SHOTS` is exactly the repo-external path above and is empty.

This must be a fresh session. Never resume or inspect
`session_f55a6882-e7cb-4c8a-b465-04d0bba4d950` or any earlier Kimi session.

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

## Exclusive write scope

Modify only:

```text
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
```

Do not create any other repository file. Screenshots may be written only to
`/private/tmp/flai-kimi-workspace-shell-v3-evidence.C5A3NE`.

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

## Test-first requirement

Before implementation edits, add or adjust focused tests for all six P1s and run them against `@1` behavior.
Record the failing assertions. Then make the minimum implementation changes and rerun to green. Do not delete or
weaken an existing assertion, the 96-case matrix, an active negative control, or a fail-closed rule.

## Network, dependency and production boundary

- Do not run package installation, `npm install`, `npm ci`, pip, curl, wget, network discovery, or a browser
  against an external URL.
- Browser bootstrap is fixed loopback only.
- Do not change Vite input, package/lock files, entry HTML/main, Stage C, backend, API, router, store, Schema,
  authentication, ACL, classification, signing, delivery, ADRs, scripts, or production adapters.
- Default `npm run build` must emit `dist/index.html` and must not emit `dist/workspace-shell.html`.
- The UI must not create REAL, verified human-sign, production completion, or internal-release facts.

## Required executor verification

Run and report:

```bash
git merge-base --is-ancestor 47d191cb4799ec57f4739b4d1c709f490481fe77 HEAD
git diff --check
git status --porcelain=v1 --untracked-files=all
git diff --name-only 47d191cb4799ec57f4739b4d1c709f490481fe77
(cd frontend && node --test)
(cd frontend && npm run build)
test -f frontend/dist/index.html
test ! -e frontend/dist/workspace-shell.html
WORKSPACE_SHELL_SHOTS="/private/tmp/flai-kimi-workspace-shell-v3-evidence.C5A3NE" \
  UV_OFFLINE=1 uv run --offline --no-project --with playwright \
  python frontend/e2e/workspace_shell_prototype_acceptance.py
```

Do not run `scripts/verify_all.sh`; Codex runs it later in a disposable verification worktree because it
regenerates tracked evidence outside your write scope.

## Stop conditions

Stop and return `BLOCKED` before the violating tool call or edit if:

- a source-context read outside the exhaustive allowlist is desired;
- any write outside the six owned files is required;
- another writer changes an owned file;
- base, branch, worktree, dependency, screenshot-directory or clean-state preflight fails;
- a package install, new dependency, production interface, real API/data, secret, external URL, OpenHands,
  Open WebUI, or non-loopback implementation network is required;
- a P1 can pass only by weakening fail-closed, locked trust colors, synthetic labeling, human signoff, or a
  negative control;
- a required check fails for an attributable reason that cannot be fixed in scope;
- the 90-minute coordinator deadline or provider/account/billing limit is reached.

## Commit and DevelopmentHandoffV1

Make small commits on `codex/kimi-workspace-shell-v3`. Do not push, merge, open a PR, alter Git configuration,
or modify coordinator artifacts. End with a clean worktree.

Return a `DevelopmentHandoffV1` draft containing:

- work-item ref/digest and `rework_of`;
- new Kimi session ref and honest runtime identity/receipt status;
- base/final SHA, branch, commits, six-file list and patch SHA-256;
- `production_changed_interfaces: []`;
- exact prototype interface changes;
- red-before/green-after evidence for every P1;
- all verification results and screenshot path;
- synthetic-only/no-internal-data/no-runtime-dependency declarations;
- risks, unresolved issues, recommended next step and a deterministic handoff digest;
- `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`.

Do not fabricate `AssistantDispatchReceiptV1`. Do not label the result authoritative `RUNNING`,
`HANDOFF_SUBMITTED`, accepted, integrated, signed, pushed, merged, production-ready, or internally released.
