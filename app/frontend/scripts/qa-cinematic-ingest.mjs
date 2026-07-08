import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

const url = process.argv[2] || 'http://127.0.0.1:5173/#/ingest';
const outDir = resolve(process.argv[3] || 'tmp/visual-qa');
const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const screenshotPath = resolve(outDir, 'cinematic-ingest-2560x1440.png');
const reportPath = resolve(outDir, 'cinematic-ingest-2560x1440.json');

mkdirSync(outDir, { recursive: true });

const result = spawnSync(chromePath, [
  '--headless',
  '--disable-gpu',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--hide-scrollbars',
  '--window-size=2560,1440',
  '--virtual-time-budget=12000',
  `--screenshot=${screenshotPath}`,
  url,
], {
  encoding: 'utf8',
  timeout: 30000,
});

const report = {
  url,
  viewport: { width: 2560, height: 1440 },
  screenshot: screenshotPath,
  exitCode: result.status,
  signal: result.signal,
  stdout: result.stdout.trim(),
  stderr: result.stderr.trim(),
};

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);

if (result.status !== 0) {
  console.error(result.stderr || result.stdout);
  process.exit(result.status || 1);
}

console.log(`screenshot=${screenshotPath}`);
console.log(`report=${reportPath}`);
