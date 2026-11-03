from pathlib import Path
import struct

def elf_build_note(raw):
    if raw[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', raw, 18)[0] != 183:
        raise RuntimeError('Expected AArch64 ELF64 module')
    offset = struct.unpack_from('<Q', raw, 40)[0]
    stride, count, strings = struct.unpack_from('<HHH', raw, 58)
    if stride != 64 or not 0 < strings < count or offset + stride*count > len(raw):
        raise RuntimeError('Invalid ELF section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, offset + i*stride) for i in range(count)]
    table = sections[strings]
    names = raw[table[4]:table[4]+table[5]]
    for section in sections:
        name = names[section[0]:].split(b'\0', 1)[0]
        if name == b'.note.gnu.build-id':
            note = raw[section[4]:section[4]+section[5]]
            if len(note) != section[5] or not note: raise RuntimeError('Invalid module build note')
            return note
    raise RuntimeError('Module build identity unavailable')

def verify_owner():
    device = Path('/sys/class/misc/kv260_dce_single_frame/device').resolve(strict=True)
    if ((device/'driver').resolve().name != 'kv260_dce_single_frame'
            or (device/'driver/module').resolve().name != 'kv260_single_frame'):
        raise RuntimeError('Single-frame driver ownership changed')
    node = (device/'of_node').resolve(strict=True)
    if node.parent != Path('/sys/firmware/devicetree/base'):
        raise RuntimeError('Expected root platform node')
    if (node/'compatible').read_bytes() != b'fpga-dce,kv260-single-frame-v1\0':
        raise RuntimeError('Wrong single-frame compatible')
    if (node/'reg').read_bytes() != struct.pack('>16I', 0, 0xa0020000, 0, 0x10000,
            0, 0xa0000000, 0, 0x10000, 0, 0xa0010000, 0, 0x10000, 0, 0xfd800000, 0, 0x1000):
        raise RuntimeError('Single-frame resources changed')
    if (node/'reg-names').read_bytes() != b'cnn\0bilinear\0curve\0smmu\0':
        raise RuntimeError('Resource names changed')
    if (node/'status').read_bytes() != b'okay\0': raise RuntimeError('Node disabled')
    for name in ['dma-ranges', 'dma-coherent', 'iommus', 'memory-region', 'firmware-name']:
        if (node/name).exists(): raise RuntimeError('Unexpected binding property ' + name)
