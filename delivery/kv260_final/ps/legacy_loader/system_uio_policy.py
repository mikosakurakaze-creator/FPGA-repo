"""Audit only the four PS AXI monitors identified in the captured KV260 DT.

Only read sysfs metadata. Never open /dev/uio*, map registers, or unbind drivers.
"""
import re
import struct

PS_MONITORS = {value + '.perf-monitor': int(value, 16)
               for value in ['ffa00000', 'fd0b0000', 'fd490000', 'ffa10000']}


def validate_uio_record(record):
    name = record['platform_device']
    if name not in PS_MONITORS:
        raise RuntimeError('Unreviewed UIO device: ' + record['uio'])
    address = PS_MONITORS[name]
    expected_device = 'devices/platform/axi/' + name
    expected_node = 'firmware/devicetree/base/axi/perf-monitor@' + format(address, 'x')
    if record['device_path'] != expected_device:
        raise RuntimeError('UIO platform path differs from captured PS monitor')
    if record['driver_path'] != 'bus/platform/drivers/xilinx-axipmon':
        raise RuntimeError('UIO driver differs from reviewed xilinx-axipmon')
    if record['of_node_path'] != expected_node or record['compatible'] != ['xlnx,axi-perf-monitor']:
        raise RuntimeError('UIO DT identity differs from captured PS monitor')
    if record['dt_address'] != address or record['dt_bytes'] != 65536:
        raise RuntimeError('UIO DT register range mismatch')
    maps = record['maps']
    if set(maps) != {'map0', 'map1'}:
        raise RuntimeError('Unexpected PS monitor UIO mappings')
    if maps['map0'] != {'address': address, 'bytes': 65536, 'offset': 0}:
        raise RuntimeError('UIO hardware map differs from captured PS monitor')
    # The Xilinx APM driver exposes a second 4096-byte LOGICAL parameter buffer.
    # Its sysfs address is kernel virtual metadata, not a DMA/physical address.
    if maps['map1']['bytes'] != 4096 or maps['map1']['offset'] != 0:
        raise RuntimeError('Unexpected PS monitor parameter buffer mapping')


def audit_system_uios(class_root, sysfs_root):
    if not class_root.exists():
        return []
    records = []
    seen = set()
    for entry in sorted(class_root.iterdir()):
        if not re.fullmatch(r'uio[0-9]+', entry.name):
            if entry.is_dir():
                raise RuntimeError('Unreviewed directory in UIO class: ' + entry.name)
            continue
        try:
            device = (entry / 'device').resolve(strict=True)
            node = (device / 'of_node').resolve(strict=True)
            driver = (device / 'driver').resolve(strict=True)
            reg = (node / 'reg').read_bytes()
            if len(reg) != 16:
                raise RuntimeError('Unexpected PS monitor DT register cell format')
            address, size = struct.unpack('>QQ', reg)
            maps = {}
            for mapping in sorted((entry / 'maps').iterdir()):
                if not mapping.is_dir():
                    raise RuntimeError('Unexpected UIO mapping entry')
                maps[mapping.name] = {
                    'address': int((mapping / 'addr').read_text().strip(), 0),
                    'bytes': int((mapping / 'size').read_text().strip(), 0),
                    'offset': int((mapping / 'offset').read_text().strip(), 0),
                }
            record = {
                'uio': entry.name, 'platform_device': device.name,
                'device_path': device.relative_to(sysfs_root).as_posix(),
                'driver_path': driver.relative_to(sysfs_root).as_posix(),
                'of_node_path': node.relative_to(sysfs_root).as_posix(),
                'compatible': [value.decode() for value in (node / 'compatible').read_bytes().split(b'\0') if value],
                'dt_address': address, 'dt_bytes': size, 'maps': maps,
            }
        except (OSError, ValueError, UnicodeError) as exc:
            raise RuntimeError('UIO devices present; metadata cannot be verified: ' + entry.name) from exc
        validate_uio_record(record)
        if record['platform_device'] in seen:
            raise RuntimeError('Duplicate UIO registration of a PS monitor')
        seen.add(record['platform_device'])
        records.append(record)
    return records
