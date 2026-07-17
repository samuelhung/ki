import { runCinematicPagesQa } from './qa-cinematic-pages-core.mjs';

const viewportArg = process.argv[5] || '2560x1440';
const [viewportWidth, viewportHeight] = viewportArg.split('x');

await runCinematicPagesQa({
  baseUrl: process.argv[2] || 'http://127.0.0.1:5188',
  outDir: process.argv[3] || 'tmp/cinematic-pages-qa-metal',
  mode: 'performance',
  enforcePerformance: false,
  enforceScreenshotPerformance: false,
  gpuMode: 'metal',
  pageKeys: process.argv[4]?.split(',').filter(Boolean) || ['today', 'ingest'],
  viewport: { width: Number(viewportWidth), height: Number(viewportHeight) },
});
