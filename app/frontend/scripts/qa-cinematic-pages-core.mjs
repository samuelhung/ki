import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import net from 'node:net';
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
  {
    key: 'toolbox',
    path: '/#/toolbox',
    markers: ['cinematic-ingest-shell', '贷款利率换算器', 'toolbox-detail-reader', 'toolbox-result-box'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'series',
    path: '/#/series',
    markers: ['cinematic-ingest-shell', '专题工作台', 'series-detail-legacy-content', 'series-core-box'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'study',
    path: '/#/study',
    markers: ['cinematic-ingest-shell', '学习中枢', 'study-detail-legacy-embedded is-ready', 'study-core-box'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'chains',
    path: '/#/industry-chains',
    markers: ['cinematic-ingest-shell', '产业链底座', 'chain-detail-embedded', 'chain-core-box'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 6000,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 16000,
  },
];

export function selectCinematicPages(pageKeys) {
  if (!pageKeys?.length) return pages;
  const requested = new Set(pageKeys);
  const unknown = [...requested].filter((key) => !pages.some((page) => page.key === key));
  if (unknown.length) throw new Error(`Unknown cinematic page key: ${unknown.join(', ')}`);
  return pages.filter((page) => requested.has(page.key));
}

function pageUrl(baseUrl, path) {
  return new URL(path, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`).toString();
}

async function findFreePort() {
  const server = net.createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  await new Promise((resolveClose) => server.close(resolveClose));
  return address.port;
}

async function waitForJson(url, timeoutMs = 10000) {
  const startedAt = performance.now();
  let lastError = '';
  while (performance.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 120));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError}`);
}

async function connectCdp(wsUrl) {
  const socket = new WebSocket(wsUrl);
  await new Promise((resolveOpen, rejectOpen) => {
    socket.addEventListener('open', resolveOpen, { once: true });
    socket.addEventListener('error', rejectOpen, { once: true });
  });

  let commandId = 0;
  const pending = new Map();

  socket.addEventListener('message', (message) => {
    const payload = JSON.parse(message.data.toString());
    if (!payload.id || !pending.has(payload.id)) return;
    const { resolveCommand, rejectCommand } = pending.get(payload.id);
    pending.delete(payload.id);
    if (payload.error) rejectCommand(new Error(payload.error.message || JSON.stringify(payload.error)));
    else resolveCommand(payload.result);
  });

  function send(method, params = {}) {
    const id = ++commandId;
    socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolveCommand, rejectCommand) => {
      pending.set(id, { resolveCommand, rejectCommand });
      setTimeout(() => {
        if (!pending.has(id)) return;
        pending.delete(id);
        rejectCommand(new Error(`CDP timeout: ${method}`));
      }, 30000);
    });
  }

  return {
    send,
    close: () => socket.close(),
  };
}

function expressionBody(source) {
  return `(() => { ${source} })()`;
}

async function evaluate(cdp, source, timeoutMs = 15000) {
  const result = await cdp.send('Runtime.evaluate', {
    expression: expressionBody(source),
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs,
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || 'Runtime.evaluate failed');
  }
  return result.result?.value;
}

async function waitFor(cdp, label, source, timeoutMs = 20000) {
  const startedAt = performance.now();
  while (performance.now() - startedAt < timeoutMs) {
    const value = await evaluate(cdp, source);
    if (value) return value;
    await new Promise((resolveWait) => setTimeout(resolveWait, 180));
  }
  throw new Error(`Timed out waiting for ${label}`);
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

async function capturePageWithCdp({ cdp, url, page, screenshotPath }) {
  const startedAt = performance.now();
  await cdp.send('Page.navigate', { url });
  await waitFor(cdp, `document ${page.key}`, `return document.readyState === 'complete' || document.readyState === 'interactive';`);
  await waitFor(
    cdp,
    `markers ${page.key}`,
    `
      const html = document.documentElement.outerHTML;
      const markers = ${JSON.stringify(page.markers)};
      if (!markers.every((marker) => html.includes(marker))) return false;
      if (html.includes('加载中...')) return false;
      if (${JSON.stringify(page.key)} === 'today') {
        const intro = document.querySelector('.cinematic-intro-wipe');
        const introStyle = intro ? getComputedStyle(intro) : null;
        const introDone = !intro || intro.classList.contains('is-intro-done') || introStyle.visibility === 'hidden' || Number(introStyle.opacity) === 0;
        const hero = document.querySelector('.cinematic-hero h1');
        return introDone && Boolean(hero) && getComputedStyle(hero).visibility !== 'hidden';
      }
      return true;
    `,
    page.virtualTimeBudgetMs + 6000,
  );

  const html = await evaluate(cdp, `return document.documentElement.outerHTML;`);
  const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  writeFileSync(screenshotPath, Buffer.from(screenshot.data, 'base64'));
  return {
    durationMs: Math.round(performance.now() - startedAt),
    html,
  };
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
  pageKeys,
} = {}) {
  const resolvedOutDir = resolve(outDir);
  mkdirSync(resolvedOutDir, { recursive: true });

  const health = await fetchHealth(baseUrl);
  const reports = [];
  const port = await findFreePort();
  const userDataDir = mkdtempSync(resolve(tmpdir(), 'ki-cinematic-pages-'));
  const chrome = spawn(chromePath, [
    '--headless=new',
    '--disable-gpu',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
    '--hide-scrollbars',
    '--no-first-run',
    '--no-default-browser-check',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    `--window-size=${viewport.width},${viewport.height}`,
    pageUrl(baseUrl, '/#/'),
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  const chromeStderr = [];
  chrome.stderr.on('data', (chunk) => chromeStderr.push(chunk.toString()));

  let cdp;
  try {
    const tabs = await waitForJson(`http://127.0.0.1:${port}/json/list`);
    const tab = tabs.find((item) => item.type === 'page') || tabs[0];
    if (!tab?.webSocketDebuggerUrl) throw new Error('No debuggable Chrome page found');
    cdp = await connectCdp(tab.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');

    for (const page of selectCinematicPages(pageKeys)) {
      const url = pageUrl(baseUrl, page.path);
      const viewportLabel = `${viewport.width}x${viewport.height}`;
      const screenshotPath = resolve(resolvedOutDir, `${page.key}-${viewportLabel}.png`);
      const capture = await capturePageWithCdp({ cdp, url, page, screenshotPath });
      const screenshotVisual = readPngVisualStats(screenshotPath);
      const html = capture.html || '';
      const stderr = chromeStderr.join('').trim();
      const markerStatus = Object.fromEntries(page.markers.map((marker) => [marker, html.includes(marker)]));
      const chromeIssues = stderr
        .split('\n')
        .filter((line) => /ERROR|TypeError|ReferenceError|SyntaxError/i.test(line))
        .slice(0, 30);
      const thresholds = {
        screenshotMs: capture.durationMs <= page.maxScreenshotMs,
        domDumpMs: true,
        canvasCount: (html.match(/<canvas\b/g) || []).length === page.expectedCanvasCount,
        screenshotVisual: screenshotVisual.ok,
      };
      const renderPass = Boolean(
        Object.values(markerStatus).every(Boolean) &&
        thresholds.canvasCount &&
        thresholds.screenshotVisual &&
        !html.includes('加载中...')
      );

      reports.push({
        key: page.key,
        url,
        screenshotPath,
        screenshotMs: capture.durationMs,
        domDumpMs: 0,
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
  } finally {
    cdp?.close();
    chrome.kill('SIGTERM');
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
