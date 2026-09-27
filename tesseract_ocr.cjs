// One local worker per page; all region jobs reuse its initialized French model.
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const { createWorker } = require(input.module);
  const version = require(path.join(input.module, 'package.json')).version;
  const worker = await createWorker('fra', 1, {
    langPath: input.model_dir,
    cacheMethod: 'none',
    gzip: false,
  }, { load_system_dawg: '0', load_freq_dawg: '0' });
  const results = [];
  try {
    for (const job of input.jobs) {
      const start = performance.now();
      await worker.setParameters({ tessedit_pageseg_mode: String(job.psm), user_defined_dpi: '400' });
      const { data } = await worker.recognize(job.image, {}, { text: true, blocks: true });
      const coordinates = box => ({
        x: box.x0 / job.width, y: 1 - box.y1 / job.height,
        width: (box.x1 - box.x0) / job.width, height: (box.y1 - box.y0) / job.height,
      });
      const lines = [];
      for (const block of data.blocks || []) {
        for (const paragraph of block.paragraphs || []) {
          for (const line of paragraph.lines || []) {
            lines.push({ text: line.text.trim(), confidence: line.confidence / 100,
              ...coordinates(line.bbox),
              words: (line.words || []).map(word => ({ text: word.text,
                confidence: word.confidence / 100, ...coordinates(word.bbox) })),
            });
          }
        }
      }
      results.push({ region_id: job.region_id, engine: 'tesseract', wrapper_version: version,
        model: 'fra/tessdata_fast', psm: job.psm, lines,
        elapsed_seconds: (performance.now() - start) / 1000 });
    }
  } finally {
    await worker.terminate();
  }
  process.stdout.write(JSON.stringify(results));
}

main().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
