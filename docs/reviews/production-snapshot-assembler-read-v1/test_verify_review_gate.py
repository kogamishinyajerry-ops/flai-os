from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("verify_review_gate.py")
SPEC = importlib.util.spec_from_file_location("snapshot_review_gate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review_gate
SPEC.loader.exec_module(review_gate)


class ReviewGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)
        self.package_dir = (
            temp_root
            / "docs"
            / "reviews"
            / "production-snapshot-assembler-read-v1"
        )
        shutil.copytree(Path(__file__).resolve().parent, self.package_dir)
        source_contract = (
            Path(__file__).resolve().parent
            / "../../product/FLAi-OS_V0.2_Design_Package"
            / "16_Production_Snapshot_Assembler_Read_Contract.md"
        ).resolve()
        target_contract_dir = (
            temp_root / "docs" / "product" / "FLAi-OS_V0.2_Design_Package"
        )
        target_contract_dir.mkdir(parents=True)
        shutil.copy2(
            source_contract,
            target_contract_dir
            / "16_Production_Snapshot_Assembler_Read_Contract.md",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, value: dict) -> None:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _manifest_path(self) -> Path:
        return self.package_dir / "review-manifest.json"

    def _configure_and_approve_all(self) -> dict:
        manifest = self._read_json(self._manifest_path())
        manifest["review_plan_status"] = "FROZEN-FOR-REVIEW"
        verifier = manifest["external_trust_verifier"]
        verifier.update(
            {
                "status": "REFERENCED-NOT-VERIFIED",
                "verifier_binding_ref": "verifier://organization/review-v1",
                "trusted_actor_registry_ref": "idp://organization/actors/v1",
                "trusted_role_assignment_registry_ref": (
                    "governance://organization/role-assignments/v1"
                ),
                "trusted_signature_or_audit_policy_ref": (
                    "trust-policy://organization/contract-review/v1"
                ),
                "trusted_finding_registry_ref": (
                    "finding-registry://organization/contract-review/v1"
                ),
                "append_only_decision_ledger_ref": (
                    "audit-ledger://organization/contract-review/v1"
                ),
            }
        )
        for index, entry in enumerate(manifest["reviews"], start=1):
            entry["reviewer_assignment"].update(
                {
                    "reviewer_display_name": f"Reviewer {index}",
                    "reviewer_actor_id": f"idp://employee/{1000 + index}",
                    "reviewer_role_assignment_ref": (
                        f"governance://role-assignment/{index}"
                    ),
                }
            )
        self._write_json(self._manifest_path(), manifest)
        plan_digest = review_gate._sha256_ref(self._manifest_path())

        for index, entry in enumerate(manifest["reviews"], start=1):
            assignment = entry["reviewer_assignment"]
            core_path = self.package_dir / entry["decision_core_path"]
            core = self._read_json(core_path)
            core.update(
                {
                    "decision_id": f"decision://psa-read-v1-r1/{index}",
                    "review_plan_digest": plan_digest,
                    "reviewer_display_name": assignment["reviewer_display_name"],
                    "reviewer_actor_id": assignment["reviewer_actor_id"],
                    "reviewer_role_assignment_ref": assignment[
                        "reviewer_role_assignment_ref"
                    ],
                    "decision": "approve",
                    "reviewed_at": f"2026-07-23T10:{index:02d}:00+08:00",
                    "open_blocking_findings_count": 0,
                }
            )
            for answer in core["review_answers"]:
                answer["answer"] = "satisfied"
                answer["rationale"] = (
                    "Confirmed against the exact frozen contract bytes."
                )
            self._write_json(core_path, core)

            seal_path = self.package_dir / entry["decision_seal_path"]
            seal = self._read_json(seal_path)
            seal.update(
                {
                    "decision_core_digest": review_gate._sha256_ref(core_path),
                    "reviewer_actor_id": assignment["reviewer_actor_id"],
                    "credential_or_audit_actor_id": (
                        f"credential://employee/{1000 + index}"
                    ),
                    "actor_credential_binding_ref": (
                        f"idp-binding://employee/{1000 + index}"
                    ),
                    "evidence_kind": "immutable_audit_receipt",
                    "key_usage_or_audit_event_type": "contract-review",
                    "signature_or_audit_evidence_ref": (
                        f"audit://contract-review/{index}"
                    ),
                    "trusted_timestamp": (
                        f"2026-07-23T10:{index:02d}:01+08:00"
                    ),
                    "trust_policy_ref": verifier[
                        "trusted_signature_or_audit_policy_ref"
                    ],
                    "trust_verification_receipt_ref": (
                        f"verification://contract-review/{index}"
                    ),
                }
            )
            self._write_json(seal_path, seal)
        return manifest

    def test_pending_pack_has_valid_structure_and_closed_gate(self) -> None:
        result = review_gate.evaluate(self.package_dir)

        self.assertEqual((), result.structure_errors)
        self.assertEqual("PENDING", result.contract_review)
        self.assertGreater(len(result.approval_blockers), 0)
        self.assertFalse(result.eligible_for_separate_implementation_slice)
        self.assertFalse(result.implementation_authorized)

    def test_seven_bound_records_still_require_external_verification(self) -> None:
        self._configure_and_approve_all()

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual((), result.structure_errors)
        self.assertEqual(
            (review_gate.EXTERNAL_TRUST_BLOCKER,),
            result.approval_blockers,
        )
        self.assertEqual(
            "PENDING_EXTERNAL_VERIFICATION",
            result.contract_review,
        )
        self.assertTrue(result.local_review_records_complete)
        self.assertFalse(result.eligible_for_separate_implementation_slice)
        self.assertFalse(result.implementation_authorized)

    def test_contract_byte_change_invalidates_structure(self) -> None:
        contract_path = (
            self.package_dir
            / "../../product/FLAi-OS_V0.2_Design_Package"
            / "16_Production_Snapshot_Assembler_Read_Contract.md"
        ).resolve()
        contract_path.write_text(
            contract_path.read_text(encoding="utf-8") + "\nchanged\n",
            encoding="utf-8",
        )

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertTrue(
            any(
                error.startswith("frozen contract SHA-256 mismatch")
                for error in result.structure_errors
            )
        )

    def test_plan_change_after_signing_invalidates_all_core_bindings(self) -> None:
        self._configure_and_approve_all()
        manifest = self._read_json(self._manifest_path())
        manifest["reviews"][0]["reviewer_assignment"][
            "reviewer_role_assignment_ref"
        ] += ".changed"
        self._write_json(self._manifest_path(), manifest)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual((), result.structure_errors)
        self.assertTrue(
            any(
                blocker.endswith("review_plan_digest does not match plan")
                for blocker in result.approval_blockers
            )
        )
        self.assertFalse(result.eligible_for_separate_implementation_slice)

    def test_question_prompt_cannot_be_replaced_by_short_id_only(self) -> None:
        manifest = self._read_json(self._manifest_path())
        manifest["question_catalog"]["COMMON-01"] = "同意"
        self._write_json(self._manifest_path(), manifest)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertIn(
            "manifest.question_catalog does not match the frozen prompts",
            result.structure_errors,
        )

    def test_frozen_identity_metadata_is_exact(self) -> None:
        original = self._read_json(self._manifest_path())
        cases = (
            (("review_package_id",), ""),
            (("target", "freeze_status"), "MUTABLE"),
            (("target", "implementation_status"), "PRODUCTION-IMPLEMENTED"),
            (("target", "byte_length"), 74878.0),
            (("gate_policy", "all_domains_required"), 1),
        )
        for path, replacement in cases:
            with self.subTest(path=path):
                manifest = copy.deepcopy(original)
                target = manifest
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                self._write_json(self._manifest_path(), manifest)

                result = review_gate.evaluate(self.package_dir)

                self.assertEqual("INVALID", result.contract_review)
                self.assertGreater(len(result.structure_errors), 0)
        self._write_json(self._manifest_path(), original)

    def test_decision_revision_rejects_bool_and_float_aliases(self) -> None:
        manifest = self._read_json(self._manifest_path())
        core_path = self.package_dir / manifest["reviews"][0]["decision_core_path"]
        original = self._read_json(core_path)
        for replacement in (True, 1.0):
            with self.subTest(replacement=replacement):
                core = copy.deepcopy(original)
                core["decision_revision"] = replacement
                self._write_json(core_path, core)

                result = review_gate.evaluate(self.package_dir)

                self.assertEqual("INVALID", result.contract_review)
                self.assertTrue(
                    any(
                        "decision_revision must be 1" in error
                        for error in result.structure_errors
                    )
                )
        self._write_json(core_path, original)

    def test_approve_words_without_complete_records_remain_pending(self) -> None:
        manifest = self._read_json(self._manifest_path())
        for entry in manifest["reviews"]:
            core_path = self.package_dir / entry["decision_core_path"]
            core = self._read_json(core_path)
            core["decision"] = "approve"
            self._write_json(core_path, core)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("PENDING", result.contract_review)
        self.assertFalse(result.local_review_records_complete)
        self.assertFalse(result.eligible_for_separate_implementation_slice)

    def test_decision_core_byte_change_breaks_seal_binding(self) -> None:
        manifest = self._configure_and_approve_all()
        entry = manifest["reviews"][0]
        core_path = self.package_dir / entry["decision_core_path"]
        core_path.write_text(
            core_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )

        result = review_gate.evaluate(self.package_dir)

        self.assertIn(
            "control-kernel-architecture: seal does not bind the exact "
            "decision core bytes",
            result.approval_blockers,
        )

    def test_core_parse_and_digest_use_the_same_bytes(self) -> None:
        manifest = self._configure_and_approve_all()
        entry = manifest["reviews"][0]
        core_path = (self.package_dir / entry["decision_core_path"]).resolve()
        seal_path = self.package_dir / entry["decision_seal_path"]
        original_core_bytes = core_path.read_bytes()
        replacement_core = json.loads(original_core_bytes.decode("utf-8"))
        replacement_core["decision"] = "reject"
        replacement_core_bytes = (
            json.dumps(replacement_core, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        replacement_digest = (
            "sha256:" + hashlib.sha256(replacement_core_bytes).hexdigest()
        )
        seal = self._read_json(seal_path)
        seal["decision_core_digest"] = replacement_digest
        self._write_json(seal_path, seal)

        original_loader = review_gate._load_json_snapshot
        swapped = False

        def swapping_loader(path: Path):
            nonlocal swapped
            snapshot = original_loader(path)
            if path.resolve() == core_path and not swapped:
                core_path.write_bytes(replacement_core_bytes)
                swapped = True
            return snapshot

        review_gate._load_json_snapshot = swapping_loader
        try:
            result = review_gate.evaluate(self.package_dir)
        finally:
            review_gate._load_json_snapshot = original_loader

        self.assertIn(
            "control-kernel-architecture: seal does not bind the exact "
            "decision core bytes",
            result.approval_blockers,
        )
        self.assertFalse(result.local_review_records_complete)

    def test_round_one_cannot_claim_a_previous_decision(self) -> None:
        manifest = self._read_json(self._manifest_path())
        core_path = self.package_dir / manifest["reviews"][0]["decision_core_path"]
        core = self._read_json(core_path)
        core["previous_decision_core_digest"] = "sha256:" + "0" * 64
        self._write_json(core_path, core)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertTrue(
            any(
                "previous_decision_core_digest must be null in round 1" in error
                for error in result.structure_errors
            )
        )

    def test_duplicate_json_key_is_rejected(self) -> None:
        manifest = self._read_json(self._manifest_path())
        core_path = self.package_dir / manifest["reviews"][0]["decision_core_path"]
        raw = core_path.read_text(encoding="utf-8")
        raw = raw.replace(
            '"decision": "pending",',
            '"decision": "pending",\n  "decision": "approve",',
            1,
        )
        core_path.write_text(raw, encoding="utf-8")

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertTrue(
            any(
                "duplicate JSON object key" in error
                for error in result.structure_errors
            )
        )

    def test_review_artifact_path_cannot_escape_package(self) -> None:
        manifest = self._read_json(self._manifest_path())
        manifest["reviews"][0]["decision_core_path"] = "../outside.json"
        self._write_json(self._manifest_path(), manifest)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertTrue(
            any(
                "paths must stay inside the review package" in error
                for error in result.structure_errors
            )
        )

    def test_review_artifact_symlink_is_rejected(self) -> None:
        manifest = self._read_json(self._manifest_path())
        core_path = self.package_dir / manifest["reviews"][0]["decision_core_path"]
        outside_path = self.package_dir.parent / "outside-core.json"
        outside_path.write_bytes(core_path.read_bytes())
        core_path.unlink()
        core_path.symlink_to(outside_path)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual("INVALID", result.contract_review)
        self.assertTrue(
            any(
                "decision core/seal must not be symlinks" in error
                for error in result.structure_errors
            )
        )

    def test_duplicate_actor_requires_explicit_sod_exception(self) -> None:
        manifest = self._read_json(self._manifest_path())
        manifest["review_plan_status"] = "FROZEN-FOR-REVIEW"
        duplicate_actor = "idp://employee/1001"
        for index, entry in enumerate(manifest["reviews"], start=1):
            assignment = entry["reviewer_assignment"]
            assignment["reviewer_display_name"] = f"Reviewer {index}"
            assignment["reviewer_actor_id"] = (
                duplicate_actor if index < 3 else f"idp://employee/{1000 + index}"
            )
            assignment["reviewer_role_assignment_ref"] = (
                f"governance://role-assignment/{index}"
            )
        self._write_json(self._manifest_path(), manifest)

        result = review_gate.evaluate(self.package_dir)

        self.assertTrue(
            any(
                "segregation-of-duties exception" in blocker
                for blocker in result.approval_blockers
            )
        )

    def test_decision_ids_must_be_unique_across_domains(self) -> None:
        manifest = self._configure_and_approve_all()
        first_entry = manifest["reviews"][0]
        first_core = self._read_json(
            self.package_dir / first_entry["decision_core_path"]
        )
        duplicate_id = first_core["decision_id"]
        for entry in manifest["reviews"][1:]:
            core_path = self.package_dir / entry["decision_core_path"]
            core = self._read_json(core_path)
            core["decision_id"] = duplicate_id
            self._write_json(core_path, core)
            seal_path = self.package_dir / entry["decision_seal_path"]
            seal = self._read_json(seal_path)
            seal["decision_core_digest"] = review_gate._sha256_ref(core_path)
            self._write_json(seal_path, seal)

        result = review_gate.evaluate(self.package_dir)

        self.assertTrue(
            any(
                "decision_id duplicates control-kernel-architecture" in blocker
                for blocker in result.approval_blockers
            )
        )
        self.assertFalse(result.local_review_records_complete)

    def test_changes_required_remains_fail_closed(self) -> None:
        manifest = self._configure_and_approve_all()
        entry = manifest["reviews"][3]
        core_path = self.package_dir / entry["decision_core_path"]
        core = self._read_json(core_path)
        core["decision"] = "changes_required"
        core["review_answers"][1]["answer"] = "unsatisfied"
        core["review_answers"][1]["finding_refs"] = [
            "finding://snapshot-contract/crypto-001"
        ]
        core["open_blocking_findings_count"] = 1
        self._write_json(core_path, core)
        seal_path = self.package_dir / entry["decision_seal_path"]
        seal = self._read_json(seal_path)
        seal["decision_core_digest"] = review_gate._sha256_ref(core_path)
        self._write_json(seal_path, seal)

        result = review_gate.evaluate(self.package_dir)

        self.assertEqual((), result.structure_errors)
        self.assertEqual("CHANGES_REQUIRED", result.contract_review)
        self.assertGreater(len(result.approval_blockers), 0)
        self.assertFalse(result.eligible_for_separate_implementation_slice)
        self.assertFalse(result.implementation_authorized)


if __name__ == "__main__":
    unittest.main()
