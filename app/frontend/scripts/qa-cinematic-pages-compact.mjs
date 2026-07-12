import { runCinematicPagesQa } from './qa-cinematic-pages-core.mjs';

await runCinematicPagesQa({
  baseUrl: process.argv[2] || 'http://10.8.0.105:9120',
  outDir: process.argv[3] || 'tmp/cinematic-pages-qa-compact',
  mode: 'compact-render',
  enforcePerformance: false,
  viewport: { width: 1440, height: 900 },
  pageKeys: process.argv[4]?.split(',').filter(Boolean),
});
