"""Read actual Vivado functional-netlist boundaries for diagnostic simulation."""
from pathlib import Path
import re


def wrapper(path):
    text = Path(path).read_text()
    match = re.search(r'\bmodule\s+(\w+)\s*\((.*?)\);(.*?)\bendmodule', text, re.S)
    if not match:
        raise RuntimeError('No wrapper in ' + str(path))
    names = [name.strip() for name in match[2].split(',')]
    body = re.sub(r'\(\*.*?\*\)', '', match[3], flags=re.S)
    ports = {}
    for direction, width, name in re.findall(
            r'^\s*(input|output)\s+(\[\d+:\d+\])?\s*(\\\S+|\w+)\s*;', body, re.M):
        ports[name] = (direction, width)
    if set(names) != set(ports):
        raise RuntimeError('Unparsed wrapper declarations: ' + str(set(names) ^ set(ports)))
    return match[1], ports


def verilog_name(name):
    return name + (' ' if name.startswith('\\') else '')
