"""New same-image 720x1272 integer Golden; no 1280-wide model-output crop.

Uses the locked lowlight payloads and unchanged Compact D integer reference.
The photograph is explicitly center-cropped at the RGB8 input boundary only.
All generated arrays stay in a new external directory.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np
from PIL import Image, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
BASE = "3c9e41a35fc08d44ba0552ce6916a421f98f94d7"
SOFTWARE = "9ef5fafa90ffd3c8ededbf22b3cf8ccb3bf16fce"
COUNT = 3*720*1272


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locked(ref, path):
    return subprocess.check_output(["git", "show", ref+":"+path], cwd=REPO)


def rne(value, shift):
    value = np.asarray(value, dtype=np.int64)
    if shift <= 0:
        return value*(1 << -shift)
    q = value >> shift
    r = value-q*(1 << shift)
    half = 1 << (shift-1)
    return q+((r > half) | ((r == half) & ((q & 1) != 0)))


def sat(value):
    return np.clip(value, -32768, 32767).astype(np.int16)


def cnn_reference(source, arrays, low):
    text = source.read_text()
    table = text.split("kZeroDceLayers[14] = {", 1)[1].split("};", 1)[0]
    layers = [tuple(map(int, row.split(","))) for row in re.findall(r"\{([\d, ]+)\}", table)]
    if len(layers) != 14 or any(len(s) != 12 for s in layers):
        raise ValueError("Unexpected locked CNN layer descriptors")
    weights = np.frombuffer(arrays["weights_int8.bin"], dtype="i1").astype(np.int64)
    bias = np.frombuffer(arrays["bias_int32.bin"], dtype="<i4").astype(np.int64)
    frac = np.frombuffer(arrays["weight_frac.bin"], dtype="i1")
    lut = np.frombuffer(arrays["tanh_lut_q15.bin"], dtype="<i2")
    skips, skip_frac = [], [14, 14, 14, 12, 13, 14]
    for block in range(1, 8):
        d, p = layers[2*(block-1):2*block]
        if block == 1:
            x = low.astype(np.int64)
        else:
            slots = [block-2] if block < 5 else {5: [2, 3], 6: [1, 4], 7: [0, 5]}[block]
            x = np.concatenate([sat(rne(skips[s], skip_frac[s]-d[3])) for s in slots]).astype(np.int64)
        ci, co, groups, fin, fout, kh, kw, ph, pw, wo, bo, fo = d
        if x.shape != (ci, 60, 106) or co != ci or groups != ci or (kh, kw, ph, pw) != (3, 3, 1, 1):
            raise ValueError("Unexpected locked CNN depthwise topology")
        padded = np.pad(x, ((0, 0), (1, 1), (1, 1)))
        kernel = weights[wo:wo+9*co].reshape(co, 3, 3)
        acc = np.broadcast_to(bias[bo:bo+co, None, None], x.shape).copy()
        for ky in range(3):
            for kx in range(3):
                acc += padded[:, ky:ky+60, kx:kx+106]*kernel[:, ky, kx, None, None]
        acc = acc.astype(np.int32).astype(np.int64)  # exact modulo-2^32 HLS accumulation
        middle = np.stack([sat(rne(acc[c], fin+int(frac[fo+c])-fout)) for c in range(co)])
        middle = sat(rne(middle, fout-p[3])).astype(np.int64)
        ci, co, groups, fin, fout, kh, kw, ph, pw, wo, bo, fo = p
        if groups != 1 or (kh, kw, ph, pw) != (1, 1, 0, 0):
            raise ValueError("Unexpected locked CNN pointwise topology")
        acc = weights[wo:wo+co*ci].reshape(co, ci) @ middle.reshape(ci, -1)
        acc += bias[bo:bo+co, None]
        acc = acc.astype(np.int32).astype(np.int64).reshape(co, 60, 106)
        value = np.stack([sat(rne(acc[c], fin+int(frac[fo+c])-fout)) for c in range(co)])
        if block < 7:
            value = np.maximum(value, 0).astype(np.int16)
            skips.append(value)
        else:
            index = np.clip(rne(value, 8), -2048, 2048)+2048
            return sat(rne(lut[index], 1))


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--d-package", type=Path, default=Path("D:/weather_builds/compact_d_numeric01/package"))
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out/"source"
    source.mkdir()
    result = {"pass": False, "board_operations": 0, "baseline": BASE, "software": SOFTWARE,
              "shape": [1, 3, 720, 1272], "scope": "new same-image software integer Golden, not RTL/board proof",
              "numpy": np.__version__, "pillow": pillow_version}
    start = time.perf_counter()
    try:
        manifest = json.loads(locked(BASE, "fpga/bringup/kv260_v12/manifest.json"))
        arrays = {}
        for name, spec in manifest["assets"].items():
            if "included_hex" not in spec:
                continue
            payload = bytes.fromhex(locked(BASE, "fpga/bringup/kv260_v12/"+spec["included_hex"]).decode())
            if len(payload) != spec["bytes"] or hashlib.sha256(payload).hexdigest() != spec["sha256"]:
                raise ValueError("Lowlight payload identity mismatch: "+name)
            arrays[name] = payload
            (source/name).write_bytes(payload)
        cpp = source/"zero_dce_cnn_top.cpp"
        cpp.write_bytes(locked(BASE, "fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4/zero_dce_cnn_top.cpp"))
        old = np.frombuffer(arrays["input_q14.bin"], dtype="<i2").reshape(3, 60, 106)
        want = np.frombuffer(arrays["expected_a_low_q14.bin"], dtype="<i2").reshape(3, 60, 106)
        got = cnn_reference(cpp, arrays, old)
        mismatch = int(np.count_nonzero(got != want))
        if mismatch:
            raise ValueError("Locked historical CNN Golden mismatch: "+str(mismatch))
        result["historical_cnn_compared_scalars"] = got.size
        result["historical_cnn_mismatches"] = mismatch
        print("JOINT_GOLDEN historical CNN matches 19080 scalars", flush=True)

        photograph = source/"night_01.jpg"
        photograph.write_bytes(locked(SOFTWARE, "data/test/night_01.jpg"))
        image = Image.open(photograph).convert("RGB")
        if image.size != (1280, 720):
            raise ValueError("Unexpected source photograph shape")
        image = image.crop((4, 0, 1276, 720))
        image.save(out/"input_1272x720.png")
        rgb = np.asarray(image, dtype=np.uint8).copy()
        rgb.tofile(out/"rgb.u8")
        original = ((rgb.astype(np.int64)*16384+127)//255).transpose(2, 0, 1).astype(np.int16)
        n = (rgb.astype(np.int64)*2-255)*16384
        din = (np.sign(n)*((np.abs(n)+127)//255)).transpose(2, 0, 1).astype(np.int16)
        total = sum(original[:, dy::12, dx::12].astype(np.int64) for dy in (5, 6) for dx in (5, 6))
        cin = rne(total, 2).astype(np.int16)
        alow = cnn_reference(cpp, arrays, cin)
        for name, value in {"original": original, "d_input": din, "cnn_input": cin, "a_low": alow}.items():
            value.astype("<i2").tofile(out/(name+".i16"))
        result["input_preprocessing"] = {"source_sha256": sha(photograph), "source_size": [1280, 720],
            "crop_box_rgb8": [4, 0, 1276, 720], "model_output_crop": False, "shared_input": "rgb.u8"}
        reference_path = source/"arithmetic.py"
        reference_path.write_bytes(locked(BASE, "fpga/reference/fixed_point_v1/arithmetic.py"))
        spec = importlib.util.spec_from_file_location("locked_arithmetic", reference_path)
        ref = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ref)
        flat = alow.ravel().tolist()
        afull = np.fromiter((ref.bilinear_pixel_raw(flat, 60, 106, c, y, x)
            for c in range(3) for y in range(720) for x in range(1272)), dtype=np.int16, count=COUNT).reshape(3, 720, 1272)
        afull.astype("<i2").tofile(out/"a_full.i16")
        light = original.astype(np.int64)
        for _ in range(8):
            light = np.clip(((light << 28)+afull.astype(np.int64)*(light*light-(light << 14))+(1 << 27)) >> 28, -32768, 32767)
        light.astype("<i2").tofile(out/"lowlight.i16")
        print("JOINT_GOLDEN lowlight full frame ready", flush=True)

        sys.path.insert(0, str(REPO))
        from models.compact_d.fixed.numeric import run, load_package
        dmeta, _, _ = load_package(a.d_package)
        if dmeta["bundle_id"] != "2fa5547661b6ebd18a8a103835ecf44fa132300a1d2e4cfca8af587473c7067a":
            raise ValueError("Wrong frozen D bundle")
        ddir = out/"d_nodes"
        ddir.mkdir()
        nodes = []
        def observe(index, node, value, stats):
            f = ddir/f'{index:02d}_{node["id"]}.i16'
            value.astype("<i2").tofile(f)
            nodes.append({"id": node["id"], "shape": list(value.shape), "file": f.name, "sha256": sha(f), **stats})
            print("JOINT_GOLDEN D "+node["id"], flush=True)
        dout = run(a.d_package, np.ascontiguousarray(din[None]), observer=observe)
        # Reference returns the actual graph output; no spatial crop is allowed.
        if dout.shape != (1, 3, 720, 1272):
            raise ValueError("D output shape mismatch")
        dout.astype("<i2").tofile(out/"d_output.i16")
        result["d_bundle_id"] = dmeta["bundle_id"]
        result["d_nodes"] = nodes
        weights = [10923, 10923, 10922]
        fused = np.clip(rne(original.astype(np.int64)*weights[0]+light*weights[1]+dout[0].astype(np.int64)*weights[2], 15), 0, 16384)
        fused.astype("<i2").tofile(out/"fused.i16")
        result["weights_q15"] = weights
        for name in ("original", "lowlight", "d_output", "fused"):
            values = np.fromfile(out/(name+".i16"), dtype="<u2")
            np.savetxt(out/(name+".hex"), values, fmt="%04x")
        result["pass"] = True
    except Exception as e:
        result["error"] = str(e)
        raise
    finally:
        result["seconds"] = time.perf_counter()-start
        result["source_files"] = {f.relative_to(out).as_posix(): sha(f) for f in source.iterdir() if f.is_file()}
        result["files"] = {f.name: {"bytes": f.stat().st_size, "sha256": sha(f)} for f in out.iterdir() if f.is_file()}
        (out/"result.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8", newline="\n")
        print("JOINT_GOLDEN_PASS="+str(result["pass"]), flush=True)


if __name__ == "__main__":
    main()
