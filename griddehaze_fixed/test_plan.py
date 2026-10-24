"""Static planner geometry/lifetime tests using small hand-derived graphs."""
import json
from pathlib import Path
import tempfile
import unittest
from .io import sha256, write_json
from .plan import shape_plan


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.nodes = [
            {'id': 'input', 'op': 'input', 'inputs': []},
            {'id': 'down', 'op': 'conv', 'inputs': ['input'], 'weight': 'down.weight',
             'kernel_size': [3, 3], 'stride': [2, 2], 'padding': [1, 1], 'dilation': [1, 1]},
            {'id': 'up', 'op': 'deconv', 'inputs': ['down'], 'weight': 'up.weight', 'output_like': 'input',
             'kernel_size': [3, 3], 'stride': [2, 2], 'padding': [1, 1], 'dilation': [1, 1]}]
        self.parameters = [{'name': 'down.weight', 'shape': [4, 3, 3, 3]},
                           {'name': 'up.weight', 'shape': [4, 3, 3, 3]}]

    def tearDown(self):
        self.temp.cleanup()

    def package(self):
        write_json(self.root/'graph.json', {'input': 'input', 'output': self.nodes[-1]['id'], 'nodes': self.nodes})
        write_json(self.root/'manifest.json', {'graph_file': 'graph.json',
                   'graph_sha256': sha256(self.root/'graph.json'), 'parameters': self.parameters})
        return self.root

    def test_odd_even_target_output_size(self):
        p = self.package()
        odd = shape_plan(p, 5, 7)
        self.assertEqual(odd['output_shape'], [1, 3, 5, 7])
        self.assertEqual(odd['nodes'][1]['shape'], [1, 4, 3, 4])
        self.assertEqual(odd['nodes'][2]['output_padding'], [0, 0])
        even = shape_plan(p, 6, 8)
        self.assertEqual(even['nodes'][2]['output_padding'], [1, 1])

    def test_shape_dependency_does_not_extend_tensor_lifetime(self):
        report = shape_plan(self.package(), 5, 7)
        inp = report['nodes'][0]
        self.assertEqual(inp['last_use'], 1)
        self.assertEqual(inp['shape_last_use'], 2)
        self.assertEqual(report['nodes'][1]['live_materialized_int16_bytes'], (3*5*7+4*3*4)*2)
        self.assertEqual(report['nodes'][2]['live_materialized_int16_bytes'], (4*3*4+3*5*7)*2)
        self.assertFalse(report['inference_executed'])

    def test_cat_materialized_and_output_retained(self):
        self.nodes += [{'id': 'cat', 'op': 'cat', 'inputs': ['input', 'up'], 'axis': 1}]
        report = shape_plan(self.package(), 5, 7)
        self.assertEqual(report['output_shape'], [1, 6, 5, 7])
        self.assertEqual(report['nodes'][-1]['last_use'], len(self.nodes))
        self.assertEqual(report['nodes'][-1]['live_materialized_int16_bytes'], 2*(3+3+6)*5*7)

    def test_reject_small_dimensions_and_tampered_graph(self):
        p = self.package()
        with self.assertRaises(ValueError):
            shape_plan(p, 3, 47)
        (p/'graph.json').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'identity'):
            shape_plan(p, 33, 47)

    def test_reject_unreachable_deconv_and_bad_concat(self):
        self.nodes[-1]['stride'] = [3, 3]
        with self.assertRaisesRegex(ValueError, 'Unreachable'):
            shape_plan(self.package(), 33, 47)
        self.nodes[-1]['stride'] = [2, 2]
        self.nodes += [{'id': 'cat', 'op': 'cat', 'inputs': ['input', 'down'], 'axis': 1}]
        with self.assertRaisesRegex(ValueError, 'concat'):
            shape_plan(self.package(), 33, 47)


if __name__ == '__main__':
    unittest.main()
