import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { inflateSync } from 'node:zlib';

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const defaultViewport = { width: 2560, height: 1440 };

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

function chromeArgsForPage(page, viewport) {
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

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function readPngVisualStats(filePath) {
  try {
    const buffer = readFileSync(filePath);
    if (buffer.toString('ascii', 1, 4) !== 'PNG') return { ok: false, error: 'not_png' };

    let offset = 8;
    let width = 0;
    let height = 0;
    let bitDepth = 0;
    let colorType = 0;
    const idatChunks = [];

    while (offset < buffer.length) {
      const length = buffer.readUInt32BE(offset);
      const type = buffer.toString('ascii', offset + 4, offset + 8);
      const dataStart = offset + 8;
      const dataEnd = dataStart + length;
      if (type === 'IHDR') {
        width = buffer.readUInt32BE(dataStart);
        height = buffer.readUInt32BE(dataStart + 4);
        bitDepth = buffer[dataStart + 8];
        colorType = buffer[dataStart + 9];
      } else if (type === 'IDAT') {
        idatChunks.push(buffer.subarray(dataStart, dataEnd));
      } else if (type === 'IEND') {
        break;
      }
      offset = dataEnd + 4;
    }

    const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : 0;
    if (!width || !height || bitDepth !== 8 || !channels) {
      return { ok: false, error: `unsupported_png_${width}x${height}_${bitDepth}_${colorType}` };
    }

    const bytesPerPixel = channels;
    const stride = width * bytesPerPixel;
    const inflated = inflateSync(Buffer.concat(idatChunks));
    const previous = Buffer.alloc(stride);
    const current = Buffer.alloc(stride);
    let inputOffset = 0;
    let samples = 0;
    let lumaTotal = 0;
    let brightSamples = 0;
    const sampleStepX = Math.max(1, Math.floor(width / 160));
    const sampleStepY = Math.max(1, Math.floor(height / 90));

    for (let y = 0; y < height; y += 1) {
      const filter = inflated[inputOffset];
      inputOffset += 1;
      inflated.copy(current, 0, inputOffset, inputOffset + stride);
      inputOffset += stride;

      for (let x = 0; x < stride; x += 1) {
        const left = x >= bytesPerPixel ? current[x - bytesPerPixel] : 0;
        const up = previous[x];
        const upLeft = x >= bytesPerPixel ? previous[x - bytesPerPixel] : 0;
        if (filter === 1) current[x] = (current[x] + left) & 255;
        else if (filter === 2) current[x] = (current[x] + up) & 255;
        else if (filter === 3) current[x] = (current[x] + Math.floor((left + up) / 2)) & 255;
        else if (filter === 4) current[x] = (current[x] + paeth(left, up, upLeft)) & 255;
      }

      if (y % sampleStepY === 0) {
        for (let x = 0; x < width; x += sampleStepX) {
          const index = x * bytesPerPixel;
          const luma = current[index] * 0.2126 + current[index + 1] * 0.7152 + current[index + 2] * 0.0722;
          lumaTotal += luma;
          samples += 1;
          if (luma > 18) brightSamples += 1;
        }
      }
      previous.set(current);
    }

    const averageLuma = samples ? lumaTotal / samples : 0;
    const brightRatio = samples ? brightSamples / samples : 0;
    return {
      ok: averageLuma >= 2.8 && brightRatio >= 0.002,
      averageLuma: Number(averageLuma.toFixed(2)),
      brightRatio: Number(brightRatio.toFixed(4)),
    };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

export async function runCinematicPagesQa({
  baseUrl = 'http://10.8.0.105:9120',
  outDir = 'tmp/cinematic-pages-qa',
  mode = 'render',
  enforcePerformance = false,
  enforceScreenshotPerformance = enforcePerformance,
  viewport = defaultViewport,
} = {}) {
  const resolvedOutDir = resolve(outDir);
  mkdirSync(resolvedOutDir, { recursive: true });

  const health = await fetchHealth(baseUrl);
  const reports = [];

  for (const page of pages) {
    const url = pageUrl(baseUrl, page.path);
    const viewportLabel = `${viewport.width}x${viewport.height}`;
    const screenshotPath = resolve(resolvedOutDir, `${page.key}-${viewportLabel}.png`);
    const pageChromeArgs = chromeArgsForPage(page, viewport);
    const screenshot = runChrome([...pageChromeArgs, `--screenshot=${screenshotPath}`, url]);
    const dom = runChrome([...pageChromeArgs, '--dump-dom', url]);
    const screenshotVisual = readPngVisualStats(screenshotPath);
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
      screenshotVisual: screenshotVisual.ok,
    };
    const renderPass = Boolean(
      screenshot.exitCode === 0 &&
      dom.exitCode === 0 &&
      Object.values(markerStatus).every(Boolean) &&
      thresholds.canvasCount &&
      thresholds.screenshotVisual &&
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
      screenshotVisual,
      chromeIssues,
      thresholdsEnforced: {
        screenshotMs: enforceScreenshotPerformance,
        domDumpMs: enforcePerformance,
      },
      pass: Boolean(renderPass && (!enforceScreenshotPerformance || thresholds.screenshotMs) && (!enforcePerformance || thresholds.domDumpMs)),
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

  const reportPath = resolve(resolvedOutDir, `cinematic-pages-${viewport.width}x${viewport.height}-${mode}.json`);
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
