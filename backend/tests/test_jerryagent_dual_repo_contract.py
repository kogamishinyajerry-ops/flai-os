"""Opt-in real HTTP contract test against a JerryAgent checkout.

Run with:
    FLAI_JERRYAGENT_REPO=/path/to/jerryagent pytest -q \
      backend/tests/test_jerryagent_dual_repo_contract.py
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from backend.app.runtime.jerryagent_adapter import JerryAgentAdapter, load_jerryagent_settings
from backend.tests.test_jerryagent_adapter import TOKEN, _request


_FIXTURE = r"""
import path from "node:path";
import { pathToFileURL } from "node:url";

const repo = path.resolve(process.argv[2]);
const eventFile = path.resolve(process.argv[3]);
const token = process.argv[4];
const port = Number(process.argv[5]);
const bridgeModule = await import(pathToFileURL(path.join(repo, "runtime/desktop-bridge.js")).href);
const storeModule = await import(pathToFileURL(path.join(repo, "runtime/event-store.js")).href);
const { DesktopBridgeServer, AGENT_LAYER_COMMAND_BINDING } = bridgeModule;
const { RuntimeEventStore } = storeModule;
let eventId = 0;
const store = new RuntimeEventStore({
  filePath: eventFile,
  sessionId: "dual-repo-session",
  idFactory: () => `dual-event-${++eventId}`,
});
store.append({
  type: "session.started",
  actor: { kind: "system", label: "contract fixture" },
  payload: { cwd: repo, name: "FLAi dual-repo contract" },
});
const server = new DesktopBridgeServer({
  store,
  port,
  fallbackToEphemeral: false,
  agentLayerToken: token,
  identity: {
    instanceId: "dual-repo-instance",
    sessionId: "dual-repo-session",
    runtimeKind: "external",
  },
  handleCommand: async (command) => {
    const binding = command[AGENT_LAYER_COMMAND_BINDING];
    const taskId = "dual-runtime-task";
    store.append({
      type: "task.created",
      taskId,
      actor: { kind: "user", label: "FLAi Agent Layer" },
      payload: {
        title: "FLAi dual-repo contract",
        prompt: command.prompt,
        source: "flai-agent-layer",
        autoCollaboration: command.autoCollaboration,
        externalExecution: binding,
      },
    });
    store.append({
      type: "task.status.changed",
      taskId,
      actor: { kind: "agent", label: "JerryAgent" },
      payload: { status: "running", detail: "fixture running" },
    });
    setTimeout(() => {
      store.append({
        type: "message.recorded",
        taskId,
        actor: { kind: "agent", label: "JerryAgent" },
        payload: {
          messageId: "dual-message",
          role: "assistant",
          text: "双仓真实 HTTP 协议握手候选，仍需 FLAi 人工复核。",
        },
      });
      store.append({
        type: "task.status.changed",
        taskId,
        actor: { kind: "agent", label: "JerryAgent" },
        payload: { status: "completed", detail: "fixture completed" },
      });
    }, 25);
    return { accepted: true, taskId, dispatchStatus: "pending" };
  },
});
const address = await server.start();
process.stdout.write(`${address.url}\n`);
const stop = async () => { await server.close(); process.exit(0); };
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
"""


@pytest.mark.skipif(
    not os.environ.get("FLAI_JERRYAGENT_REPO") or shutil.which("node") is None,
    reason="set FLAI_JERRYAGENT_REPO to run the real dual-repo bridge contract",
)
@pytest.mark.parametrize("astral_prompt", [False, True], ids=["baseline", "unicode-codepoints"])
def test_flai_adapter_completes_against_real_jerryagent_bridge(
    tmp_path: Path, astral_prompt: bool
) -> None:
    repo = Path(os.environ["FLAI_JERRYAGENT_REPO"]).resolve()
    assert (repo / "runtime" / "desktop-bridge.js").is_file()
    fixture = tmp_path / "dual-repo-fixture.mjs"
    fixture.write_text(_FIXTURE, encoding="utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [
            "node",
            str(fixture),
            str(repo),
            str(tmp_path / "events.jsonl"),
            TOKEN,
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        base_url = process.stdout.readline().strip()
        assert base_url.startswith("http://127.0.0.1:")
        settings = load_jerryagent_settings(
            {
                "FLAI_JERRYAGENT_ENABLED": "1",
                "FLAI_JERRYAGENT_URL": base_url,
                "FLAI_JERRYAGENT_TOKEN": TOKEN,
                "FLAI_JERRYAGENT_TIMEOUT_S": "10",
                "FLAI_JERRYAGENT_POLL_INTERVAL_S": "0.01",
            }
        )
        request, _events = _request(tmp_path)
        if astral_prompt:
            # Cross-language witness: Python counts Unicode code points while
            # JavaScript String.length counts UTF-16 units.  This payload stays
            # below both FLAi's 32k-character and 64 KiB canonical-body limits,
            # but would be rejected by a Jerry bridge that used UTF-16 units.
            request.task["inputs"] = {
                "objective": "😀" * 8_000,
                "constraints": ["😀" * 500] * 12 + ["a" * 500] * 8,
            }
        adapter = JerryAgentAdapter(settings)
        try:
            outcome = adapter.execute(request)
        finally:
            adapter.close()
        assert outcome.receipt.runtime_identity["product"] == "JerryAgent"
        assert outcome.receipt.final_revision is not None
        assert outcome.result["outputs"][0]["candidate_only"] is True
        assert (tmp_path / "output" / "jerryagent_result.md").is_file()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.returncode not in (0, -15):
            stderr = process.stderr.read() if process.stderr is not None else ""
            pytest.fail(f"JerryAgent bridge fixture exited {process.returncode}: {stderr}")
