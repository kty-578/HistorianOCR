"""Run the Windows-compatible PDFium/Tesseract path on actual sample pages."""

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from session_storage import SessionStorage


def verify(pdf):
    os.environ['OCR_LAYOUT_ENGINE'] = 'tesseract'
    with SessionStorage(app.ROOT / '.cache/portable-verification') as session:
        app.DATA = session.path
        workspace = app.Workspace(pdf, 1, None, None, 1)
        assert workspace.total_pages == 836
        for number in (256, 619):
            workspace.recognize_image(number, 'tesseract')
            page = workspace.page(number)
            layout = workspace.page_layout(number)
            assert layout['layout_engine'] == layout['ocr_engine'] == 'tesseract'
            assert all(result['engine'] == 'tesseract' for result in layout['recognition'])
            margins = [r for r in layout['regions'] if r['kind'] == 'marginal_note']
            if number == 256:
                assert len(margins) == 2 and all(r['side'] == 'left' for r in margins)
                assert 'appellacions' in page['edited_text']
                assert 'appellacions' not in page['notes_text']
            else:
                assert len(margins) == 1 and margins[0]['side'] == 'right'
                notes = [r for r in layout['regions'] if r['kind'] == 'footnote']
                assert len(notes) == 2 and notes[0]['box'][2] < notes[1]['box'][0]
                for phrase in ('La plupart', 'Anc. lois'):
                    assert phrase in page['notes_text'] and phrase not in page['edited_text']
                assert page['edited_text'].endswith('pour ce')
            workspace.save(number, page['printed_label'], page['edited_text'], page['notes_text'])
            assert workspace.page(number) == page
            assert page['notes_text'] in workspace.export_text()
            assert workspace.image(number)
            print(f'PASS: portable page {number}, body, notes, save, export and image', flush=True)
        assert workspace.processed_pages() == [256, 619]
        assert {int(path.name[:4]) for path in workspace.cache.glob('*.png')} == {256, 619}
    assert not session.path.exists()
    print('PASS: portable session cleanup')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', type=Path)
    verify(parser.parse_args().pdf)
