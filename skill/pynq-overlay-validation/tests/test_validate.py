"""Behavioral Host checks. Temporary files only; no PYNQ dependency."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pynq_skill_validate", ROOT / "scripts" / "validate.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = validator.load_json(ROOT / "assets" / "mmio-master.example.json")

    def rejected(self, contract):
        with self.assertRaises(validator.ValidationError):
            validator.check_contract(contract)

    def test_both_transport_profiles_and_metadata_inventory(self):
        for example in ("mmio-master.example.json", "axi-dma.example.json"):
            c = validator.load_json(ROOT / "assets" / example)
            inventory = {"ip_dict": {}}
            if c["ip"].get("addressable", True):
                inventory["ip_dict"][c["ip"]["name"]] = {"type": c["ip"]["vlnv"], "addr_range": c["ip"]["addr_range"]}
            if c["transport"]["kind"] == "axi-stream-dma":
                inventory["ip_dict"]["axi_dma_0"] = {"type": "xilinx.com:ip:axi_dma:7.1"}
            result = validator.check_contract(c, inventory)
            self.assertTrue(result["inventory_checked"])
            self.assertFalse(result["board_validated"])
            self.assertEqual(result["accelerator_inventory_checked"], c["ip"].get("addressable", True))
            with self.assertRaises(validator.ValidationError):
                validator.check_contract(c, {"ip_dict": {}})

    def test_shape_dtype_and_layout_must_agree(self):
        for key, value in (("nbytes", 31), ("dtype", "uint32"), ("layout", "NHWC"), ("shape", [True]), ("shape", [0])):
            c = copy.deepcopy(self.contract)
            c["buffers"][0][key] = value
            self.rejected(c)

    def test_alignment_guards_and_cache_policy(self):
        for key, value in (("alignment_bytes", 3), ("guard_bytes", 3), ("cache_policy", "assume-coherent")):
            c = copy.deepcopy(self.contract)
            c["buffers"][0][key] = value
            self.rejected(c)

    def test_register_width_bounds_and_aliasing(self):
        for low in (2, 256, 0, 24):
            c = copy.deepcopy(self.contract)
            c["transport"]["pointer_registers"]["input"]["low"] = low
            self.rejected(c)
        c = copy.deepcopy(self.contract)
        c["transport"]["address_bits"] = 64
        self.rejected(c)
        c["transport"]["pointer_registers"]["input"]["high"] = 20
        c["transport"]["pointer_registers"]["output"]["high"] = 28
        self.assertEqual(validator.check_contract(c)["status"], "HOST_CONTRACT_PASS")

    def test_timeout_is_finite_and_not_an_integer_flag(self):
        for timeout in (0, -1, True, float("nan"), float("inf")):
            c = copy.deepcopy(self.contract)
            c["control"]["timeout_s"] = timeout
            self.rejected(c)

    def test_dma_size_and_alignment_limits(self):
        c = validator.load_json(ROOT / "assets" / "axi-dma.example.json")
        c["transport"]["max_transfer_bytes"] = 31
        self.rejected(c)
        c["transport"]["max_transfer_bytes"] = 16383
        c["transport"]["address_alignment_bytes"] = 8
        self.rejected(c)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pynq-skill-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        validator.create_demo(self.root)
        self.c = validator.load_json(self.root / "contract.json")
        self.bundle = validator.load_json(self.root / "run.json")

    def compare(self):
        return validator.compare_bundle(self.c, self.bundle, self.root, require_ab=True)

    def test_full_ab_demo_passes_without_board_claim(self):
        result = self.compare()
        self.assertEqual(result["status"], "HOST_FILES_PASS")
        self.assertEqual(sum(r["outputs"][0]["bytes_compared"] for r in result["frames"]), 64)
        self.assertFalse(result["board_validated"])
        with self.assertRaises(validator.ValidationError):
            validator.create_demo(self.root)

    def test_one_stale_word_and_truncation_are_rejected(self):
        path = self.root / "B_actual.bin"
        original = path.read_bytes()
        path.write_bytes((self.root / "A_actual.bin").read_bytes()[:4] + original[4:])
        with self.assertRaises(validator.ValidationError):
            self.compare()
        path.write_bytes(original[:-1])
        with self.assertRaises(validator.ValidationError):
            self.compare()

    def test_tail_word_and_guard_corruption_are_rejected(self):
        path = self.root / "A_actual.bin"
        original = path.read_bytes()
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaises(validator.ValidationError):
            self.compare()
        path.write_bytes(original)
        for side in ("before", "after"):
            guard = self.root / ("A_" + side + ".bin")
            guard.write_bytes(b"Z" * 63 + b"X")
            with self.assertRaises(validator.ValidationError):
                self.compare()
            guard.write_bytes(b"Z" * 64)

    def test_wrong_golden_sha_and_poison_collision_are_rejected(self):
        record = self.bundle["frames"][0]["outputs"]["output"]
        original_sha = record["golden_sha256"]
        record["golden_sha256"] = "0" * 64
        with self.assertRaises(validator.ValidationError):
            self.compare()
        record["golden_sha256"] = original_sha
        record["poison_hex"] = "00000000"
        with self.assertRaises(validator.ValidationError):
            self.compare()

    def test_ab_identical_inputs_or_outputs_are_rejected(self):
        second = self.bundle["frames"][1]
        original_input = second["inputs"]["input"]
        second["inputs"]["input"] = "A_input.bin"
        with self.assertRaises(validator.ValidationError):
            self.compare()
        second["inputs"]["input"] = original_input
        second["outputs"]["output"] = copy.deepcopy(self.bundle["frames"][0]["outputs"]["output"])
        with self.assertRaises(validator.ValidationError):
            self.compare()

    def test_missing_output_samefile_and_escaping_paths_are_rejected(self):
        record = self.bundle["frames"][0]["outputs"]["output"]
        for field, value in (("actual", "A_golden.bin"), ("actual", "../escape.bin")):
            old = record[field]
            record[field] = value
            with self.assertRaises(validator.ValidationError):
                self.compare()
            record[field] = old
        self.bundle["frames"][0]["outputs"] = {}
        with self.assertRaises(validator.ValidationError):
            self.compare()


    def test_guard_aliases_and_hardlinks_are_rejected(self):
        record = self.bundle["frames"][0]["outputs"]["output"]
        (self.root / "A_after.bin").write_bytes(b"X" * 64)
        record["guard_after"] = record["guard_before"]
        with self.assertRaises(validator.ValidationError):
            self.compare()
        alias = self.root / "A_guard_hardlink.bin"
        os.link(self.root / record["guard_before"], alias)
        record["guard_after"] = alias.name
        with self.assertRaises(validator.ValidationError):
            self.compare()

    def test_multiple_equal_outputs_require_independent_actual_and_guard_snapshots(self):
        second_buffer = copy.deepcopy(self.c["buffers"][1])
        second_buffer["name"] = "output2"
        self.c["buffers"].append(second_buffer)
        self.c["transport"]["pointer_registers"]["output2"] = {"low": 32}
        for frame in self.bundle["frames"]:
            first = frame["outputs"]["output"]
            second = copy.deepcopy(first)
            for field in ("actual", "guard_before", "guard_after"):
                original = self.root / first[field]
                copied = self.root / ("second_" + first[field])
                copied.write_bytes(original.read_bytes())
                second[field] = copied.name
            frame["outputs"]["output2"] = second
        self.assertEqual(self.compare()["status"], "HOST_FILES_PASS")
        first = self.bundle["frames"][0]["outputs"]["output"]
        second = self.bundle["frames"][0]["outputs"]["output2"]
        (self.root / second["actual"]).write_bytes(b"\xa5" * 32)
        second["actual"] = first["actual"]
        with self.assertRaises(validator.ValidationError):
            self.compare()
        alias = self.root / "actual_hardlink.bin"
        os.link(self.root / first["actual"], alias)
        second["actual"] = alias.name
        with self.assertRaises(validator.ValidationError):
            self.compare()


if __name__ == "__main__":
    unittest.main()
