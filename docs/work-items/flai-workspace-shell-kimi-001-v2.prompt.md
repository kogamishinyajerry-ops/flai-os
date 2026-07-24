# Kimi Workspace Shell V1 P1 Rework Dispatch Prompt

## Frozen envelope

- Work item: `flai-workspace-shell-kimi-001@2`
- Work item digest: `${WORK_ITEM_DIGEST}`
- Rework of: `flai-workspace-shell-kimi-001@1`
- Human owner: `JerryKogami`
- Frozen base: `47d191cb4799ec57f4739b4d1c709f490481fe77`
- Branch: `codex/kimi-workspace-shell-v2`
- Worktree: `/private/tmp/flai-kimi-workspace-shell-v2.eZNz49`
- Environment: `EXTERNAL_DEVELOPMENT`
- Data: `EXTERNAL_DEVELOPMENT_SYNTHETIC_ONLY`
- Result class: `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`

You are the bounded rework executor for six frozen P1 findings. You are not a human reviewer, CODEOWNER, merge
owner, release signer, production authority, or source of FLAi trust facts.

## Objective

Close exactly `WSK3-P1-URL-CONTRACT`, `WSK3-P1-DOM-CONTRACT`, `WSK3-P1-TRUST-COLORS`,
`WSK3-P1-INVALID-HISTORY`, `WSK3-P1-NETWORK-LEDGER`, and `WSK3-P1-RAIL-STATE`.

Do not redesign the shell, add features, refactor unrelated code, integrate OpenHands/Open WebUI, add a production
entry, change a production interface, or address P2/code-smell findings in source.

## Mandatory preflight

Before editing, print and verify:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
test -d frontend/node_modules
test "${WORKSPACE_SHELL_SHOTS:-}" = "/private/tmp/flai-workspace-shell-v2-evidence.ti4aa2"
test -d "${WORKSPACE_SHELL_SHOTS}"
test -z "$(find "${WORKSPACE_SHELL_SHOTS}" -mindepth 1 -maxdepth 1 -print -quit)"
```

Stop unless:

- cwd is `/private/tmp/flai-kimi-workspace-shell-v2.eZNz49`;
- branch is `codex/kimi-workspace-shell-v2`;
- HEAD is exactly `47d191cb4799ec57f4739b4d1c709f490481fe77`;
- the worktree is clean;
- `frontend/node_modules` is already present;
- `WORKSPACE_SHELL_SHOTS` is exactly the coordinator-owned, repo-external directory
  `/private/tmp/flai-workspace-shell-v2-evidence.ti4aa2`, and that directory is empty.

Read completely before editing:

```text
docs/agents/kimi-k3-workspace-shell-pilot.md
docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md
frontend/src/prototypes/stage-c/stage-c.css
frontend/src/prototypes/stage-c/StageCWorkbenchPrototype.vue
frontend/src/prototypes/stage-c/observer-contract.js
frontend/src/prototypes/workspace-shell/fixtures.js
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
```

The coordinator freeze payload and acceptance report are not present in the executor branch. This prompt contains
the complete authorized rework. Do not search for or read any other files unless a listed file imports it and the
read is strictly necessary to understand an existing symbol. Do not open external links.

## Exclusive write scope

You may modify only:

```text
frontend/src/prototypes/workspace-shell/WorkspaceShellPrototype.vue
frontend/src/prototypes/workspace-shell/workspace-view.js
frontend/src/prototypes/workspace-shell/workspace-view.test.js
frontend/src/prototypes/workspace-shell/workspace-shell.css
frontend/e2e/workspace_shell_prototype_acceptance.py
frontend/src/prototypes/workspace-shell/NOTES.md
```

Every other file is read-only. Do not create new source, test, configuration, lock, screenshot, or handoff files in
the repository. Screenshots may be written only to the coordinator-provided temporary evidence directory.

## Six exact P1 fixes

### P1-1 — URL contract

- The only reality query is `reality=REAL|MOCK|TEST|UNKNOWN`.
- Do not support `form` as an alias.
- Missing, empty, mixed-case, or invalid `reality` fails closed to `UNKNOWN`.
- Every positive core E2E URL must explicitly include a legal `reality`.
- Add negative E2E checks proving `?reality=MOCK` renders MOCK, while `?reality=FAKE`, `?reality=`,
  `?reality=mock`, a missing `reality`, and `?form=MOCK` all render UNKNOWN.

### P1-2 — frozen DOM contract

The rendered page must expose these exact ten `data-testid` values:

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

Additional internal test IDs are allowed only where existing interaction tests need them. Add one E2E assertion
that enumerates all ten exact values. Conditional queue and delivery nodes must be checked in states where they
are expected to exist.

### P1-3 — locked trust colors and semantics

- Define and preserve the locked tokens:
  - clay work `#b4562f`;
  - REAL green `#1e7d46`;
  - human-sign teal `#0e7c7b`;
  - true-failure red `#b3352c`;
  - unverified amber `#986810`.
- The synthetic prototype must never render REAL green or human-sign teal, but the token semantics must remain
  defined and unborrowed.
- `data-trust` may use `work`, `terminal`, `fail`, or `unverified`; terminal is neutral ink, not a sixth trust color.
- Remove `active`, `attention`, and `synthetic` as trust-slot values.
- Synthetic REAL/MOCK/TEST display forms remain explicitly synthetic and use `data-slot="unverified"`; the form
  remains visible in `data-reality-form`.
- Running uses clay work; waiting_review is static clay work; completed/cancelled are neutral terminal;
  failed/permission-denied are red fail; missing/invalid/UNKNOWN are amber unverified.
- Add DOM/computed-style assertions that running is exactly `rgb(180, 86, 47)`, failed exactly
  `rgb(179, 53, 44)`, UNKNOWN exactly `rgb(152, 104, 16)`, completed is neither green nor clay, and no synthetic
  page contains `data-slot=real` or `data-slot=sign`.

### P1-4 — invalid history

- UI history may use raw fixture events only after the observer projection confirms the whole event set.
- If the projected snapshot mode is `unknown`, render no event history.
- At minimum, `observation-invalid` and stale/identity/reality fail-closed projections must not expose the rejected
  event title, object, digest, witness, preview, or step in history.
- Add unit and E2E checks proving `observation-invalid` has zero history rows and does not contain
  `正在处理：气动周报-草稿.docx`.
- In the unit test, traverse all 96 matrix fixtures plus the `stale` overlay; for every case whose projected
  snapshot is `mode === "unknown"`, assert zero history. This assertion must be generic over projection mode,
  not a special case for `observation-invalid`.

### P1-5 — cross-navigation network ledger

- Keep application API-attempt counters outside a document lifetime so navigation cannot reset them.
- Count denied fetch, XHR, WebSocket, EventSource, beacon, and service-worker registration attempts separately.
- Keep actual Playwright request routing as a second independent network witness.
- Run the normal product interaction sequence in a clean context and prove zero application attempts and zero
  non-loopback requests.
- In a separate negative-control context, deliberately invoke one denied fetch on an early page, navigate, and
  prove the persistent ledger still reports exactly one fetch attempt. This negative control must fail against @1.
- Vite HMR on fixed loopback may remain separately disclosed, but it cannot erase or share application counters.

### P1-6 — Rail state consistency

- The currently selected workflow's Rail state must derive from the same effective observer projection as the
  center and Focus Surface.
- It must not use a static per-workflow completion label.
- Add a unit or E2E matrix check across all three workflows and all eight frozen states proving the selected Rail
  item has the same effective observed state/trust semantics as `execution-state`. Keep the explicit negative
  controls that `cfd:running` does not show completed and `docx:completed` shows a neutral completed label.
- Other non-selected synthetic items may retain lightweight fixture labels, but must not override the current
  item's observed state.

## Test-first requirement

Before changing implementation behavior, add or adjust focused tests for all six P1s and run them against the @1
behavior. Record which new assertions fail. Then implement the minimum fixes and rerun them to green. Do not
weaken or delete existing assertions.

## Network, dependency, and production boundary

- Do not run `npm install`, `npm ci`, package managers, curl, wget, browsers to external URLs, or any network
  discovery command. The coordinator already provisioned dependencies offline.
- Browser bootstrap is fixed loopback only.
- Do not read environment variables, secrets, internal data, Open WebUI source, or external repositories.
- Do not change `frontend/vite.config.js`, package files, Stage C files, backend, API, router, store, Schema, ADR,
  scripts, authentication, ACL, classification, signing, delivery, or production adapters.
- Default `npm run build` must continue to emit `dist/index.html` and not `dist/workspace-shell.html`.
- The UI must not produce REAL, verified human sign, or production completion facts.

## Required verification

Run every command and report exact results:

```bash
git merge-base --is-ancestor 47d191cb4799ec57f4739b4d1c709f490481fe77 HEAD
git diff --check
git status --porcelain=v1 --untracked-files=all
git diff --name-only 47d191cb4799ec57f4739b4d1c709f490481fe77
(cd frontend && node --test)
(cd frontend && npm run build)
test -f frontend/dist/index.html
test ! -e frontend/dist/workspace-shell.html
WORKSPACE_SHELL_SHOTS="/private/tmp/flai-workspace-shell-v2-evidence.ti4aa2" \
  UV_OFFLINE=1 uv run --offline --no-project --with playwright \
  python frontend/e2e/workspace_shell_prototype_acceptance.py
```

Final diff must contain only the six authorized files. Do not run `scripts/verify_all.sh`: the Codex coordinator
will run that full gate later in a disposable verification worktree because it regenerates tracked review
screenshots outside your write scope. Never restore, overwrite, or stage an out-of-scope file. The final executor
worktree must be clean after commits.

## Stop conditions

Stop and return `BLOCKED` if:

- any fix requires a file outside the exclusive write scope;
- a new dependency, package install, production interface, Stage C change, real API/data, secret, external URL,
  OpenHands/Open WebUI integration, or non-loopback runtime network is required;
- a P1 can pass only by weakening fail-closed, the locked trust colors, synthetic labeling, human signoff, or the
  negative control;
- the base/branch/worktree preflight fails;
- another writer changes an owned file;
- the wall-clock limit, provider limit, or any paid-resource requirement is reached.

## Commit and handoff

Make small commits on `codex/kimi-workspace-shell-v2`. Do not push, merge, open a PR, alter Git configuration, or
modify coordinator control artifacts.

Return a `DevelopmentHandoffV1` draft with:

- work-item ref/digest and `rework_of`;
- Kimi session ref and honest runtime identity evidence;
- base/final SHA, branch, commits, changed files, patch SHA-256;
- `production_changed_interfaces: []`;
- exact prototype interface changes;
- red-before/green-after evidence for all six P1s;
- every verification result and screenshot path;
- risks, unresolved issues, and recommended next step;
- `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`.

Do not fabricate an `AssistantDispatchReceiptV1` and do not label the result authoritative `RUNNING`,
`HANDOFF_SUBMITTED`, accepted, integrated, signed, pushed, merged, or internally released.
