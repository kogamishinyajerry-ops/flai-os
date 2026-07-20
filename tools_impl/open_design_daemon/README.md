# Open Design loopback daemon adapter

This is a narrow, default-off `mock=false` trial adapter. It is not a generic prompt
gateway and it is not production-ready attestation.

External input is limited to one server-owned asset-slot enum and one or more
server-owned comparison-slot enums. The task isolation id is injected only through
verified Runtime context and is rejected in the payload. There is no free-form brief,
file, attachment, or knowledge field. The adapter itself owns the fixed design intent.

Enablement requires the literal `FLAI_OPEN_DESIGN_DAEMON_ENABLED=1` plus exact values
for URL, version, channel, agent, requested model, published design-system id, and design-system
digest. URL accepts only an explicit-port `http://127.0.0.1:PORT` or
`http://[::1]:PORT` origin. `0` or unset is disabled; other boolean spellings fail.
The upstream status contract does not attest the actual executing model, so successful
provenance records `model_execution_attested=false`.

The REST client disables environment proxies and redirects, performs no retry, and
uses only public API routes. Candidate bytes come from
`GET /api/projects/:id/files` and per-segment encoded
`GET /api/projects/:id/files/<path>`; `/raw` is forbidden. File lists must remain
exactly stable, and every byte stream is fetched twice before capture.

Only strict UTF-8 HTML, SVG, CSS, JSON, Markdown and structurally verified static PNG
are admitted. HTML/SVG are attachments only. They are never executed by this adapter.
All output remains `candidate_only`, `release_effect=none`,
`classification=sensitive`, `execution_trust=untrusted_generated`, and requires human
review. Fixed input does not prove that daemon ambient memory, custom instructions, or
host files were absent; the text screen is not a sanitizer or declassification step.

The corresponding Agent package remains disabled because its role metadata is not yet
enforced by Runtime/API entrypoints. Failed responses retain `failure_stage`, known
project/run identities, and `unreconciled_upstream_side_effects_may_exist`; timeout
cannot currently cancel the Python worker thread or reconcile an Open Design run.
