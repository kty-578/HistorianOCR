"""Image-only PDF access using PDFium on macOS and Windows."""

from pathlib import Path
from threading import RLock
import pypdfium2 as pdfium

PDF_LOCK = RLock()


def page_count(path: Path) -> int:
    with PDF_LOCK:
        try:
            document = pdfium.PdfDocument(path)
        except pdfium.PdfiumError as error:
            raise ValueError('无法读取 PDF，请检查文件是否完整或需要密码。') from error
        try:
            return len(document)
        finally:
            document.close()


def render_page(path: Path, number: int, target: Path, dpi=400, max_size=None):
    try:
        _render_page(path, number, target, dpi, max_size)
    except pdfium.PdfiumError as error:
        raise ValueError('无法读取这一页的扫描图像。') from error


def _render_page(path, number, target, dpi, max_size):
    with PDF_LOCK:
        document = pdfium.PdfDocument(path)
        try:
            page = document[number-1]
            try:
                scale = max_size / max(page.get_size()) if max_size else dpi / 72
                bitmap = page.render(scale=scale)
                try:
                    image = bitmap.to_pil()
                    try:
                        image.save(target, format='PNG')
                    finally:
                        image.close()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()
