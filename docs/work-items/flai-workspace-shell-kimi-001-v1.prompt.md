# Kimi Workspace Shell V1 Dispatch Prompt

## Frozen envelope

- Work item: `flai-workspace-shell-kimi-001@1`
- Work item digest: `${WORK_ITEM_DIGEST}`
- Human owner: `JerryKogami`
- Frozen base: `71ecc9eadd457dfe03d2737d112f727b4a2183fa`
- Branch: `codex/kimi-workspace-shell-v1`
- Worktree: `/private/tmp/flai-kimi-workspace-shell.ClhXZm`
- Environment: `EXTERNAL_DEVELOPMENT`
- Data: `EXTERNAL_DEVELOPMENT_SYNTHETIC_ONLY`
- Result class: `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`
- Candidate-run budget: one new session, concurrency 1, maximum wall clock 90 minutes, no new paid resource

You are the bounded Workspace Experience executor for this work item. You are not a human reviewer,
CODEOWNER, merge owner, release signer, or production authorization authority.

## Contract precedence

For this work item only, the coordinator-owned dispatch envelope supplied with this prompt supersedes exactly these
unfrozen placeholders in `docs/agents/kimi-k3-workspace-shell-pilot.md`:

- `work_item_digest`;
- `work_item_base_sha`;
- `planned_branch`;
- `planned_worktree`;
- `executor_qualification.status`;
- `status`.

All trust, scope, test, no-copy, data, egress, stop, handoff, and non-release constraints in that pilot remain in
force. This precedence does not modify the pilot file, any ADR, or a production interface.

## Objective

Implement a desktop-grade Vue 3 Workspace Shell prototype that independently re-expresses the approved
interaction specification. The default user experience is a single fluent Workspace, not an Agent-management
dashboard:

- compact Workspace rail on the left;
- continuous execution narrative and always-available composer in the center;
- current most valuable Artifact, preview, diff, monitor, or exception in the right Focus Surface;
- restrained state-driven action glyphs;
- governance hidden by default and disclosed only at a genuine boundary.

Do not reproduce proprietary branding, icons, assets, pixel geometry, copy, or animation curves from ChatGPT,
Claude, or Open WebUI. Do not read or mount the Open WebUI clone. Implement only from the frozen FLAi-OS
behavior documents in this checkout.

## Mandatory preflight

Before editing, print and verify:

```bash
pwd
git branch --show-current
git rev-parse HEAD
git status --short
```

Stop immediately unless:

- cwd is `/private/tmp/flai-kimi-workspace-shell.ClhXZm`;
- branch is `codex/kimi-workspace-shell-v1`;
- HEAD is exactly `71ecc9eadd457dfe03d2737d112f727b4a2183fa`;
- worktree is clean.

Read completely before implementation:

```text
docs/design/OPEN-WEBUI-REFERENCE-AUDIT.md
docs/design/WORKSPACE-SHELL-V1-BLUEPRINT.md
docs/agents/kimi-k3-workspace-shell-pilot.md
docs/adr/ADR-0063-external-development-airgap-internal-workspace.md
docs/adr/ADR-0064-workspace-foreground-verifiable-delivery-and-dual-track-development.md
frontend/src/prototypes/stage-c/observer-contract.js
frontend/src/prototypes/stage-c/runtime-observer-adapter.js
frontend/src/prototypes/stage-c/fixtures.js
```

The Stage C files and every production contract are read-only.

The repository does not contain a tracked `AGENTS.md` at this frozen SHA. The applicable execution rules are
embedded in this prompt: make small reversible diffs, use the repository patch/edit mechanism, preserve unrelated
assets, do not reformat or refactor outside scope, never use destructive Git/filesystem commands, do not change
public or production interfaces, and finish with mechanical verification plus an honest evidence-based handoff.

## Exclusive write scope

You may create or modify only:

```text
frontend/workspace-shell.html
frontend/src/prototypes/workspace-shell/**
frontend/e2e/workspace_shell_prototype_acceptance.py
```

Do not modify:

- any existing Stage C file;
- `frontend/vite.config.js`;
- `frontend/package.json` or lockfiles;
- backend, API, router, store, schema, authentication, ACL, classification, signing, delivery, ADR, script, or
  production entry files.

Do not add dependencies. Do not push, merge, open a PR, alter Git configuration, or delete unrelated files.

## Required behavior

### 1. Workspace shell

- Keep the page sparse: no giant welcome typography, planning wall, card grid, or governance form as the default.
- Left rail: search, recent work, pinned work, and light status only.
- Center: short current action, compact execution history, and fixed composer.
- Right Focus Surface: choose the current Artifact/preview/runtime output/diff/evidence gap/exception according to
  the visible observer projection.
- Model, Agent, Tool, policy IDs and advanced routing stay out of the default surface.

### 2. Trust and motion

- Support action glyphs for search, read, parse, compute, render, and waiting-review.
- Motion runs only for a fresh trusted running projection.
- waiting_review, completed, failed, cancelled, stale, evidence-missing, permission-denied, and UNKNOWN stop motion.
- completed is neutral, never green.
- every task fixture is synthetic; even a `REAL` display form must remain `source-kind=synthetic-fixture` and must
  never enter the trusted REAL slot.
- synthetic/unsigned delivery never becomes teal.
- UI must not create or imply a verified human receipt.

### 3. Composer and queue

- Ctrl/Cmd+Enter submits; Enter alone remains safe for Chinese IME composition.
- Instructions submitted while active are queued as independent items with stable IDs and preserved order.
- Never concatenate multiple queued instructions into one unauditable prompt.
- A synthetic command receipt means accepted/queued only, not completed.

### 4. Focus and failure

- Artifact previews expose a synthetic digest, classification label, and source witness reference.
- invalid or missing observation data fails closed to an UNKNOWN gap and clears any previously sensitive Focus
  projection.
- permission-denied and evidence-missing show explicit public reason codes without pretending execution continues.
- no browser execution of model-provided HTML, JavaScript, Python, or shell.

### 5. Fixtures and accessibility

Provide a deterministic unit/DOM matrix:

```text
3 workflows: docx, meeting, cfd
× 8 states: running, waiting_review, completed, failed, cancelled,
            evidence-missing, permission-denied, observation-invalid
× 4 requested display forms: REAL, MOCK, TEST, UNKNOWN
= 96 cases
```

UNKNOWN is a derived fail-closed projection, not a legal execution reality.

Also verify:

- one explicit stale overlay case outside the 96-case matrix: `docx:running` with expired observation freshness must
  stop motion, display UNKNOWN/unverified, and clear or hide the previously sensitive Focus preview;
- 1440px and 1280px with no horizontal overflow;
- keyboard-only navigation and visible focus;
- reduced-motion;
- color is not the only state signal;
- all visible 11px/12px text meets WCAG 4.5:1 contrast;
- user-visible state selector, glyph motion, right Focus object, and reality badge remain consistent.

### 6. Network and build boundary

- The implementation itself makes no network calls.
- Browser tests may load document/module/static assets only from their fixed loopback dev-server origin.
- Reject and count all application fetch/XHR, WebSocket, EventSource, beacon, service-worker, backend API, and
  non-loopback requests.
- `npm run build` must not emit `frontend/dist/workspace-shell.html`.
- Do not modify Vite production input or add a main-app navigation route.

## Required checks

Run and report every command:

```bash
git merge-base --is-ancestor 71ecc9eadd457dfe03d2737d112f727b4a2183fa HEAD
git diff --check
git status --porcelain=v1 --untracked-files=all
{
  git diff --name-only 71ecc9eadd457dfe03d2737d112f727b4a2183fa
  git ls-files --others --exclude-standard
} | LC_ALL=C sort -u
(cd frontend && node --test)
(cd frontend && npm run build)
test -f frontend/dist/index.html
test ! -e frontend/dist/workspace-shell.html
WORKSPACE_SHELL_SHOTS="$(mktemp -d /private/tmp/flai-workspace-shell-shots.XXXXXX)" \
  UV_OFFLINE=1 uv run --offline --no-project --with playwright \
  python frontend/e2e/workspace_shell_prototype_acceptance.py
UV_OFFLINE=1 bash scripts/verify_all.sh
```

Scope output must contain only the exclusive write paths.

## Stop conditions

Stop and return a blocked draft handoff if:

- any required change falls outside the exclusive write scope;
- a dependency, Vite production input, production interface, Stage C contract, real API, real data, secret, or
  non-loopback runtime network is required;
- an Open WebUI source checkout or proprietary asset is required;
- a trust color, fail-closed rule, or synthetic label would need weakening;
- the base/branch/worktree preflight fails;
- another writer changes the target files;
- a required check fails for a reason attributable to this work item and cannot be fixed within scope.
- the coordinator wall-clock limit is reached, the provider reports a token/rate/account limit, or any new paid
  resource would be required.

## Commit and handoff

Make small commits on `codex/kimi-workspace-shell-v1`. Do not push.

Return a `DevelopmentHandoffV1` draft with:

- work item ref and digest;
- Kimi session ref;
- honest runtime identity evidence status;
- base and final SHA;
- commit refs and patch SHA-256;
- changed files;
- `production_changed_interfaces: []`;
- all prototype interfaces created;
- every verification command and exact result;
- screenshot paths;
- risks and unresolved issues;
- `SOURCE_CANDIDATE_NOT_INTERNAL_RELEASE`;
- recommended next step.

The Kimi CLI cannot self-issue an authoritative `AssistantDispatchReceiptV1`; do not fabricate one and do not label
the run as authoritative `RUNNING`, `HANDOFF_SUBMITTED`, integrated, accepted, or internally released.
