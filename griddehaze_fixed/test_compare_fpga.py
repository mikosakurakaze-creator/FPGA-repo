"""Raw FPGA-dump comparator tests; no board is used."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from .compare_fpga import compare
from .integer import run
from .io import save_tensor, sha256, write_json
from .test_integer import fixture


class RawComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.package = self.root / "package"; self.package.mkdir()
        self.golden = self.root / "golden"; self.golden.mkdir()
        self.manifest, graph = fixture(self.package)
        x = np.random.default_rng(887).integers(-100, 101, (1, 3, 5, 6), dtype=np.int16)
        imeta = save_tensor(self.golden, "input", x)
        imeta["activation_frac"] = 10; write_json(self.golden / "input.json", imeta)
        self.nodes = []
        def observe(name, value, stats):
            self.nodes.append({"id": name, **stats, **save_tensor(self.golden / "nodes", name.replace(".", "_"), value)})
        y = run(self.package, x, observer=observe)
        ometa = save_tensor(self.golden, "output", y)
        ometa["activation_frac"] = 10; write_json(self.golden / "output.json", ometa)
        write_json(self.golden / "report.json", dict(manifest_sha256=sha256(self.package / "manifest.json"), output=ometa, nodes=self.nodes))
        self.actual = self.root / "actual.raw"
        self.actual.write_bytes((self.golden / "output.raw").read_bytes())
        self.bundle = self.manifest["identity"]["bundle_id"]
        self.input_sha = sha256(self.golden / "input.raw")

    def tearDown(self):
        self.temporary.cleanup()

    def compare(self, **kwargs):
        return compare(self.golden, self.actual, self.package, kwargs.pop("bundle_id", self.bundle), **kwargs)

    def test_raw_output_without_candidate_metadata_exact(self):
        report = self.compare(input_sha256=self.input_sha)
        self.assertTrue(report["exact"])
        self.assertTrue(report["candidate_input_identity_verified"])
        self.assertFalse(report["hardware_test"])
        self.assertEqual(report["comparisons"][0]["max_abs_error"], 0)

    def test_undeclared_input_is_explicit(self):
        report = self.compare()
        self.assertTrue(report["exact"])
        self.assertFalse(report["candidate_input_identity_verified"])
        self.assertIsNone(report["candidate_declared_input_sha256"])

    def test_one_lsb_locates_first_nchw_and_error(self):
        y = np.frombuffer(self.actual.read_bytes(), dtype="<i2").copy()
        y[17] += 1; self.actual.write_bytes(y.tobytes())
        report = self.compare()
        self.assertFalse(report["exact"])
        first = report["first_different_tensor"]
        self.assertEqual(first["first_difference_nchw"], [0, 0, 2, 5])
        self.assertEqual(first["max_abs_error"], 1)
        self.assertEqual(first["different_elements"], 1)

    def test_truncation_and_padding_rejected(self):
        original = self.actual.read_bytes()
        for changed in [original[:-1], original + b"\x00\x00"]:
            self.actual.write_bytes(changed)
            report = self.compare()
            self.assertFalse(report["exact"])
            self.assertIn("byte count", report["first_different_tensor"]["reason"])

    def test_identity_and_input_mismatch_rejected_even_equal_bytes(self):
        report = self.compare(bundle_id="0" * 64, input_sha256="1" * 64)
        self.assertFalse(report["exact"])
        self.assertTrue(report["raw_output_exact"])
        self.assertEqual(len(report["errors"]), 2)

    def test_all_nodes_and_first_difference_in_execution_order(self):
        actual_nodes = self.root / "nodes"; actual_nodes.mkdir()
        for node in self.nodes:
            (actual_nodes / node["file"]).write_bytes((self.golden / "nodes" / node["file"]).read_bytes())
        self.assertTrue(self.compare(actual_nodes=actual_nodes)["exact"])
        for node in self.nodes[1:3]:
            path = actual_nodes / node["file"]
            y = np.frombuffer(path.read_bytes(), dtype="<i2").copy()
            y[0] += 1; path.write_bytes(y.tobytes())
        report = self.compare(actual_nodes=actual_nodes)
        self.assertFalse(report["exact"])
        self.assertEqual(report["first_different_tensor"]["tensor"], self.nodes[1]["id"])

    def test_missing_nodes_fail_unless_partial_explicit(self):
        actual_nodes = self.root / "nodes"; actual_nodes.mkdir()
        node = self.nodes[0]
        (actual_nodes / node["file"]).write_bytes((self.golden / "nodes" / node["file"]).read_bytes())
        self.assertFalse(self.compare(actual_nodes=actual_nodes)["exact"])
        report = self.compare(actual_nodes=actual_nodes, allow_partial_nodes=True)
        self.assertTrue(report["exact"])
        self.assertFalse(report["node_coverage_complete"])
        self.assertEqual(report["compared_nodes"], 1)

    def test_corrupt_golden_is_rejected(self):
        with (self.golden / "output.raw").open("ab") as stream:
            stream.write(b"\x00")
        report = self.compare()
        self.assertFalse(report["exact"])
        self.assertIn("Golden raw tensor length/hash", report["errors"][0])

    def test_large_case_hash_only_nodes(self):
        report_path = self.golden / "report.json"
        report = json.loads(report_path.read_text())
        for node in report["nodes"]:
            node.pop("file")
            node["raw_intermediate_saved"] = False
        write_json(report_path, report)
        result = self.compare(actual_nodes=self.golden / "nodes")
        self.assertTrue(result["exact"])
        self.assertEqual(result["comparisons"][0]["comparison"], "sha256_only")
        self.assertIsNone(result["comparisons"][0]["mean_abs_error"])


if __name__ == "__main__":
    unittest.main()
