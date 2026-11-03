"""Negative checks for the hold ECO evidence parser; no vendor process runs."""
from pathlib import Path
import tempfile
import unittest
from audit_timing_variant import hold_eco_rows, cell_snapshot, relocation_rows, floorplan_rows, placement_trial_rows, register_parameter_rows
from verify_timing_margin import xdc_commands
from optimize_timing_margin import placement_diagnostics


class HoldEvidenceTests(unittest.TestCase):
    def parameters(self, rows='r\t0\t0\t0\t0\n', expected=('r',)):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'parameters.tsv'
            p.write_text('cell\tINIT\tIS_C_INVERTED\tIS_D_INVERTED\tIS_R_INVERTED\n'+rows)
            return register_parameter_rows(p, expected)

    def test_register_parameters(self):
        self.assertEqual(self.parameters(), {'r':('0','0','0','0')})

    def test_register_parameter_change_is_visible(self):
        self.assertNotEqual(self.parameters('r\t0\t0\t1\t0\n'), self.parameters())

    def test_register_parameter_unknown_is_rejected(self):
        with self.assertRaises(ValueError):
            self.parameters('r\tX\t0\t0\t0\n')

    def test_register_parameter_duplicate_is_rejected(self):
        with self.assertRaises(ValueError):
            self.parameters('r\t0\t0\t0\t0\nr\t0\t0\t0\t0\n')

    def test_register_parameter_missing_is_rejected(self):
        with self.assertRaises(ValueError):
            self.parameters(expected=('r','s'))

    def test_raw_rejected_candidate_message_is_preserved(self):
        raw='PLACEMENT_TRIAL_BEGIN\tr\tSLICE_X1Y2/AFF\nERROR: [Vivado 12-1409] Routing contention\nPLACEMENT_TRIAL_END\t1\n'
        self.assertEqual(placement_diagnostics(raw)[0]['error_ids'], ['Vivado 12-1409'])

    def test_real_error_outside_trial_is_rejected(self):
        with self.assertRaises(ValueError):
            placement_diagnostics('ERROR: [Vivado 12-1409] Final failure\n')

    def test_unexpected_error_inside_trial_is_rejected(self):
        with self.assertRaises(ValueError):
            placement_diagnostics('PLACEMENT_TRIAL_BEGIN\tr\tSLICE_X1Y2/AFF\nERROR: [Place 30-99] Failure\nPLACEMENT_TRIAL_END\t1\n')

    def test_error_in_accepted_trial_is_rejected(self):
        with self.assertRaises(ValueError):
            placement_diagnostics('PLACEMENT_TRIAL_BEGIN\tr\tSLICE_X1Y2/AFF\nERROR: [Vivado 12-1409] Failure\nPLACEMENT_TRIAL_END\t0\n')

    def test_incomplete_trial_is_rejected(self):
        with self.assertRaises(ValueError):
            placement_diagnostics('PLACEMENT_TRIAL_BEGIN\tr\tSLICE_X1Y2/AFF\n')

    def trials(self, diagnostic='ERROR: [Vivado 12-1409] Cannot set LOC', accepted_site='SLICE_X2Y2', state='REJECTED'):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'trials.tsv'
            p.write_text('cell\ttarget\tstatus\tdiagnostics\n'
                f'r\tSLICE_X1Y2/AFF\t{state}\t{diagnostic}\n'
                f'r\t{accepted_site}/AFF\tACCEPTED\t\n')
            return placement_trial_rows(p, {'r':('r/D','SLICE_X1Y2','SLICE_X2Y2')})

    def test_expected_candidate_rejection_is_retained(self):
        self.assertEqual(self.trials()['rejected_bel_attempts'], 1)

    def test_unexpected_candidate_error_is_rejected(self):
        with self.assertRaises(ValueError):
            self.trials(diagnostic='ERROR: [Place 30-99] Failure')

    def test_candidate_silent_failure_is_rejected(self):
        with self.assertRaises(ValueError):
            self.trials(diagnostic='')

    def test_wrong_accepted_location_is_rejected(self):
        with self.assertRaises(ValueError):
            self.trials(accepted_site='SLICE_X3Y2')

    def test_incomplete_restoration_is_rejected_for_final_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'constraints.xdc'
            p.write_text('set_clock_uncertainty -setup 0.3 [get_clocks]\nset_clock_uncertainty -hold 0.1 [get_clocks]\n')
            self.assertEqual(xdc_commands(p, True, (0.3,0.1), require_restoration=False), [])
            with self.assertRaises(ValueError):
                xdc_commands(p, True, (0.3,0.1))

    def parse(self, text):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'proof.tsv'
            p.write_text(text)
            return hold_eco_rows(p)

    def proof(self, init="2'h2", controls='PASS', footer='1'):
        return ('buffer\tendpoint\tidentity_init\tconnections\tcontrols\n'
                f'fifo/buf\tfifo/reg/D\t{init}\tPASS\t{controls}\n'
                f'VERIFIED_IDENTITY_BUFFERS={footer}\n')

    def test_identity(self):
        self.assertEqual(self.parse(self.proof()), {'fifo/buf':'fifo/reg/D'})

    def test_inversion_rejected(self):
        with self.assertRaises(ValueError):
            self.parse(self.proof(init="2'h1"))

    def test_changed_enable_rejected(self):
        with self.assertRaises(ValueError):
            self.parse(self.proof(controls='FAIL'))

    def test_missing_rows_rejected(self):
        with self.assertRaises(ValueError):
            self.parse(self.proof(footer='2'))

    def test_duplicate_buffer_rejected(self):
        lines = self.proof(footer='2').splitlines()
        lines.insert(2, lines[1])
        with self.assertRaises(ValueError):
            self.parse('\n'.join(lines))

    def test_duplicate_original_primitive_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'cells.tsv'
            p.write_text('r\tFDRE\nr\tLUT1\n')
            with self.assertRaises(ValueError):
                cell_snapshot(p)

    def relocation(self, row='r\tr/D\tSLICE_X1Y2\tSLICE_X2Y2\tPASS', footer=1):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'relocation.tsv'
            p.write_text('cell\tendpoint\told_site\tnew_site\tconnections\n'+row+'\nVERIFIED_RELOCATED_REGISTERS='+str(footer)+'\n')
            return relocation_rows(p)

    def test_relocation(self):
        self.assertEqual(self.relocation(), {'r':('r/D','SLICE_X1Y2','SLICE_X2Y2')})

    def test_relocation_same_site_rejected(self):
        with self.assertRaises(ValueError):
            self.relocation('r\tr/D\tSLICE_X1Y2\tSLICE_X1Y2\tPASS')

    def test_relocation_changed_connection_rejected(self):
        with self.assertRaises(ValueError):
            self.relocation('r\tr/D\tSLICE_X1Y2\tSLICE_X2Y2\tFAIL')

    def test_relocation_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            self.relocation('r\tr/D\tSLICE_X1Y2\tSLICE_X2Y2\tPASS\nr\tr/D\tSLICE_X1Y2\tSLICE_X2Y2\tPASS', 2)

    def test_relocation_incomplete_rejected(self):
        with self.assertRaises(ValueError):
            self.relocation(footer=2)

    def floorplan(self, row='r\tSLICE_X2Y2\tFDRE\tPASS', footer=1):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'floorplan.tsv'
            p.write_text('cell\tsite\ttype\tconnections\n'+row+'\nVERIFIED_FLOORPLAN_REGISTERS='+str(footer)+'\n')
            return floorplan_rows(p)

    def test_floorplan(self):
        self.assertEqual(self.floorplan(), {'r':'SLICE_X2Y2'})

    def test_floorplan_wrong_primitive_rejected(self):
        with self.assertRaises(ValueError):
            self.floorplan('r\tSLICE_X2Y2\tLUT1\tPASS')

    def test_floorplan_changed_connection_rejected(self):
        with self.assertRaises(ValueError):
            self.floorplan('r\tSLICE_X2Y2\tFDRE\tFAIL')

    def test_floorplan_incomplete_rejected(self):
        with self.assertRaises(ValueError):
            self.floorplan(footer=2)


if __name__ == '__main__':
    unittest.main()
