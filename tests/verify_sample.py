"""Run image-based integration checks using the user's 1902 Tome 1 PDF."""

import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from session_storage import SessionStorage


def verify(pdf: Path) -> None:
    with SessionStorage(app.ROOT / '.cache' / 'verification-sessions') as session:
        app.DATA = session.path
        workspace = app.Workspace(pdf, 1, None, None, 1)
        assert workspace.total_pages == 836, 'This check requires the 836-page Tome 1 sample.'
        assert workspace.processed_pages() == []
        visited = []
        for number in (234, 255, 256, 257, 619):
            visited.append(number)
            page = workspace.page(number)
            layout = workspace.page_layout(number)
            regions = layout['regions']
            assert regions and len(layout['recognition']) == len(regions)
            assert all(region['box'][0] < region['box'][2] and region['box'][1] < region['box'][3] for region in regions)
            assert any(region['kind'] == 'footnote' for region in regions)
            notes = [region for region in regions if region['kind'] == 'marginal_note']
            if number == 234:
                assert not notes
                assert len([region for region in regions if region['kind'] == 'footnote']) == 2
                assert 'Voir principalement' in page['notes_text']
                assert 'Voir principalement' not in page['edited_text']
                assert page['edited_text'].endswith('sus-')
            elif number == 256:
                assert len(notes) == 2 and all(region['side'] == 'left' for region in notes)
                assert all(region['anchor'] and region['relation'] == 'vertical_proximity' for region in notes)
                assert 'appellacions' in page['edited_text']
                assert 'appellacions' not in page['notes_text']
                assert page['edited_text'].endswith('ne-')
            else:
                assert len(notes) == 1 and notes[0]['side'] == 'right'
            if number == 255:
                assert '22 mars' in page['edited_text']
                assert '\n\nDe par le Roy.' in page['edited_text']
                assert 'janvier' not in page['edited_text']
            if number == 619:
                footnotes = [region for region in regions if region['kind'] == 'footnote']
                assert len(footnotes) == 2
                assert footnotes[0]['box'][2] < footnotes[1]['box'][0]
                assert page['edited_text'].endswith('pour ce')
                for phrase in ('La plupart', 'Anc. lois', 'millésime', '105.'):
                    assert phrase not in page['edited_text']
                    assert phrase in page['notes_text'], phrase
                assert page['notes_text'].index('La plupart') < page['notes_text'].index('Anc. lois')
            assert '页面区域' in app.page_html(workspace, number)
            assert workspace.processed_pages() == sorted(visited)
            assert {int(path.name[:4]) for path in workspace.cache.glob('*.png')} == set(visited)
            workspace.save(number, page['printed_label'], page['edited_text'], page['notes_text'])
            assert workspace.page(number) == page
            assert page['edited_text'] in workspace.export_text()
            print(f'PASS {number}: on-demand page, layout, regional OCR, body/notes, save and export', flush=True)
        # The first pass must be assigned to regions without silently dropping detected words.
        for number in visited:
            with workspace.connect() as db:
                raw = json.loads(db.execute('SELECT vision_data FROM pages WHERE pdf_page=?', (number,)).fetchone()[0])
            layout = workspace.page_layout(number)
            assigned = {line['source'] for region in layout['regions'] for line in region['lines']}
            expected = {i for i,line in enumerate(raw) if line['text'].strip()}
            assert assigned == expected
        print('PASS: every preliminary text observation assigned to a region', flush=True)
    assert not session.path.exists()
    print('PASS: verification session cleaned; no preview server started', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', type=Path)
    verify(parser.parse_args().pdf)
