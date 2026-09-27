"""Interval-based XY-Cut ordering; see THIRD_PARTY.md for algorithm sources.

Coordinates use a bottom-left origin. Interval unions avoid allocating pixel
histograms and work at any page resolution.
"""


def projection_groups(items, axis, minimum_gap=0.003):
    ordered = sorted(items, key=lambda item: item.box[axis])
    groups = []
    end = float('-inf')
    for item in ordered:
        if not groups or item.box[axis] > end + minimum_gap:
            groups.append([])
            end = item.box[axis+2]
        else:
            end = max(end, item.box[axis+2])
        groups[-1].append(item)
    return groups


def reading_order(items):
    if len(items) <= 1:
        return list(items)
    for axis in (0, 1):
        groups = projection_groups(items, axis)
        if len(groups) > 1:
            if axis == 1:
                groups.reverse()
            return [item for group in groups for item in reading_order(group)]
    return sorted(items, key=lambda item: (-item.box[3], item.box[0], item.id))


def overlap_fraction(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    area = min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1]))
    return intersection / area if area > 0 else 0


def validate_regions(regions, observations):
    warnings = []
    expected = {i for i, line in enumerate(observations) if line['text'].strip()}
    assigned = {line['source'] for region in regions for line in region.lines}
    if assigned != expected:
        raise ValueError('页面区域未完整覆盖检测到的文字。')
    for index, region in enumerate(regions):
        x0, y0, x1, y1 = region.box
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise ValueError('页面区域坐标超出图像范围。')
        for other in regions[index+1:]:
            if overlap_fraction(region.box, other.box) > 0.15:
                region.review = other.review = True
                warnings.append(f'区域 {region.id} 与 {other.id} 存在交叠，请核对文字归属。')
    return warnings
