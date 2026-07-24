#!/usr/bin/env python3
"""Fail-closed structural checker for the AirGap/Workspace F0 review intake.

This checker proves only local JSON structure and Git object binding. It cannot
authenticate human identity, role assignment, signatures, revocation, findings,
SoD exceptions, or an append-only decision ledger. It never grants
implementation or production authority.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_DOMAINS = (
    "product-architecture-domain-ownership",
    "airgap-cybersecurity-transfer-control",
    "internal-identity-acl-classification-privacy",
    "self-hosted-collaboration-records-continuity",
    "authoritative-knowledge-legacy-ingest",
    "agent-runtime-sandbox-evidence-audit",
    "software-supply-chain-internal-release-operations",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DECISIONS = {"pending", "approve", "conditional", "reject"}
ANSWER_VALUES = {"pending", "satisfied", "not_satisfied", "unknown"}


class ReviewIntakeError(ValueError):
    """Raised when the local review intake is structurally invalid."""


def _git(repo_root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        raise ReviewIntakeError(
            f"git {' '.join(args)} failed: {process.stderr.strip()}"
        )
    return process.stdout.strip()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewIntakeError(message)


def validate_manifest(
    manifest: dict[str, Any],
    repo_root: Path,
    *,
    verify_git: bool = True,
) -> dict[str, Any]:
    _require(
        manifest.get("manifest_version")
        == "flai.airgap-workspace.named-review-manifest.v1",
        "unexpected manifest_version",
    )
    _require(
        manifest.get("review_package_id")
        == "flai.airgap-workspace-f0.named-review.round-1",
        "unexpected review_package_id",
    )

    target = manifest.get("target")
    _require(isinstance(target, dict), "target must be an object")
    commit_sha = target.get("frozen_commit_sha")
    tree_sha = target.get("frozen_tree_sha")
    _require(isinstance(commit_sha, str) and HEX40.fullmatch(commit_sha), "invalid frozen_commit_sha")
    _require(isinstance(tree_sha, str) and HEX40.fullmatch(tree_sha), "invalid frozen_tree_sha")
    _require(target.get("production_status") == "NO-GO", "production_status must remain NO-GO")

    paths = target.get("normative_paths")
    _require(isinstance(paths, list) and paths, "normative_paths must be non-empty")
    _require(len(paths) == len(set(paths)), "normative_paths contains duplicates")
    _require(
        all(isinstance(path, str) and path and not path.startswith("/") for path in paths),
        "normative_paths must be non-empty repository-relative strings",
    )

    if verify_git:
        actual_tree = _git(repo_root, "rev-parse", f"{commit_sha}^{{tree}}")
        _require(actual_tree == tree_sha, "frozen commit does not resolve to frozen tree")
        for path in paths:
            _git(repo_root, "cat-file", "-e", f"{commit_sha}:{path}")

    authorization = manifest.get("implementation_authorization")
    _require(isinstance(authorization, dict), "implementation_authorization must be an object")
    _require(authorization.get("authorized") is False, "implementation authorization must remain false")
    _require(authorization.get("authorization_ref") is None, "authorization_ref must remain null")

    catalog = manifest.get("question_catalog")
    _require(isinstance(catalog, dict) and catalog, "question_catalog must be non-empty")

    reviews = manifest.get("reviews")
    _require(isinstance(reviews, list), "reviews must be an array")
    _require(len(reviews) == 7, "exactly seven review domains are required")
    domain_ids = [review.get("domain_id") for review in reviews]
    _require(tuple(domain_ids) == EXPECTED_DOMAINS, "review domains or order changed")

    assigned = 0
    approved = 0
    pending = 0
    blocking = 0
    actor_domains: dict[str, list[dict[str, Any]]] = {}

    for review in reviews:
        domain_id = review["domain_id"]
        required_questions = review.get("required_question_ids")
        _require(
            isinstance(required_questions, list) and required_questions,
            f"{domain_id}: required_question_ids must be non-empty",
        )
        _require(
            all(question in catalog for question in required_questions),
            f"{domain_id}: unknown question id",
        )
        answers = review.get("question_answers")
        _require(isinstance(answers, dict), f"{domain_id}: question_answers must be an object")
        _require(
            set(answers) == set(required_questions),
            f"{domain_id}: question_answers must exactly match required_question_ids",
        )
        _require(
            all(value in ANSWER_VALUES for value in answers.values()),
            f"{domain_id}: invalid question answer",
        )

        assignment = review.get("reviewer_assignment")
        _require(isinstance(assignment, dict), f"{domain_id}: reviewer_assignment must be an object")
        _require(
            assignment.get("reviewer_principal_type") == "human",
            f"{domain_id}: reviewer principal must be human",
        )
        identity_values = (
            assignment.get("reviewer_display_name"),
            assignment.get("reviewer_actor_id"),
            assignment.get("reviewer_role_assignment_ref"),
        )
        has_any_identity = any(value is not None for value in identity_values)
        has_full_identity = all(isinstance(value, str) and value.strip() for value in identity_values)
        _require(
            not has_any_identity or has_full_identity,
            f"{domain_id}: reviewer identity assignment is partial",
        )
        if has_full_identity:
            assigned += 1
            actor_id = assignment["reviewer_actor_id"]
            actor_domains.setdefault(actor_id, []).append(review)

        decision = review.get("decision")
        _require(decision in DECISIONS, f"{domain_id}: invalid decision")
        if decision == "pending":
            pending += 1
            _require(review.get("reviewed_at") is None, f"{domain_id}: pending review cannot have reviewed_at")
        else:
            _require(has_full_identity, f"{domain_id}: decision requires complete human assignment")
            _require(
                isinstance(review.get("decision_rationale"), str)
                and review["decision_rationale"].strip(),
                f"{domain_id}: decision requires rationale",
            )
            _require(
                isinstance(review.get("reviewed_at"), str)
                and review["reviewed_at"].strip(),
                f"{domain_id}: decision requires reviewed_at",
            )
            _require(
                all(value != "pending" for value in answers.values()),
                f"{domain_id}: decision cannot retain pending answers",
            )
            if decision == "approve":
                _require(
                    all(value == "satisfied" for value in answers.values()),
                    f"{domain_id}: approve requires all answers satisfied",
                )
                approved += 1
            else:
                blocking += 1

    for actor_id, actor_reviews in actor_domains.items():
        if len(actor_reviews) <= 1:
            continue
        for review in actor_reviews:
            exception_ref = review["reviewer_assignment"].get(
                "segregation_of_duties_exception_ref"
            )
            _require(
                isinstance(exception_ref, str) and exception_ref.strip(),
                f"{actor_id}: multiple domains require SoD exception on every assignment",
            )

    verifier = manifest.get("external_trust_verifier")
    _require(isinstance(verifier, dict), "external_trust_verifier must be an object")
    verifier_status = verifier.get("status")
    _require(
        verifier_status in {"UNCONFIGURED", "REFERENCED-NOT-VERIFIED"},
        "local package cannot claim an externally verified status",
    )

    if blocking:
        gate_status = "BLOCKED"
    elif assigned < 7:
        gate_status = "PENDING_ASSIGNMENT"
    elif pending:
        gate_status = "PENDING_DECISION"
    else:
        gate_status = "PENDING_EXTERNAL_VERIFICATION"

    return {
        "gate_status": gate_status,
        "frozen_commit_sha": commit_sha,
        "frozen_tree_sha": tree_sha,
        "assigned_count": assigned,
        "approved_count": approved,
        "pending_count": pending,
        "blocking_count": blocking,
        "external_verifier_status": verifier_status,
        "implementation_authorized": False,
        "production_status": "NO-GO",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("review-manifest.json"),
    )
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    repo_root = Path(__file__).resolve().parents[3]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validate_manifest(manifest, repo_root)
    except (OSError, json.JSONDecodeError, ReviewIntakeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"valid": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
