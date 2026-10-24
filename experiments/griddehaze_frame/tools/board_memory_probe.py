"""Read-only Linux inventory. Does not allocate DMA, touch MMIO, or change boot settings."""
import json
from pathlib import Path
import platform


def read(path):
    try: return Path(path).read_text(encoding='utf-8',errors='replace').strip().replace('\0',' ')
    except OSError: return None


if __name__=='__main__':
    if platform.system()!='Linux': raise SystemExit('Run on the target KV260 Linux system')
    mem=read('/proc/meminfo') or ''
    result=dict(kind='read_only_inventory_not_DMA_allocation_proof',kernel=platform.release(),
                model=read('/sys/firmware/devicetree/base/model'),cmdline=read('/proc/cmdline'),
                memory={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in mem.splitlines()
                        if line.startswith(('MemTotal:','MemAvailable:','CmaTotal:','CmaFree:'))},
                iommu_group_count=len(list(Path('/sys/kernel/iommu_groups').glob('*'))) if Path('/sys/kernel/iommu_groups').exists() else None,
                required_scratch_bytes_720p=471859200,
                required_features_and_weights_bytes_720p=484851520,
                limitations=['CmaFree is not proof of one contiguous allocatable region.',
                             'Actual coherent DMA allocation and DMA mask must be verified by the matching kernel driver.',
                             'No conclusion about SMMU bypass or final DT/XSA solely from this inventory.'])
    print(json.dumps(result,indent=2,ensure_ascii=False))
