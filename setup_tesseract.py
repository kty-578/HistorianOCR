"""Install the pinned French model into the project model cache."""

import hashlib
from urllib.request import urlopen

from ocr_engines import MODEL, tesseract_paths

REVISION = '87416418657359cb625c412a48b6e1d6d41c29bd'
SHA256 = 'ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca'


def setup():
    node, module = tesseract_paths()
    if not node.is_file() or not (module / 'package.json').is_file():
        raise SystemExit('需要 Node.js 和 tesseract.js；通过 OCR_NODE、OCR_TESSERACT_JS 指定安装路径。')
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    if MODEL.is_file() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == SHA256:
        print('Tesseract 法语模型已就绪。')
        return
    target = MODEL.with_suffix('.download')
    try:
        url = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{REVISION}/fra.traineddata'
        with urlopen(url, timeout=60) as response, target.open('wb') as stream:
            while chunk := response.read(1024*1024):
                stream.write(chunk)
        if hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
            raise ValueError('法语模型校验失败。')
        target.replace(MODEL)
    finally:
        target.unlink(missing_ok=True)
    print('Tesseract 法语模型已就绪。')


if __name__ == '__main__':
    setup()
