from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("verify_review_intake.py")
SPEC = importlib.util.spec_from_file_location("airgap_review_intake", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review_intake = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review_intake
SPEC.loader.exec_module(review_intake)


class ReviewIntakeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package_dir = Path(__file__).resolve().parent
        cls.repo_root = cls.package_dir.parents[2]
        cls.manifest = json.loads(
            (cls.package_dir / "review-manifest.json").read_text(encoding="utf-8")
        )

    def test_baseline_is_valid_and_truthfully_zero_of_seven(self) -> None:
        result = review_intake.validate_manifest(
            copy.deepcopy(self.manifest),
            self.repo_root,
            verify_git=True,
        )
        self.assertEqual(result["gate_status"], "PENDING_ASSIGNMENT")
        self.assertEqual(result["assigned_count"], 0)
        self.assertEqual(result["approved_count"], 0)
        self.assertFalse(result["implementation_authorized"])
        self.assertEqual(result["production_status"], "NO-GO")

    def test_missing_domain_fails_closed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["reviews"].pop()
        with self.assertRaises(review_intake.ReviewIntakeError):
            review_intake.validate_manifest(
                manifest,
                self.repo_root,
                verify_git=False,
            )

    def test_ai_reviewer_fails_closed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["reviews"][0]["reviewer_assignment"][
            "reviewer_principal_type"
        ] = "ai"
        with self.assertRaises(review_intake.ReviewIntakeError):
            review_intake.validate_manifest(
                manifest,
                self.repo_root,
                verify_git=False,
            )

    def test_approval_without_identity_fails_closed(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        review = manifest["reviews"][0]
        review["decision"] = "approve"
        review["decision_rationale"] = "Looks correct."
        review["reviewed_at"] = "2026-07-24T12:00:00+08:00"
        review["question_answers"] = {
            key: "satisfied" for key in review["required_question_ids"]
        }
        with self.assertRaises(review_intake.ReviewIntakeError):
            review_intake.validate_manifest(
                manifest,
                self.repo_root,
                verify_git=False,
            )

    def test_wrong_tree_fails_when_git_binding_is_checked(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["target"]["frozen_tree_sha"] = "0" * 40
        with self.assertRaises(review_intake.ReviewIntakeError):
            review_intake.validate_manifest(
                manifest,
                self.repo_root,
                verify_git=True,
            )

    def test_seven_local_approvals_still_wait_for_external_verifier(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        for index, review in enumerate(manifest["reviews"], start=1):
            assignment = review["reviewer_assignment"]
            assignment["reviewer_display_name"] = f"Reviewer {index}"
            assignment["reviewer_actor_id"] = f"idp://employee/{index}"
            assignment["reviewer_role_assignment_ref"] = (
                f"governance://role-assignment/{index}"
            )
            review["decision"] = "approve"
            review["decision_rationale"] = "Satisfied against frozen commit."
            review["reviewed_at"] = f"2026-07-24T12:{index:02d}:00+08:00"
            review["question_answers"] = {
                key: "satisfied" for key in review["required_question_ids"]
            }
        result = review_intake.validate_manifest(
            manifest,
            self.repo_root,
            verify_git=False,
        )
        self.assertEqual(result["assigned_count"], 7)
        self.assertEqual(result["approved_count"], 7)
        self.assertEqual(
            result["gate_status"],
            "PENDING_EXTERNAL_VERIFICATION",
        )
        self.assertFalse(result["implementation_authorized"])

    def test_same_human_multiple_domains_requires_sod_exception(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        for review in manifest["reviews"][:2]:
            assignment = review["reviewer_assignment"]
            assignment["reviewer_display_name"] = "Same Reviewer"
            assignment["reviewer_actor_id"] = "idp://employee/shared"
            assignment["reviewer_role_assignment_ref"] = (
                f"governance://role-assignment/{review['domain_id']}"
            )
        with self.assertRaises(review_intake.ReviewIntakeError):
            review_intake.validate_manifest(
                manifest,
                self.repo_root,
                verify_git=False,
            )


if __name__ == "__main__":
    unittest.main()
