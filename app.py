"""Local transcription workspace for scanned historical PDFs."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import html
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
from threading import RLock
from statistics import median
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, unquote

from PIL import Image, ImageOps
from session_storage import SessionStorage
from layout import analyze_page
from ocr_engines import recognize_regions, segmentation_mode, tesseract_available, default_engine, layout_engine
from pdf_pages import page_count, render_page


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def executable(name: str) -> str:
    """Find installed tools in the shell or the bundled dependency runtime."""
    available = shutil.which(name)
    if available:
        return available
    candidates = []
    candidates += [Path('/opt/homebrew/bin') / name, Path('/usr/local/bin') / name,
                   Path('/usr/bin') / name]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise FileNotFoundError(f'缺少程序所需的工具 {name}，请检查本机安装。')


YEAR_GLYPH_PATTERN = re.compile(r"(?<!\w)([iIl1])([0-9])([iIl0-9])[ \t]?([0-9])(?=\W|$|n\.)")
YEAR_GLYPH_TRANSLATION = str.maketrans({"i": "1", "I": "1", "l": "1"})
DATE_DAY_PATTERN = re.compile(
    r"(?P<context>\b(?:le|du|ce)\s+)(?P<day>[^\s]{1,5})\s+"
    r"(?P<month>janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b",
    re.IGNORECASE,
)


def suspicious_date_days(text: str) -> list[re.Match[str]]:
    return [match for match in DATE_DAY_PATTERN.finditer(text)
            if not re.fullmatch(r"(?:[1-9]|[12][0-9]|3[01]|1er|premier)", match['day'], re.IGNORECASE)]


def date_context_pattern(text: str, match: re.Match[str]) -> re.Pattern[str]:
    # Require nearby wording to identify the same date on the scanned page.
    prefix = re.findall(r"\w+", text[max(0, match.start() - 65):match.start()])[-4:]
    words = prefix + [match['context'].strip()]
    return re.compile(r"\b" + r"\W+".join(map(re.escape, words))
                      + r"\s+(?P<day>[1-9]|[12][0-9]|3[01])\s+"
                      + re.escape(match['month']) + r"\b", re.IGNORECASE)


def join_ocr_lines(raw: str) -> tuple[str, int]:
    """Join OCR line wraps while retaining blank lines and uncertain hyphens."""
    blocks: list[str] = []
    current = ""
    uncertain = 0
    for source_line in raw.splitlines():
        line = re.sub(r"[ \t]+", " ", source_line).strip()
        if not line:
            if current:
                blocks.append(current)
                current = ""
            continue
        if not current:
            current = line
            continue
        if current.endswith(("-", "\u00ad")) and line[0].islower():
            current = current[:-1] + line
            uncertain += 1
        else:
            current += " " + line
    if current:
        blocks.append(current)
    return "\n\n".join(blocks), uncertain


def correct_year_glyphs(text: str) -> str:
    """Normalize ambiguous 1 glyphs inside four-digit year-shaped tokens."""
    def replace(match: re.Match[str]) -> str:
        if not any(glyph in "iIl" for glyph in (match.group(1), match.group(3))):
            return match.group(0)
        return "".join(match.groups()).translate(YEAR_GLYPH_TRANSLATION)

    return YEAR_GLYPH_PATTERN.sub(replace, text)


def document_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paragraph_lines(lines: list[dict]) -> str:
    """Preserve paragraph starts from indentation and vertical spacing in one column."""
    if not lines:
        return ""
    ordered = sorted(lines, key=lambda line: -(line['y'] + line['height'] / 2))
    lefts = sorted(line['x'] for line in ordered)
    left = lefts[len(lefts) // 5]
    right = max(line['x'] + line['width'] for line in ordered)
    width = right - left
    centers = [line['y'] + line['height'] / 2 for line in ordered]
    distances = [a - b for a, b in zip(centers, centers[1:]) if a > b]
    spacing = median(distances) if distances else 0
    output = []
    for index, line in enumerate(ordered):
        if index:
            gap = centers[index - 1] - centers[index]
            indented = width * 0.025 < line['x'] - left < width * 0.14
            separated = spacing > 0 and gap > spacing * 1.55
            if indented or separated:
                output.append("")
        output.append(line['text'])
    return "\n".join(output)


class Workspace:
    def __init__(
        self,
        pdf: Path,
        first_page: int,
        last_page: int | None,
        printed_start_pdf: int | None,
        printed_start_page: int,
    ) -> None:
        self.lock = RLock()
        self.pdf = pdf.resolve(strict=True)
        self.total_pages = page_count(self.pdf)
        self.first_page = first_page
        self.last_page = last_page or self.total_pages
        if not 1 <= self.first_page <= self.last_page <= self.total_pages:
            raise ValueError("Page range is outside this PDF")
        self.printed_start_pdf = printed_start_pdf
        self.printed_start_page = printed_start_page
        self.digest = document_digest(self.pdf)
        self.token = secrets.token_urlsafe(32)
        DATA.mkdir(exist_ok=True)
        self.cache = DATA / "rendered" / self.digest
        self.database = DATA / "annotations.sqlite3"
        with self.connect() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS pages (
                    document_sha256 TEXT NOT NULL,
                    pdf_page INTEGER NOT NULL,
                    printed_label TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    edited_text TEXT NOT NULL,
                    notes_text TEXT NOT NULL DEFAULT '',
                    import_version INTEGER NOT NULL DEFAULT 3,
                    vision_text TEXT NOT NULL DEFAULT '',
                    vision_notes TEXT NOT NULL DEFAULT '',
                    vision_data TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (document_sha256, pdf_page)
                )"""
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(pages)")}
            if "notes_text" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN notes_text TEXT NOT NULL DEFAULT ''")
            if "import_version" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN import_version INTEGER NOT NULL DEFAULT 1")
            if "vision_text" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN vision_text TEXT NOT NULL DEFAULT ''")
            if "vision_notes" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN vision_notes TEXT NOT NULL DEFAULT ''")
            if "layout_data" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN layout_data TEXT NOT NULL DEFAULT ''")
            if "vision_data" not in columns:
                db.execute("ALTER TABLE pages ADD COLUMN vision_data TEXT NOT NULL DEFAULT ''")
            db.execute(
                """CREATE TABLE IF NOT EXISTS page_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_sha256 TEXT NOT NULL,
                    pdf_page INTEGER NOT NULL,
                    printed_label TEXT NOT NULL,
                    edited_text TEXT NOT NULL,
                    notes_text TEXT NOT NULL,
                    saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database, timeout=20)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def check_page(self, number: int) -> None:
        if not self.first_page <= number <= self.last_page:
            raise ValueError("Page is outside the selected range")

    def default_label(self, number: int) -> str:
        if self.printed_start_pdf is None or number < self.printed_start_pdf:
            return "待确认"
        return str(self.printed_start_page + number - self.printed_start_pdf)

    def page(self, number: int) -> dict[str, str]:
        self.check_page(number)
        with self.lock:
            with self.connect() as db:
                row = db.execute(
                    "SELECT printed_label,raw_text,edited_text,notes_text,import_version,vision_text,vision_notes "
                    "FROM pages WHERE document_sha256=? AND pdf_page=?",
                    (self.digest, number),
                ).fetchone()
            if row is None or row[4] < 7:
                self.recognize_image(number)
                with self.connect() as db:
                    row = db.execute(
                        "SELECT printed_label,raw_text,edited_text,notes_text,import_version,vision_text,vision_notes "
                        "FROM pages WHERE document_sha256=? AND pdf_page=?",
                        (self.digest, number),
                    ).fetchone()
        return {
            "printed_label": row[0], "raw_text": row[1],
            "edited_text": row[2], "notes_text": row[3],
            "vision_text": row[5], "vision_notes": row[6],
        }

    def save(self, number: int, label: str, edited: str, notes: str) -> None:
        self.page(number)
        if len(label) > 80 or len(edited) > 2_000_000 or len(notes) > 2_000_000:
            raise ValueError("Submitted content is too large")
        label = label.strip() or "待确认"
        edited = correct_year_glyphs(edited)
        notes = correct_year_glyphs(notes)
        with self.connect() as db:
            previous = db.execute(
                "SELECT printed_label, edited_text, notes_text FROM pages "
                "WHERE document_sha256=? AND pdf_page=?",
                (self.digest, number),
            ).fetchone()
            if previous == (label, edited, notes):
                return
            db.execute(
                "INSERT INTO page_history (document_sha256,pdf_page,printed_label,edited_text,notes_text) "
                "VALUES (?,?,?,?,?)",
                (self.digest, number, *previous),
            )
            db.execute(
                "UPDATE pages SET printed_label=?, edited_text=?, notes_text=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE document_sha256=? AND pdf_page=?",
                (label, edited, notes, self.digest, number),
            )

    def image(self, number: int) -> bytes:
        self.check_page(number)
        target = self.cache / f"{number:04d}.png"
        if not target.exists():
            self.cache.mkdir(parents=True, exist_ok=True)
            render_page(self.pdf, number, target, max_size=1500)
        return target.read_bytes()

    def ocr_image(self, number: int) -> Path:
        self.check_page(number)
        target = self.cache / f"{number:04d}-ocr.png"
        if not target.exists():
            self.cache.mkdir(parents=True, exist_ok=True)
            render_page(self.pdf, number, target)
        return target

    def vision_binary(self) -> Path:
        bundled = os.environ.get('OCR_VISION_BINARY')
        if bundled:
            binary = Path(bundled)
            if not binary.is_file():
                raise FileNotFoundError('内置 Apple Vision 组件缺失，请重新获取完整项目。')
            return binary
        source = ROOT / "vision_ocr.swift"
        binary = ROOT / ".cache" / "vision_ocr"
        if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
            binary.parent.mkdir(exist_ok=True)
            subprocess.run([executable("swiftc"), "-o", str(binary), str(source)], check=True, capture_output=True)
        return binary

    def image_lines(self, image: Path, engine: str, psm: int = 3) -> list[dict]:
        binary = self.vision_binary() if engine == 'vision' else None
        with Image.open(image) as page_image:
            job = {'region_id': 'page', 'image': str(image), 'width': page_image.width,
                   'height': page_image.height, 'psm': psm}
        return recognize_regions([job], engine, binary)[0]['lines']

    def verify_date_days(self, number: int, text: str, page_lines: list[dict] | None = None) -> str:
        matches = list(DATE_DAY_PATTERN.finditer(text))
        if not matches:
            return text
        image = self.ocr_image(number)
        detector = layout_engine()
        key = hashlib.sha256(("date-check-v5" + text + detector).encode()).hexdigest()[:24]
        evidence = self.cache / f"{number:04d}-dates-{key}.json"
        if evidence.exists():
            return json.loads(evidence.read_text(encoding='utf-8'))["text"]
        lines = page_lines if page_lines is not None else self.image_lines(image, detector)
        decisions = []
        corrected = text
        with Image.open(image) as page_image:
            for match in reversed(matches):
                pattern = date_context_pattern(text, match)
                candidates = [(line, pattern.search(line['text'])) for line in lines]
                candidates = [(line, found) for line, found in candidates if found]
                if len(candidates) != 1:
                    continue
                line, found = candidates[0]
                if found['day'] == match['day']:
                    continue
                left = max(0, int(line['x'] * page_image.width) - 25)
                top = max(0, int((1 - line['y'] - line['height']) * page_image.height) - 25)
                right = min(page_image.width, int((line['x'] + line['width']) * page_image.width) + 25)
                bottom = min(page_image.height, int((1 - line['y']) * page_image.height) + 25)
                crop = self.cache / f"{number:04d}-date-{key}-{match.start()}.png"
                page_image.crop((left, top, right, bottom)).save(crop)
                crop_lines = self.image_lines(crop, detector, 7)
                crop_text = ' '.join(item['text'] for item in crop_lines)
                confirmations = list(pattern.finditer(crop_text))
                if len(confirmations) != 1 or confirmations[0]['day'] != found['day']:
                    continue
                corrected = corrected[:match.start('day')] + found['day'] + corrected[match.end('day'):]
                decisions.append({'region': [left, top, right, bottom], 'day': found['day'],
                                  'page_reading': line, 'region_reading': crop_lines})
        evidence.write_text(json.dumps({'text': corrected, 'confirmations': decisions}, ensure_ascii=False, indent=2), encoding='utf-8')
        return corrected

    def recognize_image(self, number: int, engine: str | None = None) -> str:
        self.check_page(number)
        engine = engine or default_engine()
        if engine not in ('vision', 'tesseract'):
            raise ValueError('未知的识别方式。')
        with self.lock:
            return self._recognize_image(number, engine)

    def _recognize_image(self, number: int, engine: str = 'vision') -> str:
        image = self.ocr_image(number)
        binary = self.vision_binary() if engine == 'vision' else None
        lines = self.image_lines(image, layout_engine())
        layout = analyze_page(lines)
        layout_path = self.cache / f'{number:04d}-layout.json'
        layout_path.write_text(json.dumps(layout.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        results = []
        body_parts = []
        note_parts = []
        jobs = []
        crops = {}
        with Image.open(image) as page_image:
            for region in layout.regions:
                x0, y0, x1, y1 = region.box
                box = (max(0, int(x0 * page_image.width)-2),
                       max(0, int((1-y1) * page_image.height)-2),
                       min(page_image.width, int(x1 * page_image.width)+3),
                       min(page_image.height, int((1-y0) * page_image.height)+3))
                crop = self.cache / f'{number:04d}-{region.id}.png'
                padded = ImageOps.expand(page_image.crop(box), border=32, fill='white')
                padded.save(crop)
                jobs.append({'region_id': region.id, 'image': str(crop),
                             'width': padded.width, 'height': padded.height,
                             'psm': segmentation_mode(region)})
                crops[region.id] = box
        recognized = recognize_regions(jobs, engine, binary)
        if [item['region_id'] for item in recognized] != [region.id for region in layout.regions]:
            raise ValueError('识别结果与页面区域不一致。')
        for region, recognition in zip(layout.regions, recognized):
            region_lines = recognition['lines']
            content = correct_year_glyphs(join_ocr_lines(paragraph_lines(region_lines))[0])
            if not content and region.lines:
                region.review = True
                layout.warnings.append(f'区域 {region.id} 未识别出文字，请核对原图。')
            results.append({**recognition, 'kind': region.kind, 'text': content,
                            'pixel_box': list(crops[region.id]), 'padding': 32})
            if region.kind in ('body', 'title'):
                body_parts.append(content)
            elif region.kind == 'marginal_note':
                side = '左侧' if region.side == 'left' else '右侧'
                note_parts.append(f'侧注（{side}）：{content}')
            elif region.kind in ('footnote', 'annotation', 'unknown'):
                note_parts.append(content)
        body = '\n\n'.join(part for part in body_parts if part)
        notes = '\n\n'.join(part for part in note_parts if part)
        edited = self.verify_date_days(number, body, lines)
        joined_notes = notes
        record = layout.to_dict()
        record['ocr_engine'] = engine
        record['layout_engine'] = layout_engine()
        record['recognition'] = results
        layout_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        with self.connect() as db:
            previous = db.execute(
                "SELECT printed_label, edited_text, notes_text FROM pages "
                "WHERE document_sha256=? AND pdf_page=?",
                (self.digest, number),
            ).fetchone()
            if previous is not None and previous[1:] != (edited, joined_notes):
                db.execute(
                    "INSERT INTO page_history (document_sha256,pdf_page,printed_label,edited_text,notes_text) "
                    "VALUES (?,?,?,?,?)",
                    (self.digest, number, *previous),
                )
            raw = "\n\n".join(item["text"] for item in results)
            label = previous[0] if previous else self.default_label(number)
            db.execute(
                "INSERT INTO pages (document_sha256,pdf_page,printed_label,raw_text,edited_text,notes_text,"
                "import_version,vision_text,vision_notes,vision_data,layout_data) VALUES (?,?,?,?,?,?,7,?,?,?,?) "
                "ON CONFLICT(document_sha256,pdf_page) DO UPDATE SET raw_text=excluded.raw_text,"
                "edited_text=excluded.edited_text,notes_text=excluded.notes_text,import_version=7,"
                "vision_text=excluded.vision_text,vision_notes=excluded.vision_notes,"
                "vision_data=excluded.vision_data,layout_data=excluded.layout_data,updated_at=CURRENT_TIMESTAMP",
                (self.digest, number, label, raw, edited, joined_notes, body, notes, json.dumps(lines, ensure_ascii=False), json.dumps(record, ensure_ascii=False)),
            )
        return edited

    def processed_pages(self) -> list[int]:
        with self.connect() as db:
            return [row[0] for row in db.execute(
                'SELECT pdf_page FROM pages WHERE document_sha256=? AND pdf_page BETWEEN ? AND ? ORDER BY pdf_page',
                (self.digest, self.first_page, self.last_page),
            )]

    def page_layout(self, number: int) -> dict:
        self.check_page(number)
        with self.connect() as db:
            row = db.execute('SELECT layout_data FROM pages WHERE document_sha256=? AND pdf_page=?',
                             (self.digest, number)).fetchone()
        return json.loads(row[0]) if row and row[0] else {'regions': [], 'warnings': []}

    def export_text(self) -> str:
        parts = []
        for number in self.processed_pages():
            data = self.page(number)
            label = data["printed_label"]
            notes = f"\n[注释]\n{data['notes_text']}" if data["notes_text"].strip() else ""
            parts.append(f"[PDF {number} | 印刷页 {label}]\n{data['edited_text']}{notes}")
        return "\n\n".join(parts) + "\n"

    def export_html(self) -> str:
        def paragraphs(text: str) -> str:
            return ''.join(f'<p>{html.escape(block)}</p>' for block in re.split(r'\n\s*\n', text) if block.strip())

        sections = []
        for number in self.processed_pages():
            data = self.page(number)
            notes = (
                f"<h3>注释</h3>{paragraphs(data['notes_text'])}"
                if data["notes_text"].strip() else ""
            )
            sections.append(
                f"<article><div>{paragraphs(data['edited_text'])}{notes}</div>"
                f"<aside>印刷页 {html.escape(data['printed_label'])}<br><small>PDF {number}</small></aside></article>"
            )
        title = html.escape(self.pdf.name)
        return (
            '<!doctype html><html lang="zh"><meta charset="utf-8">'
            f"<title>{title}</title><style>"
            "body{max-width:1100px;margin:30px auto;font:18px/1.6 Georgia,serif;color:#222}"
            "article{display:grid;grid-template-columns:1fr 150px;gap:30px;border-bottom:1px solid #bbb;padding:24px 0}"
            "article p{white-space:pre-wrap;margin:0 0 1em}article h3{font:600 16px system-ui;margin:28px 0 8px}"
            "article aside{text-align:right;font:16px system-ui;color:#555}small{color:#777}"
            "@media print{article{break-inside:avoid}}"
            "</style><h1>" + title + "</h1>" + "".join(sections) + "</html>"
        )





def page_html(workspace: Workspace, number: int, prefix: str = "") -> str:
    data = workspace.page(number)
    layout = workspace.page_layout(number)
    labels = {'body': '正文', 'title': '标题', 'header': '页眉或页码', 'footnote': '页底注释',
              'marginal_note': '侧注', 'annotation': '批注', 'unknown': '待确认区域'}
    region_labels = []
    for region in layout['regions']:
        label = labels.get(region['kind'], '待确认区域')
        if region.get('side'):
            label += '（左侧）' if region['side'] == 'left' else '（右侧）'
        region_labels.append(f'<li>{html.escape(label)}</li>')
    layout_details = '<details><summary>页面区域</summary><ol>' + ''.join(region_labels) + '</ol>'
    if any(region.get('review') for region in layout['regions']):
        layout_details += '<p><small>区域划分及侧注对应的正文位置需要核对。</small></p>'
    layout_details += ''.join(f'<p>{html.escape(warning)}</p>' for warning in layout.get('warnings', [])) + '</details>'
    title = html.escape(workspace.pdf.name)
    label = html.escape(data["printed_label"])
    edited = html.escape(data["edited_text"])
    notes = html.escape(data["notes_text"])
    previous = max(number - 1, workspace.first_page)
    following = min(number + 1, workspace.last_page)
    processed = set(workspace.processed_pages())
    earlier = workspace.page(previous)["edited_text"][-110:] if previous != number and previous in processed else ""
    later = workspace.page(following)["edited_text"][:110] if following != number and following in processed else ""
    recognition_message = '<p>此页尚未识别出文字，可查看扫描页或重新识别。</p>' if not data['edited_text'].strip() and not data['notes_text'].strip() else ''
    engine_options = ''.join(
        f'<option value="{engine}"' + (' selected' if engine == layout.get('ocr_engine', default_engine()) else '')
        + f'>{name}</option>' for engine, name in
        ([('vision', 'Apple Vision')] if sys.platform == 'darwin' else []) + ([('tesseract', 'Tesseract（法语）')] if tesseract_available() else []))
    return f"""<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF {number} · 历史文献 OCR</title><link rel="stylesheet" href="/static/app.css">
<header class="topbar"><a class="brand" href="/library"><span class="brand-mark" aria-hidden="true">❧</span>历史文献 OCR</a><nav><a href="/library">文献库</a><a href="{prefix}/page/{previous}">← 上一页</a><a href="{prefix}/page/{following}">下一页 →</a><details class="export-menu"><summary>导出 ↗</summary><div class="export-links"><a href="{prefix}/export.txt">已识别文本</a><a href="{prefix}/export.html">带页码的文本</a></div></details></nav></header>
<div class="workspace-heading"><p class="document-name" title="{title}">{title}</p><span class="page-badge">PDF {number} / {workspace.total_pages}</span></div>
<main class="workspace"><section class="panel scan-panel"><div class="panel-heading"><h2>扫描原页</h2><span class="eyebrow">Original</span></div><div class="scan-surface"><img src="{prefix}/image/{number}" alt="PDF 第 {number} 页扫描图像"></div></section>
<section class="panel editor-panel"><div class="panel-heading"><h2>文字校订</h2><span class="eyebrow">Transcription</span></div>{recognition_message}<form id="editor" method="post" action="{prefix}/save/{number}">
<input type="hidden" name="token" value="{workspace.token}">
<div class="text-fields"><div class="field-heading"><h2>正文</h2><button type="button" data-copy="edited_text">复制正文</button></div>
<textarea name="edited_text" aria-label="校订文本" spellcheck="false">{edited}</textarea>
<div class="field-heading"><h2>注释</h2><button type="button" data-copy="notes_text">复制注释</button></div><textarea class="notes" name="notes_text" aria-label="注释" spellcheck="false">{notes}</textarea></div>
<p id="copy-status" role="status" aria-live="polite"></p>
<div class="editor-actions"><label>识别方式 <select name="ocr_engine">{engine_options}</select></label><button type="submit">暂存本页</button><button class="primary" type="submit" formaction="{prefix}/recognize/{number}">重新识别本页</button></div></form></section>
<aside class="panel metadata"><h2>页面对应</h2><div><strong>PDF 页序</strong>{number} / {workspace.total_pages}
<form action="{prefix}/jump" method="get"><label>跳转到 PDF 页序 <input name="page" type="number" min="{workspace.first_page}" max="{workspace.last_page}" value="{number}" required></label><button>跳转</button></form></div>
<div><strong>书上印刷页码</strong><input form="editor" name="printed_label" value="{label}" aria-label="书上印刷页码"></div>
<div><strong>文献</strong><small>{title}</small></div>
{layout_details}
<div><strong>上一页结尾</strong><small>{html.escape(earlier) or '尚未识别'}</small></div>
<div><strong>下一页开头</strong><small>{html.escape(later) or '尚未识别'}</small></div>
<p><small>跨页文字和注释的阅读顺序请按扫描页核对。</small></p></aside></main>
<script>
document.querySelectorAll('[data-copy]').forEach(button=>button.addEventListener('click',async()=>{{
 const field=document.querySelector('textarea[name="'+button.dataset.copy+'"]');
 const status=document.getElementById('copy-status');
 try{{await navigator.clipboard.writeText(field.value);status.textContent='已复制';}}
 catch(error){{field.focus();field.select();status.textContent='文字已选中，请按 Command+C 复制。';}}
}}));
</script></html>"""


def make_handler(workspace: Workspace | None = None) -> type[BaseHTTPRequestHandler]:
    initial = workspace
    registry: dict[str, Workspace] = {}
    registry_lock = RLock()
    operation_lock = RLock()
    upload_token = secrets.token_urlsafe(32)
    documents = DATA / 'documents'
    documents.mkdir(parents=True, exist_ok=True)

    def document(digest: str) -> Workspace:
        with registry_lock:
            if digest not in registry:
                folder = documents / digest
                metadata = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
                pdf = folder / metadata['filename']
                registry[digest] = Workspace(pdf, 1, None, None, 1)
            return registry[digest]

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(30)

        def library_html(self) -> str:
            items = []
            for metadata_path in sorted(documents.glob('*/metadata.json')):
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
                digest = metadata_path.parent.name
                items.append(f'<li><a href="/documents/{digest}/page/1">'
                             f'{html.escape(metadata["filename"])}</a> · {metadata["pages"]} 页</li>')
            if initial:
                items.insert(0, f'<li><a href="/page/{initial.first_page}">{html.escape(initial.pdf.name)}</a> · 当前文献</li>')
            template = '''<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>上传 PDF · 历史文献 OCR</title>
<link rel="stylesheet" href="/static/app.css">
<header class="topbar"><a class="brand" href="/library"><span class="brand-mark" aria-hidden="true">❧</span>历史文献 OCR</a><span class="eyebrow">A space for reading</span></header>
<main class="library"><div class="welcome"><span class="eyebrow">Read · Transcribe · Discover</span><h1>让文献，重新可读。</h1><p>从一页原文开始，识别、校订，摘录所需。</p></div>
<section class="upload-card"><h2>打开一份文献</h2><p>选择本地 PDF，开始逐页识别。</p>
<form id="upload"><label class="upload-zone"><span>上传本地 PDF</span><input id="file" type="file" accept="application/pdf,.pdf" required aria-label="选择 PDF"></label>
<div class="upload-footer"><small>文献在本机处理 · 退出程序后清理</small><button class="primary" id="submit">上传并打开 ↗</button></div></form><progress id="progress" max="100" value="0" hidden aria-label="上传进度"></progress>
<p id="status" role="status" aria-live="polite"></p></section><section class="library-list"><div class="list-heading"><h2>本次文献</h2><button id="clear" type="button">清理本次缓存</button></div>DOCUMENT_ITEMS</section><p class="library-footnote">识别后的文字可直接复制，也可在校订页导出。</p></main>
<script>
document.getElementById('clear').addEventListener('click',async()=>{
 if(!confirm('清除本次上传、页面图像和识别文字？'))return;
 const response=await fetch('/clear',{method:'POST',headers:{'X-Upload-Token':'UPLOAD_TOKEN'}});
 if(response.ok)window.location.assign('/library');
 else document.getElementById('status').textContent='清理未完成，请刷新页面重试。';
});
document.getElementById('upload').addEventListener('submit',event=>{
 event.preventDefault(); const file=document.getElementById('file').files[0]; if(!file)return;
 const button=document.getElementById('submit'),status=document.getElementById('status'),progress=document.getElementById('progress');
 button.disabled=true;progress.hidden=false;progress.value=0;status.textContent='正在上传到本机…';
 const xhr=new XMLHttpRequest();xhr.open('POST','/upload');
 xhr.setRequestHeader('Content-Type','application/pdf');xhr.setRequestHeader('X-Upload-Token','UPLOAD_TOKEN');
 xhr.setRequestHeader('X-File-Name',encodeURIComponent(file.name));
 xhr.upload.onprogress=e=>{if(e.lengthComputable)progress.value=100*e.loaded/e.total;};
 xhr.upload.onload=()=>{status.textContent='正在读取文献页数…';};
 xhr.onload=()=>{button.disabled=false;if(xhr.status===201){const result=JSON.parse(xhr.responseText);
 status.textContent='上传完成，正在打开页面并识别文字…';window.location.assign(result.url);
 }else{status.textContent=xhr.responseText||'上传失败，请重试。';}};
 xhr.onerror=()=>{button.disabled=false;status.textContent='连接中断，请确认本机程序正在运行，再重新上传。';};
 xhr.send(file);
});</script></html>'''
            return template.replace('DOCUMENT_ITEMS', '<ul>' + ''.join(items) + '</ul>' if items else '<div class="empty-library">文献将在这里等待您的继续阅读。</div>').replace('UPLOAD_TOKEN', upload_token)

        def upload_pdf(self) -> None:
            if self.headers.get('X-Upload-Token') != upload_token:
                self.close_connection = True
                self.respond(403, '请从上传页面选择文件。'.encode(), 'text/plain; charset=utf-8')
                return
            staging = documents / f'{secrets.token_hex(16)}.part'
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0:
                    raise ValueError('请选择非空的 PDF 文件。')
                name = unquote(self.headers.get('X-File-Name', 'document.pdf')).replace('\\', '/')
                name = Path(name).name
                name = ''.join(char for char in name if char.isprintable())
                if not name.lower().endswith('.pdf'):
                    raise ValueError('请选择 PDF 文件。')
                name = name[:-4][:70] + '.pdf'
                with staging.open('xb') as stream:
                    remaining = length
                    while remaining:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('文件上传未完成，请重新上传。')
                        stream.write(chunk)
                        remaining -= len(chunk)
                imported = Workspace(staging, 1, None, None, 1)
                with registry_lock:
                    folder = documents / imported.digest
                    folder.mkdir(exist_ok=True)
                    metadata_path = folder / 'metadata.json'
                    if not metadata_path.exists():
                        destination = folder / name
                        staging.replace(destination)
                        imported.pdf = destination.resolve()
                        metadata_path.write_text(json.dumps({'filename': name, 'pages': imported.total_pages}, ensure_ascii=False), encoding='utf-8')
                        registry[imported.digest] = imported
                payload = json.dumps({'url': f'/documents/{imported.digest}/page/1', 'pages': imported.total_pages}).encode()
                self.respond(201, payload, 'application/json; charset=utf-8')
            except (ValueError, OSError, subprocess.CalledProcessError) as error:
                self.close_connection = True
                message = '无法读取这份 PDF，请检查文件是否完整或需要密码。' if isinstance(error, subprocess.CalledProcessError) else str(error)
                self.respond(400, message.encode(), 'text/plain; charset=utf-8')
            finally:
                staging.unlink(missing_ok=True)

        def respond(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def resolve_document(self) -> tuple[Workspace | None, str, str]:
            path = urlparse(self.path).path
            match = re.match(r'^/documents/([0-9a-f]{64})(/.*)$', path)
            if match:
                return document(match[1]), match[2], f'/documents/{match[1]}'
            return initial, path, ''

        def do_GET(self) -> None:
            with operation_lock:
                self.get_request()

        def get_request(self) -> None:
            asset = urlparse(self.path).path
            assets = {'/static/app.css': ('app.css', 'text/css; charset=utf-8'),
                      '/static/fonts/Lora.woff2': ('fonts/Lora.woff2', 'font/woff2'),
                      '/static/fonts/WenKaiGB.woff2': ('fonts/WenKaiGB.woff2', 'font/woff2')}
            if asset in assets:
                filename, content_type = assets[asset]
                target = ROOT / 'static' / filename
                if target.is_file():
                    self.respond(200, target.read_bytes(), content_type)
                else:
                    self.respond(404, b'Not found', 'text/plain')
                return
            if urlparse(self.path).path in ('/library', '/') and (initial is None or self.path != '/'):
                self.respond(200, self.library_html().encode(), 'text/html; charset=utf-8')
                return
            try:
                workspace, path, prefix = self.resolve_document()
            except (OSError, ValueError, subprocess.CalledProcessError):
                self.respond(404, '找不到这份文献。'.encode(), 'text/plain; charset=utf-8')
                return
            if workspace is None:
                self.respond(404, b'Not found', 'text/plain')
                return
            if path == '/jump':
                try:
                    number = int(parse_qs(urlparse(self.path).query)['page'][0])
                    workspace.check_page(number)
                except (KeyError, ValueError):
                    self.respond(400, '页序超出文献范围。'.encode(), 'text/plain; charset=utf-8')
                    return
                self.send_response(303)
                self.send_header('Location', f'{prefix}/page/{number}')
                self.end_headers()
                return
            if path == "/":
                self.send_response(302)
                self.send_header("Location", f"{prefix}/page/{workspace.first_page}")
                self.end_headers()
                return
            if path == "/export.txt":
                content = workspace.export_text().encode("utf-8")
                self.respond(200, content, "text/plain; charset=utf-8")
                return
            if path == "/export.html":
                content = workspace.export_html().encode("utf-8")
                self.respond(200, content, "text/html; charset=utf-8")
                return
            match = re.fullmatch(r"/(page|image)/(\d+)", path)
            if match:
                try:
                    number = int(match.group(2))
                    if match.group(1) == "image":
                        self.respond(200, workspace.image(number), "image/png")
                    else:
                        self.respond(200, page_html(workspace, number, prefix).encode("utf-8"), "text/html; charset=utf-8")
                except (ValueError, subprocess.CalledProcessError) as error:
                    self.respond(400, str(error).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self.respond(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            with operation_lock:
                self.post_request()

        def post_request(self) -> None:
            nonlocal initial, upload_token
            if urlparse(self.path).path == '/clear':
                if self.headers.get('X-Upload-Token') != upload_token:
                    self.respond(403, b'Invalid session', 'text/plain')
                    return
                with registry_lock:
                    registry.clear()
                    initial = None
                    for item in DATA.iterdir():
                        if item.name == '.lock':
                            continue
                        if item.is_dir() and not item.is_symlink():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    documents.mkdir(exist_ok=True)
                    upload_token = secrets.token_urlsafe(32)
                self.respond(200, b'{}', 'application/json')
                return
            if urlparse(self.path).path == '/upload':
                self.upload_pdf()
                return
            try:
                workspace, path, prefix = self.resolve_document()
            except (OSError, ValueError, subprocess.CalledProcessError):
                self.respond(404, b'Not found', 'text/plain')
                return
            match = re.fullmatch(r"/(save|recognize)/(\d+)", path)
            if workspace is None:
                match = None
            if not match:
                self.respond(404, b"Not found", "text/plain; charset=utf-8")
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > 3_000_000:
                self.respond(413, b"Request too large", "text/plain; charset=utf-8")
                return
            fields = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
            if fields.get("token", [""])[0] != workspace.token:
                self.respond(403, b"Invalid form token", "text/plain; charset=utf-8")
                return
            action, page_string = match.groups()
            number = int(page_string)
            try:
                old = workspace.page(number)
                workspace.save(
                    number,
                    fields.get("printed_label", [old["printed_label"]])[0],
                    fields.get("edited_text", [old["edited_text"]])[0],
                    fields.get("notes_text", [old["notes_text"]])[0],
                )
                if action == "recognize":
                    workspace.recognize_image(number, fields.get('ocr_engine', [default_engine()])[0])
            except (ValueError, subprocess.SubprocessError, OSError) as error:
                self.respond(400, str(error).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self.send_response(303)
            self.send_header("Location", f"{prefix}/page/{number}")
            self.end_headers()

    return Handler


def main() -> None:
    global DATA
    parser = argparse.ArgumentParser(description="Open a local transcription workspace for a scanned PDF")
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--first-page", type=int, default=1)
    parser.add_argument("--last-page", type=int)
    parser.add_argument("--printed-start-pdf", type=int)
    parser.add_argument("--printed-start-page", type=int, default=1)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument('--layout-engine', choices=('vision', 'tesseract'), default=layout_engine())
    args = parser.parse_args()
    os.environ['OCR_LAYOUT_ENGINE'] = args.layout_engine
    if args.layout_engine == 'vision' and sys.platform != 'darwin':
        parser.error('Apple Vision 需要 macOS，请使用 --layout-engine tesseract。')
    if (args.layout_engine == 'tesseract' or default_engine() == 'tesseract') and not tesseract_available():
        parser.error('Tesseract 尚未安装，请运行安装脚本。')
    for tool in (('swiftc',) if args.layout_engine == 'vision' and not os.environ.get('OCR_VISION_BINARY') else ()):
        try:
            executable(tool)
        except FileNotFoundError as error:
            parser.error(str(error))
    def request_exit(signum, frame):
        raise KeyboardInterrupt

    exit_signals = [getattr(signal, name) for name in ('SIGINT', 'SIGTERM', 'SIGHUP') if hasattr(signal, name)]
    for event in exit_signals:
        signal.signal(event, request_exit)
    with SessionStorage(ROOT / '.cache' / 'sessions') as session:
        DATA = session.path
        workspace = Workspace(
            args.pdf, args.first_page, args.last_page,
            args.printed_start_pdf, args.printed_start_page,
        ) if args.pdf else None
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(workspace))
        server.daemon_threads = False
        print(f"Open http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            for event in exit_signals:
                signal.signal(event, signal.SIG_IGN)
            server.server_close()


if __name__ == "__main__":
    main()
