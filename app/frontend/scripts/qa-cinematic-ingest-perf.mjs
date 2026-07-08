import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const url = process.argv[2] || 'http://10.8.0.105:9120/#/ingest';
const outDir = resolve(process.argv[3] || 'tmp/perf-qa');
const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const viewport = { width: 2560, height: 1440 };
const screenshotPath = resolve(outDir, 'cinematic-ingest-perf-2560x1440.png');
const reportPath = resolve(outDir, 'cinematic-ingest-perf-2560x1440.json');

mkdirSync(outDir, { recursive: true });

function runChrome(args, timeout = 45000) {
  const startedAt = performance.now();
  const result = spawnSync(chromePath, args, {
    encoding: 'utf8',
    timeout,
  });
  return {
    durationMs: Math.round(performance.now() - startedAt),
    exitCode: result.status,
    signal: result.signal,
    stdout: result.stdout || '',
    stderr: result.stderr || '',
  };
}

function healthUrlFromPage(pageUrl) {
  try {
    const parsed = new URL(pageUrl);
    return `${parsed.origin}/api/health`;
  } catch (_) {
    return '';
  }
}

async function fetchHealth(pageUrl) {
  const healthUrl = healthUrlFromPage(pageUrl);
  if (!healthUrl) return { ok: false, error: 'invalid url' };
  const startedAt = performance.now();
  try {
    const response = await fetch(healthUrl);
    const text = await response.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch (_) {
      // Keep raw body when endpoint returns non-JSON.
    }
    return {
      ok: response.ok,
      status: response.status,
      durationMs: Math.round(performance.now() - startedAt),
      url: healthUrl,
      body: json || text.slice(0, 500),
    };
  } catch (error) {
    return {
      ok: false,
      durationMs: Math.round(performance.now() - startedAt),
      url: healthUrl,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

const baseChromeArgs = [
  '--headless',
  '--disable-gpu',
  '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader',
  '--hide-scrollbars',
  `--window-size=${viewport.width},${viewport.height}`,
  '--virtual-time-budget=12000',
];

const health = await fetchHealth(url);
const screenshot = runChrome([
  ...baseChromeArgs,
  `--screenshot=${screenshotPath}`,
  url,
]);
const dom = runChrome([
  ...baseChromeArgs,
  '--dump-dom',
  url,
]);

const html = dom.stdout || '';
const stderr = `${screenshot.stderr}\n${dom.stderr}`.trim();
const keyMarkers = {
  shell: html.includes('cinematic-ingest-shell'),
  processingTrack: html.includes('处理轨道'),
  eventList: html.includes('ingest-index-list'),
  topicRail: html.includes('ingest-topic-orbit'),
  detailReader: html.includes('ingest-detail-reader'),
  detailTabs: html.includes('ingest-detail-tabs'),
  mediaBox: html.includes('laser-media-box'),
  loadingStuck: html.includes('加载中...'),
};
const chromeIssues = stderr
  .split('\n')
  .filter((line) => /ERROR|TypeError|ReferenceError|SyntaxError/i.test(line))
  .slice(0, 40);

const report = {
  url,
  viewport,
  capturedAt: new Date().toISOString(),
  health,
  timings: {
    screenshotMs: screenshot.durationMs,
    domDumpMs: dom.durationMs,
    totalChromeMs: screenshot.durationMs + dom.durationMs,
  },
  screenshot: {
    path: screenshotPath,
    exitCode: screenshot.exitCode,
    signal: screenshot.signal,
  },
  dom: {
    exitCode: dom.exitCode,
    signal: dom.signal,
    bytes: html.length,
    keyMarkers,
  },
  chromeIssues,
  pass: Boolean(
    health.ok &&
    screenshot.exitCode === 0 &&
    dom.exitCode === 0 &&
    keyMarkers.shell &&
    keyMarkers.detailReader &&
    keyMarkers.mediaBox &&
    !keyMarkers.loadingStuck
  ),
};

writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);

console.log(`perf_report=${reportPath}`);
console.log(`screenshot=${screenshotPath}`);
console.log(`pass=${report.pass}`);
console.log(`screenshot_ms=${report.timings.screenshotMs}`);
console.log(`dom_dump_ms=${report.timings.domDumpMs}`);

if (!report.pass) {
  process.exit(1);
}
