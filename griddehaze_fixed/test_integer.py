"""Primitive scalar oracles, DAG cross checks and package corruption tests.

Run ``python -m unittest griddehaze_fixed.test_integer -v``.  Test fixtures are
small deterministic synthetic tensors, never claimed to be a formal dataset.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from . import integer as g
from .fetch import COMMIT, WEIGHT_SHA256


def scalar_round(value, shift):
    value = int(value)
    if shift <= 0:
        return value << -shift
    magnitude = (abs(value) + (1 << (shift - 1))) >> shift
    return -magnitude if value < 0 else magnitude


def scalar_conv(x, weight, bias, stride, padding, dilation):
    cin, h, w = x.shape
    cout, _, kh, kw = weight.shape
    oh = (h + 2 * padding[0] - dilation[0] * (kh - 1) - 1) // stride[0] + 1
    ow = (w + 2 * padding[1] - dilation[1] * (kw - 1) - 1) // stride[1] + 1
    result = np.empty((cout, oh, ow), dtype=np.int64)
    for co in range(cout):
        for yy in range(oh):
            for xx in range(ow):
                value = int(bias[co])
                for ci in range(cin):
                    for ky in range(kh):
                        for kx in range(kw):
                            sy = yy * stride[0] - padding[0] + ky * dilation[0]
                            sx = xx * stride[1] - padding[1] + kx * dilation[1]
                            if 0 <= sy < h and 0 <= sx < w:
                                value += int(x[ci, sy, sx]) * int(weight[co, ci, ky, kx])
                result[co, yy, xx] = value
    return result


def scalar_deconv(x, weight, bias, stride, padding, dilation, target):
    cin, h, w = x.shape
    _, cout, kh, kw = weight.shape
    result = np.zeros((cout,) + tuple(target), dtype=np.int64)
    # Each output sample is independently reconstructed by gathering only input
    # samples whose expanded coordinates line up with this kernel tap.
    for co in range(cout):
        for yy in range(target[0]):
            for xx in range(target[1]):
                value = int(bias[co])
                for ci in range(cin):
                    for ky in range(kh):
                        for kx in range(kw):
                            py = yy + padding[0] - ky * dilation[0]
                            px = xx + padding[1] - kx * dilation[1]
                            if py % stride[0] == 0 and px % stride[1] == 0:
                                sy, sx = py // stride[0], px // stride[1]
                                if 0 <= sy < h and 0 <= sx < w:
                                    value += int(x[ci, sy, sx]) * int(weight[ci, co, ky, kx])
                result[co, yy, xx] = value
    return result


def scalar_graph(graph, parameters, x, default_frac):
    """Independent tiny-DAG oracle with scalar rounding and Python integers."""
    values, fracs = {}, {}
    def aligned(array, shift):
        return np.array([scalar_round(v, shift) for v in array.flat], np.int64).reshape(array.shape)
    def clamp(array):
        return np.array([max(-32768, min(32767, int(v))) for v in array.flat], np.int16).reshape(array.shape)
    for node in graph["nodes"]:
        name, op = node["id"], node["op"]
        frac = node.get("activation_frac", default_frac)
        inputs = node["inputs"]
        args = [values[n] for n in inputs]
        if op == "input":
            output = x[0].copy()
        elif op in {"conv", "deconv"}:
            common = (args[0], parameters[node["weight"]], parameters[node["bias"]], tuple(node["stride"]), tuple(node["padding"]), tuple(node["dilation"]))
            accumulator = scalar_deconv(*common, values[node["output_like"]].shape[-2:]) if op == "deconv" else scalar_conv(*common)
            output = np.empty_like(accumulator)
            for c, fw in enumerate(node["weight_frac"]):
                output[c] = aligned(accumulator[c], fracs[inputs[0]] + fw - frac)
            output = clamp(output)
        elif op == "relu":
            output = clamp(np.maximum(aligned(args[0], fracs[inputs[0]] - frac), 0))
        elif op == "cat":
            output = np.concatenate([clamp(aligned(arg, fracs[n] - frac)) for arg, n in zip(args, inputs)], axis=0)
        elif op == "add":
            output = clamp(aligned(args[0], fracs[inputs[0]] - frac) + aligned(args[1], fracs[inputs[1]] - frac))
        elif op == "mulcoef":
            coefficient = parameters[node["coefficient"]]
            product = args[0].astype(np.int64) * coefficient.astype(np.int64)[:, None, None]
            output = clamp(aligned(product, fracs[inputs[0]] + node["coefficient_frac"] - frac))
        else:
            raise AssertionError(op)
        values[name], fracs[name] = output, frac
    return {name: value[None] for name, value in values.items()}


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def update_bundle(manifest):
    identity = {k: v for k, v in manifest["identity"].items() if k != "bundle_id"}
    payload = dict(identity=identity, quantization=manifest["quantization"], code_hashes=manifest["export_code_hashes"],
                   graph_sha256=manifest["graph_sha256"], blob_sha256=manifest["blob_sha256"])
    manifest["identity"]["bundle_id"] = hashlib.sha256(canonical(payload)).hexdigest()


def fixture(directory):
    """An identity-pinned but explicitly synthetic miniature execution DAG."""
    rng = np.random.default_rng(87234)
    params, blob = [], bytearray()
    def parameter(name, array, layout, frac):
        array = np.ascontiguousarray(array)
        blob.extend(b"\x00" * ((-len(blob)) % 64))
        raw = array.tobytes()
        params.append(dict(name=name, dtype=array.dtype.name, shape=list(array.shape), layout=layout, frac=frac,
                           offset=len(blob), nbytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        blob.extend(raw)
    def conv_parameters(name, shape, transpose=False):
        cout = shape[1] if transpose else shape[0]
        parameter(name + ".weight", rng.integers(-3, 4, shape, dtype=np.int8), "IOHW" if transpose else "OIHW", [2] * cout)
        parameter(name + ".bias", np.arange(cout, dtype=np.int64) - 1, "O", [12] * cout)
    conv_parameters("down", (2, 3, 3, 3))
    conv_parameters("up", (2, 3, 3, 3), True)
    conv_parameters("out", (3, 6, 1, 1))
    parameter("coefficient", np.array([16384, -8192, 24576], np.int16), "C", 14)
    def conv_node(name, source, stride, padding, transpose=False):
        return dict(id=name, op="deconv" if transpose else "conv", inputs=[source], weight=name + ".weight",
                    bias=name + ".bias", weight_frac=[2] * (3 if transpose or name == "out" else 2),
                    stride=[stride, stride], padding=[padding, padding], dilation=[1, 1], groups=1,
                    **({"output_like": "input"} if transpose else {}))
    nodes = [dict(id="input", op="input", inputs=[]), conv_node("down", "input", 2, 1),
             dict(id="relu", op="relu", inputs=["down"]), conv_node("up", "relu", 2, 1, True),
             dict(id="mix", op="mulcoef", inputs=["up"], coefficient="coefficient", coefficient_frac=14),
             dict(id="add", op="add", inputs=["input", "mix"]),
             dict(id="cat", op="cat", inputs=["input", "add"], axis=1), conv_node("out", "cat", 1, 0),
             dict(id="output", op="relu", inputs=["out"])]
    graph = dict(format_version=g.FORMAT_VERSION, nodes=nodes, input="input", output="output")
    graph_bytes = canonical(graph)
    manifest = dict(format_version=g.FORMAT_VERSION,
                    identity=dict(model="GridDehazeNet", source_commit=COMMIT, weight_sha256=WEIGHT_SHA256,
                                  test_only="synthetic_miniature_not_official_weights"),
                    quantization=dict(activation_bits=16, activation_frac=10, weight_bits=8, coefficient_bits=16,
                                      coefficient_frac=14, accumulator_bits=64, rounding="half_away_from_zero", saturation="signed_clamp"),
                    graph_file="graph.json", blob_file="parameters.bin", graph_sha256=hashlib.sha256(graph_bytes).hexdigest(),
                    blob_sha256=hashlib.sha256(blob).hexdigest(), blob_nbytes=len(blob), parameters=params,
                    export_code_hashes={name: g.sha256(Path(g.__file__).with_name(name)) for name in ("export.py", "fetch.py", "integer.py")})
    update_bundle(manifest)
    (directory / "graph.json").write_bytes(graph_bytes)
    (directory / "parameters.bin").write_bytes(blob)
    (directory / "manifest.json").write_bytes(canonical(manifest))
    return manifest, graph


class ArithmeticTests(unittest.TestCase):
    def test_half_away_negative_and_positive_ties(self):
        values = np.arange(-19, 20, dtype=np.int64)
        for shift in range(0, 7):
            expected = np.array([scalar_round(v, shift) for v in values], np.int64)
            np.testing.assert_array_equal(g.round_shift(values, shift), expected)

    def test_round_extreme_int64_without_abs_overflow(self):
        values = np.array([-(1 << 63), -(1 << 63) + 1, -1, 0, 1, (1 << 63) - 2, (1 << 63) - 1], np.int64)
        for shift in [1, 2, 31, 62]:
            np.testing.assert_array_equal(g.round_shift(values, shift), [scalar_round(v, shift) for v in values])

    def test_left_shift_and_overflow(self):
        np.testing.assert_array_equal(g.round_shift(np.array([-17, 0, 17]), -3), [-136, 0, 136])
        with self.assertRaises(OverflowError):
            g.round_shift(np.array([1 << 62], np.int64), -1)
        with self.assertRaises(ValueError):
            g.round_shift(np.array([1]), 63)
        with self.assertRaises(ValueError):
            g.round_shift(np.array([1.5]), 1)

    def test_per_channel_requantization_and_saturation(self):
        x = np.array([[[65535, -65535]], [[65534, -65538]], [[32768, -32769]], [[16384, -16385]]], np.int64)
        result, stats = g.requantize(x, [1, 1, 0, -1])
        np.testing.assert_array_equal(result, [[[32767, -32768]], [[32767, -32768]], [[32767, -32768]], [[32767, -32768]]])
        self.assertEqual(stats, dict(saturated_low=3, saturated_high=3))

    def test_convolution_scalar_oracle(self):
        rng = np.random.default_rng(123)
        x = rng.integers(-32768, 32768, (2, 5, 7), dtype=np.int16)
        weight = rng.integers(-128, 128, (3, 2, 3, 2), dtype=np.int8)
        bias = np.array([13, -7, 2], dtype=np.int64)
        for stride, padding, dilation in [((1, 1), (1, 0), (1, 1)), ((2, 3), (2, 1), (2, 1)), ((1, 2), (0, 1), (1, 2))]:
            expected = scalar_conv(x, weight, bias, stride, padding, dilation)
            for backend in ["numpy", "direct"]:
                np.testing.assert_array_equal(g.conv2d_accumulate(x, weight, bias, stride, padding, dilation, backend), expected)

    def test_transpose_scalar_oracle_odd_even_and_dilation(self):
        rng = np.random.default_rng(234)
        x = rng.integers(-32768, 32768, (2, 3, 4), dtype=np.int16)
        weight = rng.integers(-128, 128, (2, 3, 3, 3), dtype=np.int8)
        bias = np.array([13, -7, 2], dtype=np.int64)
        for stride, padding, dilation in [((2, 2), (1, 1), (1, 1)), ((2, 3), (1, 1), (2, 1))]:
            minimum = tuple((x.shape[d + 1] - 1) * stride[d] - 2 * padding[d] + dilation[d] * 2 + 1 for d in range(2))
            for extra in [(0, 0), (1, 1), (0, 1)]:
                target = tuple(a + b for a, b in zip(minimum, extra))
                expected = scalar_deconv(x, weight, bias, stride, padding, dilation, target)
                for backend in ["numpy", "direct"]:
                    np.testing.assert_array_equal(g.deconv2d_accumulate(x, weight, bias, stride, padding, dilation, target, backend), expected)

    def test_operator_shape_and_overflow_failures(self):
        x, w, b = np.ones((1, 2, 2), np.int16), np.ones((1, 1, 3, 3), np.int8), np.zeros(1, np.int64)
        with self.assertRaises(ValueError):
            g.conv2d_accumulate(x, w, b)
        with self.assertRaises(ValueError):
            g.deconv2d_accumulate(x, w, b, stride=2, padding=1, output_shape=(5, 5))
        with self.assertRaises(ValueError):
            g.conv2d_accumulate(x, w, b, stride=0)
        with self.assertRaises(OverflowError):
            g.conv2d_accumulate(x, w, np.array([(1 << 63) - 1], np.int64), padding=1)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.manifest, self.graph = fixture(self.directory)
        self.input = np.random.default_rng(345).integers(-32768, 32768, (1, 3, 5, 6), dtype=np.int16)

    def tearDown(self):
        self.temporary.cleanup()

    def save_manifest(self):
        (self.directory / "manifest.json").write_bytes(canonical(self.manifest))

    def save_graph(self):
        payload = canonical(self.graph)
        (self.directory / "graph.json").write_bytes(payload)
        self.manifest["graph_sha256"] = hashlib.sha256(payload).hexdigest()
        update_bundle(self.manifest)
        self.save_manifest()

    def set_scales(self, scales):
        for node in self.graph["nodes"]:
            node["activation_frac"] = scales[node["id"]]
        self.manifest["quantization"]["activation_frac"] = scales["input"]
        self.manifest["quantization"]["output_frac"] = scales[self.graph["output"]]
        descriptors = {p["name"]: p for p in self.manifest["parameters"]}
        for node in self.graph["nodes"]:
            if node["op"] in {"conv", "deconv"}:
                descriptors[node["bias"]]["frac"] = [scales[node["inputs"][0]] + fw for fw in node["weight_frac"]]
        self.save_graph()

    def test_entire_dag_two_operator_backends_every_node(self):
        for height, width in [(4, 4), (5, 6), (6, 5), (7, 7)]:
            x = np.ascontiguousarray(self.input[:, :, :min(height, 5), :min(width, 6)])
            if x.shape[-2:] != (height, width):
                x = np.random.default_rng(height * width).integers(-32768, 32768, (1, 3, height, width), dtype=np.int16)
            observed = {}
            def observer(name, value, stats):
                self.assertFalse(value.flags.writeable)
                observed[name] = (value.copy(), dict(stats))
            y = g.run(self.directory, x, "numpy", observer)
            other = {}
            z = g.run(self.directory, x, "direct", lambda n, v, s: other.update({n: (v.copy(), dict(s))}))
            np.testing.assert_array_equal(y, z)
            self.assertEqual(set(observed), {n["id"] for n in self.graph["nodes"]})
            for name in observed:
                np.testing.assert_array_equal(observed[name][0], other[name][0])
                self.assertEqual(observed[name][1], other[name][1])

    def test_deterministic_repeat_and_output_dtype(self):
        first = g.run(self.directory, self.input)
        np.testing.assert_array_equal(first, g.run(self.directory, self.input))
        self.assertEqual(first.dtype, np.dtype(np.int16))
        self.assertEqual(first.shape, self.input.shape)

    def test_per_node_scales_all_ops_against_scalar_oracle(self):
        scales = dict(input=10, down=8, relu=9, up=7, mix=11, add=10, cat=8, out=9, output=10)
        self.set_scales(scales)
        _, graph, parameters = g.load_package(self.directory)
        expected = scalar_graph(graph, parameters, self.input, 10)
        for backend in ["numpy", "direct"]:
            observed = {}
            def observer(name, value, stats):
                self.assertEqual(stats["activation_frac"], scales[name])
                observed[name] = value.copy()
            result = g.run(self.directory, self.input, backend, observer)
            for name in expected:
                np.testing.assert_array_equal(observed[name], expected[name])
            np.testing.assert_array_equal(result, expected[graph["output"]])

    def test_add_rescales_int64_without_premature_operand_saturation(self):
        self.graph["nodes"] = [dict(id="input", op="input", inputs=[]),
                               dict(id="mix", op="mulcoef", inputs=["input"], coefficient="coefficient", coefficient_frac=14),
                               dict(id="add", op="add", inputs=["input", "mix"])]
        self.graph["output"] = "add"
        self.set_scales(dict(input=0, mix=0, add=1))
        x = np.full((1, 3, 4, 4), 30000, np.int16)
        # Channel one coefficient is -0.5: (30000 - 15000)*2 = 30000.
        # Prematurely saturating each aligned operand would give 2767 instead.
        for backend in ["numpy", "direct"]:
            result = g.run(self.directory, x, backend)
            np.testing.assert_array_equal(result[0, 1], np.full((4, 4), 30000, np.int16))

    def test_concat_alignment_saturation_and_relu_negative_clipping(self):
        self.graph["nodes"] = [dict(id="input", op="input", inputs=[]),
                               dict(id="positive", op="relu", inputs=["input"]),
                               dict(id="cat", op="cat", inputs=["input", "positive"], axis=1)]
        self.graph["output"] = "cat"
        self.set_scales(dict(input=0, positive=14, cat=14))
        x = np.full((1, 3, 4, 4), -32768, np.int16)
        x[0, 0] = 32767
        observed = {}
        result = g.run(self.directory, x, observer=lambda n, v, s: observed.update({n: dict(s)}))
        self.assertEqual(observed["positive"]["saturated_low"], 0)
        self.assertEqual(observed["positive"]["saturated_high"], 16)
        self.assertEqual(observed["cat"]["saturated_low"], 32)
        self.assertEqual(observed["cat"]["saturated_high"], 16)
        np.testing.assert_array_equal(result[0, 4:], np.zeros((2, 4, 4), np.int16))

    def test_invalid_per_node_input_output_scales_rejected(self):
        self.graph["nodes"][0]["activation_frac"] = 9
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "preprocessing scale"):
            g.load_package(self.directory)
        self.graph["nodes"][0]["activation_frac"] = 10
        self.graph["nodes"][1]["activation_frac"] = 15
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "per-node"):
            g.load_package(self.directory)
        self.graph["nodes"][1]["activation_frac"] = 8
        self.manifest["quantization"]["output_frac"] = 9
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "display/output scale"):
            g.load_package(self.directory)

    def add_calibration(self):
        calibration = dict(node_fracs={node["id"]: node.get("activation_frac", 10) for node in self.graph["nodes"]},
                           provenance="synthetic_unit_test_only")
        payload = canonical(calibration)
        (self.directory / "scale_config.json").write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        self.manifest.update(scale_config_file="scale_config.json", scale_config_sha256=digest, calibration=calibration)
        self.manifest["identity"]["scale_config_sha256"] = digest
        update_bundle(self.manifest)
        self.save_manifest()

    def test_calibration_original_bytes_and_embedded_content_verified(self):
        self.add_calibration()
        g.load_package(self.directory)
        with (self.directory / "scale_config.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "configuration SHA-256"):
            g.load_package(self.directory)
        self.add_calibration()
        self.manifest["calibration"]["provenance"] = "changed"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "embedded calibration"):
            g.load_package(self.directory)

    def test_calibration_graph_scales_and_recorded_conv_shifts_verified(self):
        self.add_calibration()
        self.graph["nodes"][1]["activation_frac"] = 9
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "calibration/graph"):
            g.load_package(self.directory)
        self.graph["nodes"][1]["activation_frac"] = 10
        self.graph["nodes"][1]["requantization_shift"] = [3, 3]
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "recorded requantization shift"):
            g.load_package(self.directory)

    def test_unsigned_float_batch_channels_size_noncontiguous_rejected(self):
        for value in [self.input.astype(np.uint16), self.input.astype(np.float32), self.input[0],
                      np.tile(self.input, (2, 1, 1, 1)), self.input[:, :2], self.input[:, :, :3], self.input[:, :, :, ::2]]:
            with self.assertRaises(ValueError):
                g.run(self.directory, value)

    def test_blob_byte_corruption_rejected(self):
        path = self.directory / "parameters.bin"
        payload = bytearray(path.read_bytes()); payload[0] ^= 1; path.write_bytes(payload)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            g.load_package(self.directory)

    def test_graph_corruption_rejected(self):
        with (self.directory / "graph.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            g.load_package(self.directory)

    def test_quantization_change_without_bundle_change_rejected(self):
        self.manifest["quantization"]["activation_frac"] = 11
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "bundle identity"):
            g.load_package(self.directory)

    def test_metadata_scale_change_rejected(self):
        self.manifest["parameters"][0]["frac"][0] += 1
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "scale mismatch"):
            g.load_package(self.directory)

    def test_parameter_hash_change_rejected(self):
        self.manifest["parameters"][0]["sha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "parameter SHA-256"):
            g.load_package(self.directory)

    def test_producer_code_change_rejected(self):
        self.manifest["export_code_hashes"]["integer.py"] = "0" * 64
        update_bundle(self.manifest)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "producer code identity"):
            g.load_package(self.directory)

    def test_wrong_model_identity_and_version_rejected(self):
        self.manifest["identity"]["source_commit"] = "wrong"
        update_bundle(self.manifest); self.save_manifest()
        with self.assertRaisesRegex(ValueError, "pinned task"):
            g.load_package(self.directory)
        self.manifest["format_version"] = "other-model-v2"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "format/version"):
            g.load_package(self.directory)

    def test_non_topological_and_duplicate_graph_rejected(self):
        self.graph["nodes"][1]["inputs"] = ["output"]
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "topologically"):
            g.load_package(self.directory)
        self.graph["nodes"][1]["inputs"] = ["input"]
        self.graph["nodes"][1]["id"] = "input"
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            g.load_package(self.directory)

    def test_unsupported_groups_and_concat_axis_rejected(self):
        self.graph["nodes"][1]["groups"] = 2
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "grouped convolution"):
            g.load_package(self.directory)
        self.graph["nodes"][1]["groups"] = 1
        self.graph["nodes"][6]["axis"] = 3
        self.save_graph()
        with self.assertRaisesRegex(ValueError, "channel concatenation"):
            g.load_package(self.directory)

    def test_overlapping_parameters_rejected(self):
        first, second = self.manifest["parameters"][:2]
        # Make a complete, hash-correct duplicate payload reference rather than
        # relying on a separate hash error to reject it.
        second.update(offset=first["offset"], nbytes=first["nbytes"], dtype=first["dtype"], shape=first["shape"], sha256=first["sha256"])
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "overlapping"):
            g.load_package(self.directory)

    def test_escaping_blob_path_rejected(self):
        self.manifest["blob_file"] = "../parameters.bin"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "escapes"):
            g.load_package(self.directory)


if __name__ == "__main__":
    unittest.main()
