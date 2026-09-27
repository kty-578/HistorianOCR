"""Page-local region analysis. Coordinates are normalized, with a bottom-left origin."""

from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import median
import re
from reading_order import reading_order, validate_regions


@dataclass
class Region:
    id: str
    kind: str
    box: list[float]
    order: int
    lines: list[dict]
    side: str | None = None
    anchor: str | None = None
    relation: str | None = None
    review: bool = False
    evidence: list[str] = field(default_factory=list)


@dataclass
class PageLayout:
    regions: list[Region]
    warnings: list[str]
    version: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


def bounds(lines: list[dict]) -> list[float]:
    return [min(line['x'] for line in lines), min(line['y'] for line in lines),
            max(line['x'] + line['width'] for line in lines),
            max(line['y'] + line['height'] for line in lines)]


def mode_position(values: list[float]) -> float:
    counts = Counter(round(value / 0.012) for value in values)
    bucket = counts.most_common(1)[0][0]
    return median(value for value in values if round(value / 0.012) == bucket)


def footer_top(lines: list[dict]) -> float | None:
    main = [line for line in lines if 0.25 < line['y'] < 0.85 and line['width'] > 0.35]
    if len(main) < 4:
        return None
    height = median(line['height'] for line in main)
    width = median(line['width'] for line in main)
    marker = re.compile(r'^\s*(?:\([0-9ivxl]+\)|\[[0-9]+\]|[0-9]+[.)]|[*†‡]|[.,iIl1]\s+N[°o])', re.I)
    starts = []
    # A sustained pair of smaller columns can identify notes even when the
    # opening reference mark is unreadable. Require several rows in both columns.
    lower = [line for line in lines if 0.03 < line['y'] < 0.45
             and line['width'] < width * 0.7]
    paired = [line for line in lower if any(
        other is not line and abs(other['y'] - line['y']) < height * 0.6
        and (other['x'] > line['x'] + line['width'] + 0.015
             or line['x'] > other['x'] + other['width'] + 0.015)
        for other in lower)]
    # Separate vertically disconnected groups before testing their typography.
    for band in blocks(paired, False):
        divided = columns(band)
        if (len(divided) == 2 and all(len(group) >= 3 for group in divided)
                and median(line['height'] for line in band) < height * 0.85):
            starts.append(max(line['y'] + line['height'] for line in band))
    for line in lines:
        if not 0.03 < line['y'] < 0.4 or not marker.match(line['text']):
            continue
        parallel = any(abs(other['y'] - line['y']) < height * 0.6
                       and (other['x'] > line['x'] + line['width'] + 0.015
                            or line['x'] > other['x'] + other['width'] + 0.015)
                       for other in lines)
        continuation = [line]
        for following in sorted((item for item in lines if item['y'] < line['y']),
                                key=lambda item: -item['y']):
            if continuation[-1]['y'] - following['y'] > height * 1.5:
                break
            if following['x'] < line['x']+line['width'] and following['x']+following['width'] > line['x']:
                continuation.append(following)
        bibliography = re.search(r'\bN[°o]\s*\d', line['text'], re.I)
        if (line['height'] < height * 0.85
                or (bibliography and median(item['height'] for item in continuation) < height * 0.85)
                or (parallel and line['width'] < width * 0.7)):
            starts.append(line['y'] + line['height'])
    return max(starts) + 0.004 if starts else None


def fragments(line: dict, left: float, right: float) -> list[tuple[str, dict]]:
    words = line.get('words') or [line]
    groups: list[tuple[str, list[dict]]] = []
    for word in sorted(words, key=lambda item: item['x']):
        center = word['x'] + word['width'] / 2
        kind = 'left' if center < left - 0.008 else 'right' if center > right + 0.008 else 'body'
        if groups and groups[-1][0] == kind:
            groups[-1][1].append(word)
        else:
            groups.append((kind, [word]))
    result = []
    for kind, group in groups:
        x0, y0, x1, y1 = bounds(group)
        result.append((kind, {'text': ' '.join(word['text'] for word in group),
                             'x': x0, 'y': y0, 'width': x1-x0, 'height': y1-y0,
                             'words': group, 'source': line['source']}))
    return result


def blocks(lines: list[dict], split_indent: bool = True) -> list[list[dict]]:
    if not lines:
        return []
    ordered = sorted(lines, key=lambda line: -(line['y'] + line['height']/2))
    centers = [line['y'] + line['height']/2 for line in ordered]
    distances = [a-b for a,b in zip(centers, centers[1:]) if a-b > 0.003]
    spacing = median(distances) if distances else median(line['height'] for line in lines)
    if not split_indent:
        spacing = min(spacing, median(line['height'] for line in lines)*1.6)
    left = mode_position([line['x'] for line in lines])
    width = max(line['x']+line['width'] for line in lines)-left
    result = []
    for index, line in enumerate(ordered):
        indented = split_indent and 0.025*width < line['x']-left < 0.14*width
        if not result or centers[index-1]-centers[index] > spacing*1.55 or indented:
            result.append([])
        result[-1].append(line)
    return result


def columns(lines: list[dict]) -> list[list[dict]]:
    """Accept a vertical gutter only when multiple text rows support both columns."""
    if len(lines) < 4:
        return [lines] if lines else []
    left, _, right, _ = bounds(lines)
    width = right-left
    candidates = sorted({line['x'] for line in lines if left+width*.3 < line['x'] < left+width*.7})
    for edge in candidates:
        split = edge - 0.01
        a = [line for line in lines if line['x']+line['width'] <= split]
        b = [line for line in lines if line['x'] >= split]
        if len(a) < 2 or len(b) < 2:
            continue
        crossing = [line for line in lines if line not in a and line not in b]
        fragments_by_side = [[], []]
        for line in crossing:
            words = line.get('words', [])
            if not words or any(word['x'] < split < word['x']+word['width'] for word in words):
                break
            for side, group in enumerate(([w for w in words if w['x']+w['width'] <= split],
                                           [w for w in words if w['x'] >= split])):
                if group:
                    x0, y0, x1, y1 = bounds(group)
                    fragments_by_side[side].append({**line, 'words': group,
                        'text': ' '.join(w['text'] for w in sorted(group, key=lambda w: w['x'])),
                        'x': x0, 'y': y0, 'width': x1-x0, 'height': y1-y0})
        else:
            return columns(a+fragments_by_side[0]) + columns(b+fragments_by_side[1])
    return [lines]


def analyze_page(observations: list[dict]) -> PageLayout:
    lines = [{**line, 'source': index} for index,line in enumerate(observations) if line['text'].strip()]
    if not lines:
        return PageLayout([], [])
    boundary = footer_top(lines)
    footnotes = [line for line in lines if boundary is not None and line['y']+line['height']/2 < boundary]
    remaining = [line for line in lines if line not in footnotes]
    main = [line for line in remaining if .2 < line['y'] < .85 and line['width'] > .4]
    warnings = []
    regions = []

    def add(kind, group, side=None, review=False, evidence=None):
        if group:
            regions.append(Region(f'r{len(regions)+1}', kind, bounds(group), len(regions), group,
                                  side=side, review=review, evidence=evidence or []))

    if len(main) < 4:
        warnings.append('正文边界需要核对。')
        body_columns = columns(remaining)
        for group in body_columns:
            for block in blocks(group):
                add('body', block, review=True, evidence=['text_positions'])
    else:
        left = mode_position([line['x'] for line in main])
        right = mode_position([line['x']+line['width'] for line in main])
        typical_height = median(line['height'] for line in main)
        body = []
        margin = {'left': [], 'right': []}
        for line in remaining:
            if line['y'] > .925 and line['height'] < typical_height*1.15:
                add('header', [line], evidence=['top_position', 'text_height'])
                continue
            # Large, isolated display text remains a title, including text wider than the body.
            if line['height'] > typical_height*1.45:
                body.append(line)
                continue
            for kind, fragment in fragments(line, left, right):
                if kind == 'body':
                    body.append(fragment)
                else:
                    margin[kind].append(fragment)
        for block in blocks(body):
            height = median(line['height'] for line in block)
            letters = ''.join(char for line in block for char in line['text'] if char.isalpha())
            capitals = sum(char.isupper() for char in letters) / max(1, len(letters))
            kind = 'title' if height > typical_height*1.4 or capitals > .8 else 'body'
            add(kind, block, evidence=['main_text_alignment', 'line_spacing'])
        for side, group in margin.items():
            for block in blocks(group, False):
                add('marginal_note', block, side, True, ['outside_main_text', 'word_positions'])
    for column in columns(footnotes):
        add('footnote', column, evidence=['bottom_position', 'text_height_or_columns'])
        regions[-1].box[1] = max(0, min(line['y'] for line in footnotes)
                                - median(line['height'] for line in footnotes)*1.2)
    body_regions = [region for region in regions if region.kind in ('body','title')]
    for region in regions:
        if region.kind == 'marginal_note' and body_regions:
            center = (region.box[1]+region.box[3])/2
            anchor = min(body_regions, key=lambda item: max(item.box[1]-center, center-item.box[3], 0))
            region.anchor = anchor.id
            region.relation = 'vertical_proximity'
    # Apply independent reading orders to body, side notes and footnotes.
    regions = [region for kinds in (('header',), ('body', 'title'), ('marginal_note',),
                                    ('footnote', 'annotation', 'unknown'))
               for region in reading_order([item for item in regions if item.kind in kinds])]
    warnings.extend(validate_regions(regions, observations))
    for order, region in enumerate(regions):
        region.order = order
    return PageLayout(regions, warnings)
