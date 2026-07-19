import { spawn } from 'node:child_process';

import {
  findFreePort,
  runCinematicPagesQa,
  stopChildProcess,
} from './qa-cinematic-pages-core.mjs';

async function waitForPreview(url, timeoutMs = 15000) {
  const startedAt = performance.now();
  let lastError = '';
  while (performance.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 150));
  }
  throw new Error(`Timed out waiting for production preview ${url}: ${lastError}`);
}

const outDir = process.argv[2] || 'tmp/cinematic-pages-production-1440';
const viewportArg = process.argv[3] || '1440x900';
const [width, height] = viewportArg.split('x').map(Number);
const port = await findFreePort();
const baseUrl = `http://127.0.0.1:${port}`;
const preview = spawn('npm', [
  'run',
  'preview',
  '--',
  '--host',
  '127.0.0.1',
  '--port',
  String(port),
  '--strictPort',
], { stdio: ['ignore', 'pipe', 'pipe'] });

const previewOutput = [];
preview.stdout.on('data', (chunk) => previewOutput.push(chunk.toString()));
preview.stderr.on('data', (chunk) => previewOutput.push(chunk.toString()));

try {
  await waitForPreview(baseUrl);
  await runCinematicPagesQa({
    baseUrl,
    outDir,
    mode: 'performance',
    enforcePerformance: false,
    enforceScreenshotPerformance: false,
    gpuMode: 'metal',
    pageKeys: ['today', 'ingest', 'briefings'],
    viewport: { width, height },
    revisitFirstPage: true,
    warmRevisitCount: 3,
  });
} catch (error) {
  const output = previewOutput.join('').trim();
  if (output) console.error(output);
  throw error;
} finally {
  await stopChildProcess(preview);
}
