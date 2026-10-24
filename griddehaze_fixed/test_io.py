"""Independent pixel conversion oracles and strict Golden comparison regressions."""
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from .cli import compare_dirs
from .io import display_rgb8, input_rgb8, save_tensor, write_json


def rational_nearest_away(value):
    """Integer divmod oracle, independent of vector conversion implementation."""
    numerator, denominator = value.numerator, value.denominator
    integer, remainder = divmod(abs(numerator), denominator)
    return (-1 if numerator < 0 else 1) * (integer + int(2*remainder >= denominator))


class PixelContractTests(unittest.TestCase):
    def test_all_256_levels_all_supported_fractions(self):
        rgb = np.repeat(np.arange(256, dtype=np.uint8)[:, None, None], 3, axis=2)
        for frac in range(15):
            expected = [rational_nearest_away(Fraction((2*v-255)*(1 << frac), 255)) for v in range(256)]
            actual = input_rgb8(rgb, frac)
            self.assertEqual(actual.shape, (1, 3, 256, 1))
            self.assertEqual(actual.dtype, np.dtype('<i2'))
            self.assertTrue(actual.flags.c_contiguous)
            for channel in range(3):
                np.testing.assert_array_equal(actual[0, channel, :, 0], expected)

    def test_rgb_channel_and_spatial_order(self):
        rgb = np.array([[[0, 127, 255], [255, 128, 0]], [[64, 192, 32], [16, 48, 80]]], dtype=np.uint8)
        result = input_rgb8(rgb, 10)
        self.assertTrue(result.flags.c_contiguous)
        for y in range(2):
            for x in range(2):
                for c in range(3):
                    self.assertEqual(int(result[0, c, y, x]),
                                     rational_nearest_away(Fraction((2*int(rgb[y, x, c])-255)*1024, 255)))

    def test_display_clamp_and_half_up_boundaries(self):
        for frac in range(15):
            raw = [-32768, -1, 0, 1, 2, (1 << frac)//2, (1 << frac)-1, 1 << frac, 32767]
            q = np.tile(np.array(raw, dtype=np.int16), (1, 3, 1, 1))
            expected = [rational_nearest_away(Fraction(min(1 << frac, max(0, v))*255, 1 << frac)) for v in raw]
            out = display_rgb8(q, frac)
            self.assertEqual(out.shape, (1, len(raw), 3))
            for channel in range(3):
                np.testing.assert_array_equal(out[0, :, channel], expected)
        self.assertEqual(int(display_rgb8(np.ones((1, 3, 1, 1), dtype=np.int16), 1)[0, 0, 0]), 128)

    def test_input_rejects_wrong_format_and_scale(self):
        for rgb in (np.zeros((2, 2, 3), np.float32), np.zeros((2, 2), np.uint8), np.zeros((2, 2, 4), np.uint8)):
            with self.assertRaises(ValueError):
                input_rgb8(rgb, 10)
        for frac in (-1, 15):
            with self.assertRaises(ValueError):
                input_rgb8(np.zeros((2, 2, 3), np.uint8), frac)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.expected, self.actual = self.root/'expected', self.root/'actual'
        self.report = self.root/'comparison.json'
        self.fixture(self.expected)
        self.fixture(self.actual)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def tensor(value):
        return np.array([[[[value]]]], dtype=np.int16)

    def fixture(self, directory):
        save_tensor(directory, 'input', self.tensor(1))
        nodes = []
        for name, value in [('z_first', 3), ('a_second', 4)]:
            nodes.append({'id': name, **save_tensor(directory/'nodes', name, self.tensor(value))})
        save_tensor(directory, 'output', self.tensor(4))
        save_tensor(directory, 'display_rgb8', np.array([[[255, 0, 0]]], dtype=np.uint8))
        write_json(directory/'report.json', {'nodes': nodes, 'manifest_sha256': 'same-package'})

    def compare(self):
        value = compare_dirs(self.expected, self.actual, self.report)
        return value, json.loads(self.report.read_text(encoding='utf-8'))

    def test_exact_and_hashes_recorded(self):
        result, report = self.compare()
        self.assertTrue(result)
        self.assertTrue(report['identity_equal'])
        for entry in report['comparisons']:
            self.assertEqual(entry['expected_raw_sha256'], entry['actual_raw_sha256'])

    def test_first_difference_is_execution_order_not_lexical_order(self):
        for name in ('a_second', 'z_first'):
            save_tensor(self.actual/'nodes', name, self.tensor(99))
        result, report = self.compare()
        self.assertFalse(result)
        self.assertEqual(Path(report['first_different_tensor']['tensor']).name, 'z_first.json')
        self.assertEqual(report['first_different_tensor']['first_difference_nchw'], [0, 0, 0, 0])
        self.assertEqual(report['first_different_tensor']['max_abs_error'], 96)

    def test_extra_and_missing_node_metadata_fail(self):
        save_tensor(self.actual/'nodes', 'extra', self.tensor(4))
        result, report = self.compare()
        self.assertFalse(result)
        self.assertIn('Node metadata file coverage mismatch', report['errors'])
        (self.actual/'nodes'/'extra.json').unlink()
        (self.actual/'nodes'/'z_first.json').unlink()
        self.assertFalse(self.compare()[0])

    def test_missing_declared_node_and_duplicate_id_fail(self):
        path = self.actual/'report.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report['nodes'] = report['nodes'][:1]
        write_json(path, report)
        self.assertFalse(self.compare()[0])
        report['nodes'].append(report['nodes'][0])
        write_json(path, report)
        self.assertFalse(self.compare()[0])

    def test_input_identity_required_even_when_outputs_equal(self):
        save_tensor(self.actual, 'input', self.tensor(2))
        result, report = self.compare()
        self.assertFalse(result)
        self.assertFalse(report['identity_equal'])
        self.assertEqual(report['first_different_tensor']['tensor'], 'input.json')

    def test_manifest_identity_required(self):
        path = self.actual/'report.json'
        report = json.loads(path.read_text(encoding='utf-8'))
        report['manifest_sha256'] = 'different-package'
        write_json(path, report)
        result, report = self.compare()
        self.assertFalse(result)
        self.assertFalse(report['identity_equal'])

    def test_corrupt_raw_or_metadata_is_not_a_tolerated_difference(self):
        (self.actual/'nodes'/'z_first.raw').write_bytes(b'\x00\x00')
        result, report = self.compare()
        self.assertFalse(result)
        self.assertIn('hash mismatch', report['first_different_tensor']['reason'])
        self.fixture(self.actual)
        path = self.actual/'nodes'/'z_first.json'
        meta = json.loads(path.read_text(encoding='utf-8'))
        meta['shape'] = [1, 1, 1, 2]
        write_json(path, meta)
        self.assertFalse(self.compare()[0])

    def test_missing_run_report_fails(self):
        (self.actual/'report.json').unlink()
        self.assertFalse(self.compare()[0])


if __name__ == '__main__':
    unittest.main()
