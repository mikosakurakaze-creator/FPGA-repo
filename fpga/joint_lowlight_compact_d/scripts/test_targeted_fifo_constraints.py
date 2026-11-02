"""Positive/negative checks for the exact four-R-FIFO provenance exception."""
import unittest

from targeted_fifo_constraint_contract import BRAM_KEYS, compare_targeted_compiled, provenance_pairs


def fixture():
    old, new = [], []
    for i, (first, second) in enumerate(provenance_pairs(sorted(BRAM_KEYS)), 1):
        for lines, source, numbers in ((old, first, [*range(1, 47), 49, 53, 67]),
                                       (new, second, [*range(1, 47), 49, 56, 57])):
            lines.append(source.replace('id:ENUMERATION', f'id:{i}'))
            lines.extend(f'set_property src_info {{type:SCOPED_XDC file:{i} line:{n} export:INPUT save:NONE read:READ}} [current_design]' for n in numbers)
    for lines in (old, new):
        lines.extend(['create_clock -period 10 [get_ports clk]', 'set_max_delay 5 -from A -to B'])
    return old, new


class TargetedConstraintTests(unittest.TestCase):
    def test_exact_vendor_provenance_change(self):
        self.assertEqual(compare_targeted_compiled(*fixture(), sorted(BRAM_KEYS))['provenance_substitutions'], 8)

    def test_changed_clock_rejected(self):
        a, b = fixture()
        b[-2] = b[-2].replace('period 10', 'period 20')
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_added_false_path_rejected(self):
        a, b = fixture()
        b.append('set_false_path -from A -to B')
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_other_fifo_scope_rejected(self):
        a, b = fixture()
        b = [line.replace('m00_r_node', 'm00_w_node') for line in b]
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_missing_line_provenance_rejected(self):
        a, b = fixture()
        del b[4]
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_duplicate_line_provenance_rejected(self):
        a, b = fixture()
        b.append(b[4])
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_reordered_timing_commands_rejected(self):
        a, b = fixture()
        b[-2:] = reversed(b[-2:])
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))

    def test_vendor_file_path_change_rejected(self):
        a, b = fixture()
        b = [line.replace('xpm_fifo_rst.tcl', 'other.tcl') for line in b]
        with self.assertRaises(ValueError): compare_targeted_compiled(a, b, sorted(BRAM_KEYS))


if __name__ == '__main__':
    unittest.main()
