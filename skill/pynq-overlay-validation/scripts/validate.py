"""Offline checks only. Standard library; never imports PYNQ or accesses hardware."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, name + " must be an integer >= " + str(minimum))
    return value


def itemsize(dtype):
    require(isinstance(dtype, str) and re.fullmatch(r"(?:[ui]1|[<>][ui][248])", dtype) is not None,
            "dtype must be i1/u1 or explicit-endian integer such as <i2, >u4")
    return int(dtype[-1])


def text(value, name):
    require(isinstance(value, str) and bool(value.strip()), name + " must be nonempty text")
    return value


def check_contract(contract, inventory=None):
    require(isinstance(contract, dict), "contract must be an object")
    require(type(contract.get("schema_version")) is int and contract["schema_version"] == 1, "unsupported schema_version")
    require(contract.get("evidence_level") in {"synthetic-host-only", "board-candidate"}, "invalid evidence_level")
    text(contract.get("board"), "board")
    text(contract.get("pynq_version"), "pynq_version")
    ip = contract.get("ip")
    require(isinstance(ip, dict), "ip must be an object")
    name = text(ip.get("name"), "ip.name")
    text(ip.get("vlnv"), "ip.vlnv")
    addressable = ip.get("addressable", True)
    require(type(addressable) is bool, "ip.addressable must be boolean")
    span = integer(ip.get("addr_range"), "ip.addr_range", 4 if addressable else 0)
    require(addressable or span == 0, "stream-only IP must declare addr_range=0")

    def reg(value, label, mask=True):
        require(isinstance(value, dict), label + " must be an object")
        offset = integer(value.get("offset"), label + ".offset")
        require(offset % 4 == 0 and offset + 4 <= span, label + " outside aligned 32-bit register window")
        if mask:
            require(0 < integer(value.get("mask"), label + ".mask", 1) <= 0xFFFFFFFF, label + " mask too wide")
        return offset

    buffers = contract.get("buffers")
    require(isinstance(buffers, list) and bool(buffers), "buffers must be a nonempty list")
    by_name = {}
    for b in buffers:
        require(isinstance(b, dict), "each buffer must be an object")
        key = text(b.get("name"), "buffer.name")
        require(key not in by_name, "duplicate buffer " + key)
        require(b.get("role") in {"input", "output"}, "only separate input/output buffers are supported")
        shape = b.get("shape")
        require(isinstance(shape, list) and bool(shape), "shape must be a nonempty list")
        for d in shape:
            integer(d, "shape dimension", 1)
        size = itemsize(b.get("dtype"))
        require(b.get("layout") == "C", "only C-contiguous layout is supported")
        require(integer(b.get("nbytes"), "buffer.nbytes", 1) == math.prod(shape) * size,
                "nbytes does not equal shape * dtype size: " + key)
        align = integer(b.get("alignment_bytes"), "alignment_bytes", 1)
        require(align & (align - 1) == 0 and align >= size, "alignment_bytes must be a power of two >= itemsize")
        guards = integer(b.get("guard_bytes"), "guard_bytes", 1)
        require(guards % align == 0, "guard_bytes must preserve payload alignment")
        require(b.get("cache_policy") in {"explicit-sync", "verified-coherent"}, "cache_policy must be explicit-sync or verified-coherent")
        by_name[key] = b
    require(any(b["role"] == "input" for b in buffers) and any(b["role"] == "output" for b in buffers),
            "at least one input and one output are required")
    control = contract.get("control")
    require(isinstance(control, dict), "control must be an object")
    timeout = control.get("timeout_s")
    require(type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0, "timeout_s must be finite and positive")
    require(control.get("kind") in {"register", "free-running"}, "unsupported control kind")
    require(addressable or control["kind"] == "free-running", "stream-only IP cannot declare MMIO register control")
    if control["kind"] == "register":
        reg(control.get("start"), "start")
        reg(control.get("done"), "done")
        text(control.get("completion_semantics"), "completion_semantics")
    transport = contract.get("transport")
    require(isinstance(transport, dict), "transport must be an object")
    kind = transport.get("kind")
    if kind == "mmio-master":
        require(addressable, "mmio-master profile requires addressable accelerator IP")
        require(control["kind"] == "register", "mmio-master profile requires explicit register control")
        require(transport.get("address_bits") in {32, 64}, "address_bits must be 32 or 64")
        ptrs = transport.get("pointer_registers")
        require(isinstance(ptrs, dict) and set(ptrs) == set(by_name), "one pointer-register pair is required per buffer")
        occupied = set()
        protected = {control["start"]["offset"], control["done"]["offset"]}
        for key, pointer in ptrs.items():
            require(isinstance(pointer, dict), "pointer-register entry must be an object")
            words = [pointer.get("low")]
            if transport["address_bits"] == 64:
                words.append(pointer.get("high"))
            else:
                require("high" not in pointer, "32-bit profile cannot declare high pointer register")
            for word in words:
                off = reg({"offset": word}, "pointer " + key, mask=False)
                require(off not in occupied and off not in protected, "pointer register aliases control or another pointer")
                occupied.add(off)
    elif kind == "axi-stream-dma":
        text(transport.get("dma_ip"), "dma_ip")
        require(transport["dma_ip"] != name, "DMA and accelerator IP must be distinct in this profile")
        text(transport.get("tlast_policy"), "tlast_policy")
        maximum = integer(transport.get("max_transfer_bytes"), "max_transfer_bytes", 1)
        align = integer(transport.get("address_alignment_bytes"), "address_alignment_bytes", 1)
        require(align & (align - 1) == 0, "DMA alignment must be a power of two")
        require(len(buffers) == 2, "DMA profile supports exactly one input and one output")
        for channel, role in (("send_buffer", "input"), ("recv_buffer", "output")):
            key = transport.get(channel)
            require(isinstance(key, str) and key in by_name and by_name[key]["role"] == role, "invalid " + channel)
            require(by_name[key]["nbytes"] <= maximum, "DMA transfer exceeds configured maximum")
            require(by_name[key]["alignment_bytes"] % align == 0, "buffer alignment does not satisfy DMA requirement")
    else:
        raise ValidationError("unsupported transport kind")
    if inventory is not None:
        require(isinstance(inventory, dict) and isinstance(inventory.get("ip_dict"), dict), "inventory must contain ip_dict")
        ips = inventory["ip_dict"]
        if addressable:
            require(name in ips and isinstance(ips[name], dict), "accelerator missing from inventory")
            observed = ips[name]
            require(observed.get("type") == ip["vlnv"], "accelerator VLNV differs from inventory")
            require(observed.get("addr_range") == span, "accelerator register window differs from inventory")
        else:
            require(name not in ips, "stream-only declaration conflicts with addressable IP inventory")
        if kind == "axi-stream-dma":
            dma = ips.get(transport["dma_ip"])
            require(isinstance(dma, dict) and str(dma.get("type", "")).startswith("xilinx.com:ip:axi_dma:"),
                    "AXI DMA IP missing or wrong VLNV in inventory")
    return {"status": "HOST_CONTRACT_PASS", "evidence_level": contract["evidence_level"],
            "inventory_checked": inventory is not None,
            "accelerator_inventory_checked": inventory is not None and addressable,
            "buffer_count": len(buffers), "board_validated": False}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def local_file(root, value):
    text(value, "data path")
    require(not Path(value).is_absolute(), "data path must be relative to bundle")
    path = (root / value).resolve()
    require(path.is_relative_to(root), "data path escapes bundle directory")
    require(path.is_file(), "data file missing: " + value)
    return path


def read_exact(path, expected):
    require(path.stat().st_size == expected, "wrong byte length: " + path.name)
    return path.read_bytes()


def compare_bundle(contract, bundle, root, require_ab=False):
    check_contract(contract)
    root = Path(root).resolve()
    require(isinstance(bundle, dict) and type(bundle.get("schema_version")) is int and bundle["schema_version"] == 1,
            "unsupported bundle schema")
    frames = bundle.get("frames")
    require(isinstance(frames, list) and bool(frames), "frames must be nonempty")
    require(not require_ab or len(frames) == 2, "A/B mode requires exactly two frames")
    inputs = {b["name"]: b for b in contract["buffers"] if b["role"] == "input"}
    outputs = {b["name"]: b for b in contract["buffers"] if b["role"] == "output"}
    ids, signatures, rows = set(), [], []
    observed_files, reference_files = [], []

    def observed_file(path, label):
        for previous, previous_label in observed_files + reference_files:
            require(not path.samefile(previous), "observed file aliases " + previous_label + ": " + label)
        observed_files.append((path, label))

    def reference_file(path, label):
        for previous, previous_label in observed_files:
            require(not path.samefile(previous), "reference file aliases observed " + previous_label + ": " + label)
        reference_files.append((path, label))

    for frame in frames:
        require(isinstance(frame, dict), "frame must be an object")
        ident = text(frame.get("id"), "frame.id")
        require(ident not in ids, "duplicate frame id")
        ids.add(ident)
        declared_inputs, declared_outputs = frame.get("inputs"), frame.get("outputs")
        require(isinstance(declared_inputs, dict) and set(declared_inputs) == set(inputs), "all input files are required")
        require(isinstance(declared_outputs, dict) and set(declared_outputs) == set(outputs), "all output files are required")
        input_signature, output_signature = [], []
        for key, b in inputs.items():
            input_path = local_file(root, declared_inputs[key])
            reference_file(input_path, ident + "/input/" + key)
            raw = read_exact(input_path, b["nbytes"])
            input_signature.append(hashlib.sha256(raw).hexdigest())
        frame_rows = []
        for key, b in outputs.items():
            record = declared_outputs[key]
            require(isinstance(record, dict), "output record must be an object")
            actual_path, golden_path = local_file(root, record.get("actual")), local_file(root, record.get("golden"))
            reference_file(golden_path, ident + "/golden/" + key)
            observed_file(actual_path, ident + "/actual/" + key)
            golden = read_exact(golden_path, b["nbytes"])
            expected_sha = record.get("golden_sha256")
            require(isinstance(expected_sha, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha) is not None,
                    "golden_sha256 must be a lowercase SHA256")
            require(hashlib.sha256(golden).hexdigest() == expected_sha, "Golden SHA256 mismatch")
            poison_hex = record.get("poison_hex")
            require(isinstance(poison_hex, str), "poison_hex is required")
            try:
                poison = bytes.fromhex(poison_hex)
            except ValueError as error:
                raise ValidationError("poison_hex is not hex") from error
            size = itemsize(b["dtype"])
            require(len(poison) == size, "poison_hex must encode one dtype scalar")
            require(all(golden[i:i + size] != poison for i in range(0, len(golden), size)),
                    "poison occurs in Golden; choose another scalar")
            actual = read_exact(actual_path, b["nbytes"])
            require(actual == golden, "full byte comparison failed: " + ident + "/" + key)
            guard_byte = integer(record.get("guard_byte"), "guard_byte")
            require(guard_byte <= 255, "guard_byte must fit one byte")
            for side in ("guard_before", "guard_after"):
                guard_path = local_file(root, record.get(side))
                observed_file(guard_path, ident + "/" + key + "/" + side)
                guard = read_exact(guard_path, b["guard_bytes"])
                require(guard == bytes([guard_byte]) * b["guard_bytes"], "guard damaged: " + ident + "/" + key + "/" + side)
            digest = hashlib.sha256(actual).hexdigest()
            output_signature.append(digest)
            frame_rows.append({"name": key, "bytes_compared": len(actual), "sha256": digest, "guards": "PASS"})
        signatures.append((input_signature, output_signature))
        rows.append({"id": ident, "outputs": frame_rows})
    if require_ab:
        require(signatures[0][0] != signatures[1][0], "A/B input files are identical")
        require(signatures[0][1] != signatures[1][1], "A/B expected outputs are identical; select a discriminating pair")
    return {"status": "HOST_FILES_PASS", "ab_checked": require_ab, "frames": rows, "board_validated": False,
            "limitation": "Files alone do not prove prefill, fresh completion, DMA/cache correctness or a new hardware run."}


def create_demo(output):
    """Produce tiny synthetic files in a new/empty directory, never real board data."""
    root = Path(output).resolve()
    require(not root.exists() or (root.is_dir() and not any(root.iterdir())), "demo output must be a new or empty directory")
    root.mkdir(parents=True, exist_ok=True)
    contract = load_json(Path(__file__).resolve().parents[1] / "assets" / "mmio-master.example.json")
    bundle = {"schema_version": 1, "origin": "synthetic Python byte copy; no PYNQ or hardware execution", "frames": []}
    for label, base in (("A", 0), ("B", 16)):
        raw = struct.pack("<8I", *(base + i for i in range(8)))
        names = {kind: label + "_" + kind + ".bin" for kind in ("input", "actual", "golden", "before", "after")}
        for kind, name in names.items():
            with (root / name).open("xb") as stream:
                stream.write(b"Z" * 64 if kind in {"before", "after"} else raw)
        bundle["frames"].append({"id": label, "inputs": {"input": names["input"]}, "outputs": {"output": {
            "actual": names["actual"], "golden": names["golden"], "golden_sha256": hashlib.sha256(raw).hexdigest(),
            "guard_before": names["before"], "guard_after": names["after"], "guard_byte": 90, "poison_hex": "a5a5a5a5"}}})
    for name, data in (("contract.json", contract), ("run.json", bundle)):
        with (root / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
    result = compare_bundle(contract, bundle, root, require_ab=True)
    result["synthetic_demo"] = True
    result["bundle_directory"] = str(root)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="check the declared contract; optional PYNQ metadata snapshot")
    check.add_argument("contract")
    check.add_argument("--inventory")
    compare = commands.add_parser("compare", help="full binary Golden, guard and optional A/B file validation")
    compare.add_argument("contract")
    compare.add_argument("bundle", help="JSON; data paths are relative to this file")
    compare.add_argument("--require-ab", action="store_true")
    demo = commands.add_parser("demo", help="generate and verify synthetic A/B files; no hardware")
    demo.add_argument("output", help="new or empty directory")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = create_demo(args.output)
        elif args.command == "check":
            contract = load_json(args.contract)
            result = check_contract(contract, load_json(args.inventory) if args.inventory else None)
        else:
            contract = load_json(args.contract)
            result = compare_bundle(contract, load_json(args.bundle), Path(args.bundle).resolve().parent, args.require_ab)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error), "board_validated": False}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
