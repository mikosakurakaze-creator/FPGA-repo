"""Portable package integrity and rejection paths; never connects to hardware."""
from pathlib import Path
import copy
import tempfile
import tkinter
import unittest
from prepare_payloads import ROOT, digest, load, read_assets, tcl_value, validate_layout


class HostOnlyTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load(ROOT / "manifest.json")
        self.plan = load(ROOT / "single_frame_plan.json")

    def test_frozen_library_bytes_and_source_has_no_automatic_hardware_calls(self):
        t = tkinter.Tcl()
        for name, rec in self.manifest["libraries"].items():
            p = ROOT / name
            raw = p.read_bytes()
            self.assertEqual((len(raw), digest(raw)), (rec["bytes"], rec["sha256"]))
            if p.suffix == ".tcl":
                t.call("source", p.as_posix())
        self.assertEqual(t.eval("info commands ::single_frame::run"), "::single_frame::run")

    def test_six_small_samples_decode_to_frozen_identities(self):
        small = [v for v in self.manifest["assets"].values() if "included_hex" in v]
        self.assertEqual(len(small), 6)
        for r in small:
            raw = bytes.fromhex((ROOT / r["included_hex"]).read_text(encoding="ascii"))
            self.assertEqual((len(raw), digest(raw)), (r["bytes"], r["sha256"]))

    def test_full_layout_is_bounded(self):
        validate_layout(self.plan, self.manifest["regions"])

    def test_overlap_and_out_of_range_are_rejected(self):
        for mode in ("overlap", "outside", "length"):
            regions = copy.deepcopy(self.manifest["regions"])
            regions[1]["address"] = regions[0]["address"] if mode == "overlap" else 0x24000000
            if mode == "length":
                regions[1]["bytes"] = 0
            with self.assertRaises(ValueError):
                validate_layout(self.plan, regions)

    def test_corrupt_supplied_asset_is_not_silently_replaced_by_sample(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "input_q14.bin").write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                read_assets(Path(d), self.manifest)

    def test_missing_large_asset_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(FileNotFoundError, "expected_a_full_q14"):
                read_assets(Path(d), self.manifest)

    def test_tcl_data_is_literal_even_with_special_path_characters(self):
        t = tkinter.Tcl()
        value = {"file": 'x $env(HOME) [error BAD] "quoted" \\ a', "n": 64}
        t.eval("set policy " + tcl_value(value))
        self.assertEqual(t.eval("dict get $policy file"), value["file"])

    def test_single_frame_approval_and_consumed_attempt_stop_before_callbacks(self):
        t = tkinter.Tcl()
        t.call("source", (ROOT / "single_frame_candidate.tcl").as_posix())
        t.eval('set calls 0; proc reject_gate {label} {incr ::calls; error STOP}')
        with self.assertRaisesRegex(tkinter.TclError, "APPROVAL_OR_ONCE"):
            t.eval("::single_frame::run WRONG {} unused unused unused unused reject_gate unused unused unused")
        self.assertEqual(int(t.getvar("calls")), 0)
        with self.assertRaisesRegex(tkinter.TclError, "STOP"):
            t.eval("::single_frame::run MASTER_APPROVED_SINGLE_FRAME_ONCE {} unused unused unused unused reject_gate unused unused unused")
        with self.assertRaisesRegex(tkinter.TclError, "APPROVAL_OR_ONCE"):
            t.eval("::single_frame::run MASTER_APPROVED_SINGLE_FRAME_ONCE {} unused unused unused unused reject_gate unused unused unused")
        self.assertEqual(int(t.getvar("calls")), 1)


if __name__ == "__main__":
    unittest.main()
