"""Host-only plan/budget checks; no transport or board runner is imported."""
import copy
import json
from pathlib import Path
import unittest

from prepare_repeat_plan import audit_two_frame_budget, scope_digest, EXPECTED_SCOPE_SHA, SHARED

ROOT = Path(__file__).resolve().parent


class PlanChecks(unittest.TestCase):
    def setUp(self):
        self.candidate = json.loads((ROOT / "repeat_2frame_plan.json").read_text(encoding="utf-8"))

    def test_frozen_public_semantics(self):
        plan = json.loads((SHARED / "single_frame_plan.json").read_text(encoding="utf-8"))
        self.assertEqual(scope_digest(plan), EXPECTED_SCOPE_SHA)
        audit_two_frame_budget(self.candidate)
        self.assertEqual(self.candidate["board_operations_this_tool"], 0)
        self.assertEqual(self.candidate["BOARD_30FPS"], "NOT_TESTED")

    def test_extra_frame_rejected(self):
        self.candidate["frames"].append(copy.deepcopy(self.candidate["frames"][0]))
        with self.assertRaisesRegex(ValueError, "Frame budget"):
            audit_two_frame_budget(self.candidate)

    def test_extra_start_rejected(self):
        self.candidate["frames"][1]["schedule"][0]["start"]["attempts"] = 2
        with self.assertRaisesRegex(ValueError, "Start budget"):
            audit_two_frame_budget(self.candidate)

    def test_removed_parameter_rejected(self):
        self.candidate["frames"][1]["schedule"][0]["argument_writes"].pop()
        with self.assertRaisesRegex(ValueError, "budget"):
            audit_two_frame_budget(self.candidate)

    def test_modified_input_scope_detected(self):
        plan = json.loads((SHARED / "single_frame_plan.json").read_text(encoding="utf-8"))
        plan["schedule"][0]["argument_writes"][0]["value"] = "0x24000000"
        self.assertNotEqual(scope_digest(plan), EXPECTED_SCOPE_SHA)


if __name__ == "__main__":
    unittest.main()
