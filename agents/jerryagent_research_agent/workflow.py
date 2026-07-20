"""Fail-closed sentinel for a sidecar-only Agent package."""


def run(_context):
    raise RuntimeError(
        "jerryagent_research_agent must execute through "
        "jerryagent_sidecar@flai.agent-layer.v1; native execution is forbidden"
    )

