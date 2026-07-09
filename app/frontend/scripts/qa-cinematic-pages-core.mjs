import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const viewport = { width: 2560, height: 1440 };

const pages = [
  {
    key: 'today',
    path: '/#/',
    markers: ['cinematic-dashboard', '今日知几', 'cinematic-scene-canvas'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 7000,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 22000,
  },
  {
    key: 'ingest',
    path: '/#/ingest',
    markers: ['cinematic-ingest-shell', '处理轨道', 'ingest-detail-reader', 'laser-media-box'],
    maxScreenshotMs: 6500,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'system',
    path: '/#/system',
    markers: ['cinematic-ingest-shell', '系统中枢', 'system-detail-reader', 'system-core-box'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 14000,
  },
];

function pageUrl(baseUrl, path) {
  return new URL(path, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`).toString();
}

function runChrome(args, timeout = 60000) {
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

async function fetchHealth(baseUrl) {
  const startedAt = performance.now();
  try {
    const response = await fetch(new URL('/api/health', baseUrl).toString());
    const text = await response.text();
    return {
      ok: response.ok,
      status: response.status,
      durationMs: Math.round(performance.now() - startedAt),
      body: JSON.parse(text),
    };
  } catch (error) {
    return {
      ok: false,
      durationMs: Math.round(performance.now() - startedAt),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function chromeArgsForPage(page) {
  return [
    '--headless',
    '--disable-gpu',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--hide-scrollbars',
    `--window-size=${viewport.width},${viewport.height}`,
    `--virtual-time-budget=${page.virtualTimeBudgetMs}`,
  ];
}

export async function runCinematicPagesQa({
  baseUrl = 'http://10.8.0.105:9120',
  outDir = 'tmp/cinematic-pages-qa',
  mode = 'render',
  enforcePerformance = false,
} = {}) {
  const resolvedOutDir = resolve(outDir);
  mkdirSync(resolvedOutDir, { recursive: true });

  const health = await fetchHealth(baseUrl);
  const reports = [];

  for (const page of pages) {
    const url = pageUrl(baseUrl, page.path);
    const screenshotPath = resolve(resolvedOutDir, `${page.key}-2560x1440.png`);
    const pageChromeArgs = chromeArgsForPage(page);
    const screenshot = runChrome([...pageChromeArgs, `--screenshot=${screenshotPath}`, url]);
    const dom = runChrome([...pageChromeArgs, '--dump-dom', url]);
    const html = dom.stdout || '';
    const stderr = `${screenshot.stderr}\n${dom.stderr}`.trim();
    const markerStatus = Object.fromEntries(page.markers.map((marker) => [marker, html.includes(marker)]));
    const chromeIssues = stderr
      .split('\n')
      .filter((line) => /ERROR|TypeError|ReferenceError|SyntaxError/i.test(line))
      .slice(0, 30);
    const thresholds = {
      screenshotMs: screenshot.durationMs <= page.maxScreenshotMs,
      domDumpMs: dom.durationMs <= page.maxDomDumpMs,
      canvasCount: (html.match(/<canvas\b/g) || []).length === page.expectedCanvasCount,
    };
    const renderPass = Boolean(
      screenshot.exitCode === 0 &&
      dom.exitCode === 0 &&
      Object.values(markerStatus).every(Boolean) &&
      thresholds.canvasCount &&
      !html.includes('加载中...')
    );

    reports.push({
      key: page.key,
      url,
      screenshotPath,
      screenshotMs: screenshot.durationMs,
      domDumpMs: dom.durationMs,
      domBytes: html.length,
      canvasCount: (html.match(/<canvas\b/g) || []).length,
      virtualTimeBudgetMs: page.virtualTimeBudgetMs,
      markerStatus,
      thresholds: {
        ...thresholds,
        maxScreenshotMs: page.maxScreenshotMs,
        maxDomDumpMs: page.maxDomDumpMs,
        expectedCanvasCount: page.expectedCanvasCount,
      },
      chromeIssues,
      pass: Boolean(renderPass && (!enforcePerformance || (thresholds.screenshotMs && thresholds.domDumpMs))),
    });
  }

  const report = {
    mode,
    baseUrl,
    viewport,
    capturedAt: new Date().toISOString(),
    health,
    pages: reports,
    pass: Boolean(health.ok && reports.every((item) => item.pass)),
  };

  const reportPath = resolve(resolvedOutDir, `cinematic-pages-2560x1440-${mode}.json`);
  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);

  console.log(`qa_report=${reportPath}`);
  console.log(`mode=${mode}`);
  for (const page of reports) {
    console.log(`${page.key}: pass=${page.pass} screenshot_ms=${page.screenshotMs} dom_ms=${page.domDumpMs} canvas=${page.canvasCount} virtual_time=${page.virtualTimeBudgetMs}`);
    console.log(`${page.key}_thresholds=${JSON.stringify(page.thresholds)}`);
    console.log(`${page.key}_screenshot=${page.screenshotPath}`);
  }
  console.log(`pass=${report.pass}`);

  if (!report.pass) process.exit(1);
  return report;
}
