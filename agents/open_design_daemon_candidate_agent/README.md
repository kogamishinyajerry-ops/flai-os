# Open Design daemon candidate Agent

Disabled/L0 package for the narrow Open Design loopback adapter. The manifest's
`admin_only` permission is planning metadata only: the current Runtime/API does not
enforce it, so the Agent must remain disabled until role gates cover create, batch,
and team entrypoints.

The external input is deliberately non-expressive: one of three server-owned asset
slots and an allowlisted comparison matrix. Task isolation identity is injected only
by verified Runtime context and is rejected in the payload. Output is nevertheless
`sensitive`: fixed FLAi input does not prove that Open Design ambient memory, custom
instructions, or host files were absent. Any future arbitrary brief, file, attachment,
or knowledge input requires a new version and explicit classification/role policy.

`mock=false` means the adapter attempted the configured loopback daemon; it does not
attest the actual executing model, sandbox containment, sidecar identity, or production
readiness. Successful provenance records the requested model separately and fixes
`model_execution_attested=false`. Failed tool responses retain their failure stage,
deterministic project/run identities when known, and whether unreconciled upstream
side effects may exist.

On success the package contains:

- `open_design_daemon_candidates.json` — exact candidate manifest and passive preview bindings;
- `open_design_daemon_provenance.json` — daemon/result/safety evidence;
- `flai_design_reference_package.json` — exact FLAi SSOT projection;
- `OPEN_DESIGN_DAEMON_REVIEW.md` — the human boundary;
- `captured/**` — exact double-fetched candidate bytes.

The workflow exposes `review_contract=open-design-candidate/v1`,
`generator_kind=open_design_daemon`, and the exact candidate-manifest SHA-256 for a
pre-seal Runtime projection. It never treats workflow success as selection or release.
P2.8 currently rejects this sensitive candidate fail-closed; a live compare/promotion
path remains blocked until enforceable roles and an explicit per-file declassification
policy (or an attested dedicated sidecar) exist.
