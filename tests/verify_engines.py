"""Exercise regional OCR and the engine selector with the original sample PDF."""

import argparse
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Thread
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from session_storage import SessionStorage
from setup_tesseract import setup


def verify(pdf):
    setup()
    with SessionStorage(app.ROOT / '.cache/engine-verification') as session:
        app.DATA = session.path
        workspace = app.Workspace(pdf, 1, None, None, 1)
        workspace.recognize_image(619, 'tesseract')
        page = workspace.page(619)
        layout = workspace.page_layout(619)
        assert layout['ocr_engine'] == 'tesseract'
        assert all(item['engine'] == 'tesseract' for item in layout['recognition'])
        assert {item['psm'] for item in layout['recognition']} == {4, 6, 7}
        assert page['edited_text'].endswith('pour ce')
        for phrase in ('La plupart', 'Anc. lois', '105.'):
            assert phrase in page['notes_text'] and phrase not in page['edited_text']
        assert page['notes_text'].index('La plupart') < page['notes_text'].index('Anc. lois')
        assert 'Mars 1516' in page['notes_text'] and 'Mars 1516' not in page['edited_text']
        assert workspace.processed_pages() == [619]
        assert {int(path.name[:4]) for path in workspace.cache.glob('*.png')} == {619}
        print('PASS: Tesseract regional modes, body, columns, margin and on-demand OCR', flush=True)

        server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(workspace))
        thread = Thread(target=server.serve_forever)
        thread.start()
        client = HTTPConnection('127.0.0.1', server.server_port, timeout=120)
        try:
            client.request('GET', '/page/619')
            response = client.getresponse()
            html = response.read().decode()
            assert response.status == 200
            assert '<option value="tesseract" selected>' in html
            for engine in ('vision', 'tesseract'):
                fields = {'token': workspace.token, 'ocr_engine': engine,
                          'printed_label': '365', 'edited_text': page['edited_text'],
                          'notes_text': page['notes_text']}
                client.request('POST', '/recognize/619', urlencode(fields),
                               {'Content-Type': 'application/x-www-form-urlencoded'})
                response = client.getresponse()
                response.read()
                assert response.status == 303
                assert workspace.page_layout(619)['ocr_engine'] == engine
            page = workspace.page(619)
            for route in ('/export.txt', '/export.html', '/image/619'):
                client.request('GET', route)
                response = client.getresponse()
                payload = response.read()
                assert response.status == 200 and payload
                if route == '/export.txt':
                    assert page['edited_text'] in payload.decode()
                    assert page['notes_text'] in payload.decode()
            print('PASS: HTTP engine selection, persistence, exports and page image', flush=True)
        finally:
            client.close()
            server.shutdown()
            thread.join()
            server.server_close()
    assert not session.path.exists()
    print('PASS: temporary verification server closed and session removed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', type=Path)
    verify(parser.parse_args().pdf)
