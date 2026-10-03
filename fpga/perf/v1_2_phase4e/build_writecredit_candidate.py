"""Create the isolated r4 RTL writer scheduling overlay; never edit frozen r4.

The C++ copy is a numerical reference, not a new HLS scheduling implementation.
Only three generated writer control modules are overlaid for RTL verification.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "fpga/hls/zero_dce_cnn_v1_2_30fps/candidate_b_rowstream_r4"
CANDIDATE = FROZEN.with_name("candidate_b_rowstream_r4_writecredit")
RTL = Path("E:/HLS/cnn_v1_2_phase3b_r4/cnn_component/hls/syn/verilog")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def helper(text, bundle):
    p = "m_axi_gmem_" + bundle + "_0"
    text = replace_once(text, "        result_fifo_cap\n);", "        result_fifo_cap,\n        write_credit_empty\n);")
    text = replace_once(text, "input  [8:0] result_fifo_cap;", "input  [8:0] result_fifo_cap;\noutput write_credit_empty;")
    marker = "// power-on initialization"
    extra = f"""// Phase 4E: logical row requests and coalesced row responses use two credits.
// The unchanged m_axi adapter retains physical burst splitting and data packing.
reg [1:0] credit_count;
wire row_request = {p}_AWVALID && {p}_AWREADY;
wire row_retire = {p}_BVALID && {p}_BREADY;
assign write_credit_empty = (credit_count == 0);
always @(posedge ap_clk) begin
    if (ap_rst) credit_count <= 0;
    else case ({{row_request, row_retire}})
        2'b10: credit_count <= credit_count + 1'b1;
        2'b01: credit_count <= credit_count - 1'b1;
        default: credit_count <= credit_count;
    endcase
end

"""
    text = replace_once(text, marker, extra + marker)
    old = f"({p}_AWREADY == 1'b1)"
    assert text.count(old) == 4, text.count(old)
    text = text.replace(old, f"(({p}_AWREADY == 1'b1) & (credit_count < 2))")
    text = replace_once(text, f"if (({p}_AWREADY == 1'b0))", f"if (({p}_AWREADY == 1'b0) || (credit_count == 2))")
    # State 9 is now the data-send completion event. Keep all earlier states.
    old = f"(({p}_BVALID == 1'b1) & (1'b1 == ap_CS_fsm_state9))"
    assert text.count(old) == 4, text.count(old)
    text = text.replace(old, "(1'b1 == ap_CS_fsm_state9)")
    start = text.index("always @ (*) begin\n    if ((1'b1 == ap_CS_fsm_state9)) begin\n        gmem_")
    end = text.index("\nend", start) + len("\nend")
    text = text[:start] + f"always @ (*) begin\n    gmem_{bundle}_blk_n_B = 1'b1;\nend" + text[end:]
    start = text.rfind("always @ (*) begin", 0, text.index(p + "_BREADY = 1'b1;"))
    end = text.index("\nend", start) + len("\nend")
    text = text[:start] + f"always @ (*) begin\n    {p}_BREADY = (credit_count != 0);\nend" + text[end:]
    # This is only a diagnostic block signal; it no longer stalls data completion.
    text = replace_once(text, f"if (({p}_BVALID == 1'b0))", "if (1'b0)")
    return text


def caller(text):
    marker = "// power-on initialization"
    text = replace_once(text, marker, "// Phase 4E: no writer or block completion until every row B is retired.\nwire workspace_write_credit_empty;\nwire output_write_credit_empty;\nwire all_write_credits_empty = workspace_write_credit_empty && output_write_credit_empty;\n\n" + marker)
    for instance, empty in [("grp_row_axi_writer_fu_171", "workspace_write_credit_empty"), ("grp_row_axi_writer_2_fu_181", "output_write_credit_empty")]:
        start = text.index(instance + "(")
        end = text.index("\n);", start)
        part = text[start:end]
        part = replace_once(part, ".result_fifo_cap(9'd0)", ".result_fifo_cap(9'd0),\n    .write_credit_empty(" + empty + ")")
        text = text[:start] + part + text[end:]
    cond = "(icmp_ln245_fu_214_p2 == 1'd1)"
    assert text.count(cond) == 4, text.count(cond)
    text = text.replace(cond, "((icmp_ln245_fu_214_p2 == 1'd1) & all_write_credits_empty)")
    old = """            end else begin
                ap_NS_fsm = ap_ST_fsm_state7;
            end
        end
        ap_ST_fsm_state7"""
    new = """            end else if (icmp_ln245_fu_214_p2 == 1'd1) begin
                // All rows sent: remain here until both bundles fully drain.
                ap_NS_fsm = ap_ST_fsm_state6;
            end else begin
                ap_NS_fsm = ap_ST_fsm_state7;
            end
        end
        ap_ST_fsm_state7"""
    return replace_once(text, old, new)


def main():
    if CANDIDATE.exists():
        raise SystemExit("Refuse to overwrite existing candidate")
    source_hashes = {str(p): sha(p) for p in FROZEN.iterdir() if p.is_file()}
    records = []
    transformed = {}
    for name, transform in [
        ("zero_dce_cnn_top_row_axi_writer.v", lambda t: helper(t, "workspace")),
        ("zero_dce_cnn_top_row_axi_writer_2.v", lambda t: helper(t, "output")),
        ("zero_dce_cnn_top_p_anonymous_namespace_output_writer.v", caller),
    ]:
        frozen = RTL / name
        transformed[name] = transform(frozen.read_text())
        records.append({"name": name, "frozen": str(frozen), "frozen_sha256": sha(frozen)})
    CANDIDATE.mkdir()
    for name in ["zero_dce_cnn_top.cpp", "zero_dce_cnn_top.h", "tb_zero_dce_cnn_dump.cpp"]:
        shutil.copy2(FROZEN / name, CANDIDATE / name)
    out = CANDIDATE / "rtl"
    out.mkdir()
    for record in records:
        candidate = out / record["name"]
        candidate.write_text(transformed[record["name"]], encoding="utf-8")
        record["candidate_sha256"] = sha(candidate)
    assert all(sha(Path(p)) == h for p, h in source_hashes.items())
    (CANDIDATE / "candidate_manifest.json").write_text(json.dumps({"kind": "generated_rtl_writer_scheduling_overlay", "credit_limit": 2, "frozen_cpp": source_hashes, "overlays": records}, indent=2), encoding="utf-8")
    print(json.dumps({"candidate": str(CANDIDATE), "changed_rtl": [r["name"] for r in records], "frozen_unchanged": True}))


if __name__ == "__main__":
    main()
