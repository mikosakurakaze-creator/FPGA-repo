"""Nonoverlapping low-DDR addresses for simulation, never board allocations."""


def align(value, boundary=4096):
    if value < 0 or boundary < 1 or boundary & (boundary - 1):
        raise ValueError('Invalid alignment request')
    return (value + boundary - 1) & ~(boundary - 1)


def validate_regions(regions, limit=0x80000000):
    """Check whole aligned DMA slots across both AXI masters."""
    ordered = sorted(regions, key=lambda r: r['base'])
    for i, region in enumerate(ordered):
        base, size = region['base'], region['allocation_bytes']
        if base < 0 or size <= 0 or base % 64 or size % 64 or base + size > limit:
            raise ValueError('Invalid low-DDR slot: ' + region['name'])
        if i and ordered[i-1]['base'] + ordered[i-1]['allocation_bytes'] > base:
            raise ValueError('Overlapping DDR slots: ' + ordered[i-1]['name'] + '/' + region['name'])
    return True


def frame_fixture(image_bytes, scratch_bytes, parameter_bytes, layout_bytes=1344):
    if min(image_bytes, scratch_bytes, parameter_bytes, layout_bytes) <= 0:
        raise ValueError('All payload lengths must be positive')
    feature_base = 0x10000000
    input_at = 4096
    output_at = align(input_at + image_bytes)
    scratch_at = align(output_at + image_bytes)
    feature_bytes = align(scratch_at + scratch_bytes)
    # Preserve the small-test parameter base, move it above the entire feature
    # aperture for large frames. HP0/HP3 address the same physical DDR.
    parameter_base = max(0x20000000, align(feature_base + feature_bytes, 65536))
    layout_at = align(parameter_bytes)
    parameter_capacity = align(layout_at + layout_bytes)
    regions = [dict(name=name, base=base, payload_bytes=size, allocation_bytes=align(size, 64))
               for name, base, size in [
                   ('input', feature_base + input_at, image_bytes),
                   ('output', feature_base + output_at, image_bytes),
                   ('scratch', feature_base + scratch_at, scratch_bytes),
                   ('parameters', parameter_base, parameter_bytes),
                   ('layout', parameter_base + layout_at, layout_bytes)]]
    validate_regions(regions)
    if feature_base + feature_bytes > parameter_base or parameter_base + parameter_capacity > 0x80000000:
        raise ValueError('Simulation RAM apertures overlap or exceed low DDR')
    return dict(kind='simulated_disjoint_low_ddr_not_board_allocation', feature_base=feature_base,
                feature_bytes=feature_bytes, input_at=input_at, output_at=output_at,
                scratch_at=scratch_at, parameter_base=parameter_base,
                parameter_capacity=parameter_capacity, layout_at=layout_at,
                regions=regions, cross_master_overlap_check=True)
