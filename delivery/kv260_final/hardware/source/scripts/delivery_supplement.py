"""Generate BIN, actual-HWH register tables and clock/reset guide for a new image."""
from pathlib import Path
import csv, hashlib, json, shutil, subprocess
from xml.etree import ElementTree as ET
from run_checks import vendor_runtime

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def props(node):
    return {n.get('NAME'): n.get('VALUE') for n in node.findall('PROPERTY')}

def export_registers(out):
    address = json.loads((out / 'address_map.json').read_text(encoding='utf-8'))
    tree = ET.parse(out / 'joint_system.hwh').getroot()
    modules = {m.get('INSTANCE'): m for m in tree.iter('MODULE')}
    records, fields, cores = [], [], {}
    translations = {'read-only': '只读', 'write-only': '只写', 'read-write': '读写'}
    lines = ['# 六核寄存器表', '',
             '来源为本包 joint_system.hwh 与 address_map.json；以下偏移是字节偏移，绝对地址为控制基址加偏移。所有列出的寄存器均为32位，64位指针由低、高两个32位寄存器组成。', '',
             'register_map.csv 便于表格软件查看；register_map.json 保留原始属性及位域；register_fields.csv 列出HWH实际给出的位域。融合核HWH未定义位域，控制位的权威语义见 docs/fusion_contract.md，不套用其他HLS核的行为。', '',
             '本镜像采用轮询，关闭 auto_restart。启动前写完全部配置并执行屏障；读取done时保存该次状态，不能反复读清后再期待原状态。地址寄存器写物理地址，使用本帧独立且64字节对齐的DDR缓冲。', '']
    for key, spec in sorted(address['cores'].items(), key=lambda kv: int(kv[1]['base'], 0)):
        module = modules[spec['cell']]
        params = {p.get('NAME'): p.get('VALUE') for p in module.iter('PARAMETER')}
        base_parameter = 'C_BASEADDR' if key == 'fusion' else 'C_S_AXI_CONTROL_BASEADDR'
        assert int(params[base_parameter], 0) == int(spec['base'], 0)
        base = int(spec['base'], 0)
        regs = []
        for reg in module.iter('REGISTER'):
            p = props(reg)
            offset = int(p['ADDRESS_OFFSET'], 0)
            assert int(p['SIZE'], 0) == 32 and offset % 4 == 0 and offset + 4 <= spec['range']
            row = {'core': key, 'instance': spec['cell'], 'base': f'0x{base:08X}',
                   'offset': f'0x{offset:02X}', 'absolute_address': f'0x{base+offset:08X}',
                   'register': reg.get('NAME'), 'width_bits': 32, 'access': p['ACCESS'],
                   'reset_value': p.get('RESET_VALUE', ''), 'description': p.get('DESCRIPTION', '')}
            fs = []
            for field in reg.findall('./FIELDS/FIELD'):
                fp = props(field)
                fs.append({'name': field.get('NAME'), 'properties': fp})
                fields.append({'core': key, 'register': row['register'], 'register_offset': row['offset'],
                               'field': field.get('NAME'), 'bit_offset': fp.get('BIT_OFFSET', ''),
                               'bit_width': fp.get('BIT_WIDTH', ''), 'access': fp.get('ACCESS', ''),
                               'read_action': fp.get('READ_ACTION', ''),
                               'modified_read_values': fp.get('MODIFIED_READ_VALUES', ''),
                               'description': fp.get('DESCRIPTION', '')})
            regs.append(dict(row, properties=p, fields=fs))
            records.append(row)
        assert len({r['offset'] for r in regs}) == len(regs)
        cores[key] = {'instance': spec['cell'], 'base': spec['base'], 'range_bytes': spec['range'], 'registers': regs}
        lines += [f"## {key}  {spec['base']}", '', '| 偏移 | 绝对地址 | 寄存器 | 位宽 | 访问 |', '| --- | --- | --- | --- | --- |']
        lines += [f"| `{r['offset']}` | `{r['absolute_address']}` | `{r['register']}` | 32 | {translations[r['access']]} |" for r in regs]
        lines.append('')
    assert len(cores) == 6 and len(records) == 91
    for name, rows in [('register_map.csv', records), ('register_fields.csv', fields)]:
        with (out / name).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write_json(out / 'register_map.json', {'source_hwh_sha256': sha(out / 'joint_system.hwh'), 'cores': cores})
    lines += ['## 固定配置与调度', '',
              '- prepare：abi_cookie偏移0x48，值0x4A503031。',
              '- CNN：使用包内四个冻结模型数组；输入小图106×60，输出三通道小参数图。',
              '- Bilinear：input_height偏移0x28写60，input_width偏移0x30写106。',
              '- Curve：count偏移0x34写2747520。',
              '- D：height偏移0x30写720，width偏移0x38写1272，abi_cookie偏移0x40写0x44433031。work_cycles/input_cycles只按实际核输出解释，未在真板测量。',
              '- fusion：W_I/W_L/W_D偏移0x48/0x50/0x58，各为[0,32768]，和为32768；cookie偏移0x60写0x4A463031；frame_id偏移0x68，成功后核对0x70的completed_frame。AP_CTRL bit7不实现auto_restart。',
              '- prepare成功后可重叠启动CNN和D；CNN→Bilinear→Curve按完成依赖推进；本帧Curve和D均成功后才启动fusion。完整顺序和异常恢复见docs/loading_order.md。', '']
    (out / 'register_map.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return {'cores': len(cores), 'registers': len(records), 'hwh_field_records': len(fields), 'source_hwh_sha256': sha(out / 'joint_system.hwh')}

def add_supplements(out,build,payload,vivado):
    runtime=out.parent/(out.name+"_bootgen_runtime")
    runtime.mkdir(parents=True, exist_ok=False)
    _,env=vendor_runtime(runtime,vivado)
    exe=runtime/"vendor_runtime/bootgen.exe"
    shutil.copy2(vivado/"bin/unwrapped/win64.o/bootgen.exe",exe)
    env["RDI_PROG"]=exe.as_posix()
    bif=out/"evidence/bootgen_joint.bif"
    bif.write_text("all:\n{\n  joint_system.bit\n}\n",encoding="ascii")
    command=[str(exe),"-arch","zynqmp","-image","evidence/bootgen_joint.bif","-process_bitstream","bin","-w","on"]
    log=out/"evidence/bootgen.log"
    with log.open("xb") as f:proc=subprocess.run(command,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT)
    receipt={"command":command,"exit_code":proc.returncode,"log_sha256":sha(log),"board_operations":0}
    write_json(out/"evidence/bootgen_result.json",receipt)
    if proc.returncode:raise ValueError("Bootgen failed; preserve logs and incomplete package")
    expected=bytearray(len(payload))
    if len(payload)%4:raise ValueError("Non-word-aligned bit payload")
    for i in range(4):expected[i::4]=payload[3-i::4]
    if (out/"joint_system.bit.bin").read_bytes()!=expected:raise ValueError("Bootgen BIN differs from word-swapped BIT payload")
    receipt.update(bin_sha256=sha(out/"joint_system.bit.bin"),bit_sha256=sha(out/"joint_system.bit"),configuration_bytes=len(payload),word_swapped_payload_matches=True)
    write_json(out/"evidence/bootgen_result.json",receipt)
    registers=export_registers(out)
    write_json(out/"evidence/register_export.json",registers)
    address=json.loads((out/"address_map.json").read_text())
    accepted=json.loads((build/"acceptance.json").read_text())
    lines=["# 时钟与复位说明","","来自本包实际 HWH、地址审计和同次新实现；不得和旧镜像混用。","", "| 核 | 基址 | 频率/Hz | 时钟 | 低有效复位 |", "| --- | --- | --- | --- | --- |"]
    for key,v in address["cores"].items():lines.append(f"| {key} | {v['base']} | {v['clock_hz']} | {v['clock_net']} | {v['active_low_reset_net']} |")
    lines += ["", "PS HPM 控制侧及 HP0–HP3 数据侧工作于约 100 MHz。D 的约 200 MHz 域经双时钟 SmartConnect 连接控制/读/写通路。各核之间通过同一片 DDR 的不同缓冲区交接；D 内部层间使用片上 FIFO。", "", "PS/pl_resetn0 低有效复位送入两组 proc_sys_reset，各自在所属时钟域同步释放。超时或 AXI 失败后作废输出，停止新启动，待所有 outstanding 静止或完成全 PL 恢复后才复用缓冲。", "",f"本次 routed WNS={accepted['timing']['WNS_ns']} ns，WHS={accepted['timing']['WHS_ns']} ns；完整覆盖、CDC、DRC、bus-skew 及 route 见 reports/。这是新流水融合的联合实现结果；未做真板时钟/FPS 测量。"]
    (out/"clock_reset.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (out/"README.md").write_text("""# KV260 联合硬件包：流水 Prepare + 三路融合

本包由新六核综合、布局布线、时序/CDC/DRC/覆盖验收和同图 Golden 通过后生成。融合 revision 3 使用 128-bit、最长 64 拍突发、三输入/一输出 FIFO、八路五级计算流水及独立读写引擎。

Prepare 使用 128-bit 连续突发、片上分块重排和五任务 DATAFLOW；从一次 RGB 读取中生成原图、D 输入及 CNN 小图。数值合同与软件寄存器偏移不变，详见 `docs/prepare_pipeline.md`。`evidence/prepare_pipeline_acceptance.json` 绑定完整图数值、RTL、综合和实际 128-bit 集成通路证据。

- `joint_system.bit` + 同名 `joint_system.hwh`：PYNQ overlay 输入。
- `joint_system.bit.bin`：Bootgen 2025.2 转换结果，已独立核对 BIT 配置数据字节序。
- `joint_system.xsa`：同次硬件平台；BIT/HWH 与 XSA 中规范产物对应。
- `register_map.md/csv/json`、`address_map.json`：实际 HWH 提取的六核寄存器和地址表。
- `clock_reset.md`、`docs/loading_order.md`：时钟复位、加载调用顺序及异常恢复。
- `runtime/run_pipeline_pynq.py`：三槽连续帧调用入口，记录批次FPS、输出间隔及逐帧哈希；本轮未在板端执行。
- `evidence/fusion_pipeline_acceptance.json`：精确源码/IP 身份、全帧数值与吞吐仿真证据；`reports/` 为本次实现报告。
- `SHA256SUMS` 包含 manifest 和所有 payload 的 SHA256；ZIP 的 SHA256 位于旁边 `.zip.sha256` 文件。

30 FPS 为目标。融合在明确的内存模型下已检查每帧不超过 33.333 ms；这不是整个系统或真板 30 FPS 的实测结论。单帧参考调度仍有 prepare→模型路径→fusion 的完成依赖；持续帧率还取决于其他核、帧间调度、PS 和共享 DDR。上板前先校验哈希，按加载文档确认 LOW DDR/64-byte 对齐及 DMA/cache 所有权，运行后核对 Golden 与真实持续 FPS。
""",encoding="utf-8")
