"""Opt-in real HTTP contract test against a JerryAgent checkout.

Run with:
    FLAI_JERRYAGENT_REPO=/path/to/jerryagent pytest -q \
      backend/tests/test_jerryagent_dual_repo_contract.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.app.runtime.agent_execution import canonical_json_bytes
from backend.app.runtime.jerryagent_adapter import (
    JerryAgentAdapter,
    build_jerryagent_facts_reader,
    load_jerryagent_settings,
)
from backend.tests.test_jerryagent_adapter import TOKEN, _request


_FIXTURE = r"""
import path from "node:path";
import readline from "node:readline";
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
const terminalRelease = new Promise((resolve) => {
  const input = readline.createInterface({ input: process.stdin });
  input.once("line", () => {
    input.close();
    resolve();
  });
});
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
    store.append({
      type: "subagent.created",
      taskId,
      actor: { kind: "system", label: "JerryAgent runtime" },
      payload: {
        subagentId: "dual-secret-subagent-id",
        name: "dual-secret-subagent-name",
        role: "dual-secret-subagent-role",
        objective: "dual-secret-subagent-objective",
      },
    });
    store.append({
      type: "subagent.status.changed",
      taskId,
      actor: { kind: "subagent", id: "dual-secret-subagent-id" },
      payload: {
        subagentId: "dual-secret-subagent-id",
        status: "running",
        detail: "dual-secret-subagent-detail",
      },
    });
    void terminalRelease.then(() => {
      store.append({
        type: "subagent.status.changed",
        taskId,
        actor: { kind: "subagent", id: "dual-secret-subagent-id" },
        payload: {
          subagentId: "dual-secret-subagent-id",
          status: "completed",
          detail: "dual-secret-subagent-completed-detail",
        },
      });
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
    });
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
        stdin=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        base_url = process.stdout.readline().strip()
        assert base_url.startswith("http://127.0.0.1:")
        settings_env = {
            "FLAI_JERRYAGENT_ENABLED": "1",
            "FLAI_JERRYAGENT_URL": base_url,
            "FLAI_JERRYAGENT_TOKEN": TOKEN,
            "FLAI_JERRYAGENT_TIMEOUT_S": "10",
            "FLAI_JERRYAGENT_POLL_INTERVAL_S": "0.01",
        }
        settings = load_jerryagent_settings(settings_env)
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
        facts_reader = build_jerryagent_facts_reader(settings_env)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                execution = executor.submit(adapter.execute, request)
                identity_bound = None
                observed = None
                event_deadline = time.monotonic() + 5
                while time.monotonic() < event_deadline:
                    for event_name, payload in list(_events.rows):
                        if event_name == "agent_layer_identity_bound":
                            identity_bound = payload
                        elif event_name == "agent_layer_observed":
                            observed = payload
                    if identity_bound is not None and observed is not None:
                        break
                    if execution.done():
                        execution.result()
                        pytest.fail(
                            "JerryAgent execution completed before its live fact "
                            "witness could be observed"
                        )
                    time.sleep(0.005)

                assert identity_bound is not None
                assert observed is not None
                expected_binding = {
                    "requestSha256": identity_bound["request_sha256"],
                    "runtimeTaskId": identity_bound["runtime_task_id"],
                    "instanceId": identity_bound["runtime_identity"]["instanceId"],
                    "sessionId": identity_bound["runtime_identity"]["sessionId"],
                    "runtimeKind": identity_bound["runtime_identity"]["runtimeKind"],
                    "minimumRevision": observed["revision"],
                }
                expected_identity = {
                    **identity_bound["runtime_identity"],
                    "executionId": request.task["id"],
                    "externalTaskId": request.task["id"],
                    "requestSha256": identity_bound["request_sha256"],
                }
                expected_source_epoch = hashlib.sha256(
                    canonical_json_bytes(expected_identity)
                ).hexdigest()

                live_facts = facts_reader.read(
                    request.task["id"],
                    expected_binding=expected_binding,
                    timeout_s=5,
                )
                assert live_facts["sourceEpoch"] == expected_source_epoch
                assert live_facts["revision"] >= observed["revision"]
                assert live_facts["status"] == "running"
                assert live_facts["wait"] is not None
                assert live_facts["wait"] == {
                    "kind": "subagent_completion",
                    "since": live_facts["wait"]["since"],
                    "subjectOrdinal": 1,
                    "pendingCount": 1,
                    "continueWhen": "subagents_terminal",
                }
                assert live_facts["delegationHold"] is None
                assert live_facts["subagentCount"] == 1
                assert live_facts["subagentsTruncated"] is False
                assert len(live_facts["subagents"]) == 1
                assert live_facts["subagents"][0] == {
                    "ordinal": 1,
                    "status": "running",
                    "retryOfOrdinal": None,
                    "createdAt": live_facts["subagents"][0]["createdAt"],
                    "updatedAt": live_facts["subagents"][0]["updatedAt"],
                }
                rendered_live_facts = json.dumps(live_facts, ensure_ascii=False)
                for secret in (
                    "dual-secret-subagent-id",
                    "dual-secret-subagent-name",
                    "dual-secret-subagent-role",
                    "dual-secret-subagent-objective",
                    "dual-secret-subagent-detail",
                ):
                    assert secret not in rendered_live_facts
                assert "identity" not in live_facts
                assert "runtimeTaskId" not in live_facts
                assert "requestSha256" not in live_facts

                # An explicit stdin latch, rather than a timing window, keeps
                # the runtime in its observable running/wait state until the
                # cross-repo /facts assertions have completed.
                assert process.stdin is not None
                process.stdin.write("release-terminal\n")
                process.stdin.flush()
                outcome = execution.result(timeout=10)

            terminal_binding = {
                **expected_binding,
                "minimumRevision": outcome.receipt.final_revision,
            }
            terminal_facts = facts_reader.read(
                outcome.receipt.execution_id,
                expected_binding=terminal_binding,
                timeout_s=5,
            )
        finally:
            facts_reader.close()
            adapter.close()
        assert outcome.receipt.request_sha256 == identity_bound["request_sha256"]
        assert dict(outcome.receipt.runtime_identity) == identity_bound["runtime_identity"]
        assert outcome.receipt.runtime_identity["product"] == "JerryAgent"
        assert outcome.receipt.final_revision is not None
        assert terminal_facts["sourceEpoch"] == expected_source_epoch
        assert terminal_facts["revision"] >= outcome.receipt.final_revision
        assert terminal_facts["status"] == "completed"
        assert terminal_facts["wait"] is None
        assert terminal_facts["subagentCount"] == 1
        assert terminal_facts["subagents"] == [
            {
                "ordinal": 1,
                "status": "completed",
                "retryOfOrdinal": None,
                "createdAt": terminal_facts["subagents"][0]["createdAt"],
                "updatedAt": terminal_facts["subagents"][0]["updatedAt"],
            }
        ]
        assert "dual-secret-subagent-completed-detail" not in json.dumps(
            terminal_facts, ensure_ascii=False
        )
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
