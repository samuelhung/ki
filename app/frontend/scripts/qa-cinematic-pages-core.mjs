import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import net from 'node:net';
import { inflateSync } from 'node:zlib';

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const defaultViewport = { width: 2560, height: 1440 };
const performanceSettleMs = 5000;

const pages = [
  {
    key: 'today',
    path: '/#/',
    markers: ['cinematic-dashboard', '今日知几', 'cinematic-scene-canvas'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 7000,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 22000,
    screenshotSettleMs: 1800,
  },
  {
    key: 'ingest',
    path: '/#/ingest',
    markers: ['ki-shell-legacy-ingest', 'ki-ingest-split-stage', 'ingest-detail-reader', 'dual-nav-action-menu'],
    maxScreenshotMs: 6500,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'briefings',
    path: '/#/briefings',
    markers: ['ki-shell-briefings', 'briefing-split-stage', 'briefing-history-pane', 'briefing-detail-pane'],
    readySelectors: ['.ki-shell-briefings', '.briefing-split-stage', '.briefing-history-pane', '.briefing-detail-pane'],
    readyState: 'briefings',
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'system',
    path: '/#/system',
    markers: ['ki-shell-system', 'ki-ingest-split-stage', 'system-detail-reader', 'system-function-list'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'toolbox',
    path: '/#/toolbox',
    markers: ['ki-shell-toolbox', 'toolbox-tool-list', 'toolbox-detail-reader', 'toolbox-primary-results'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 14000,
  },
  {
    key: 'series',
    path: '/#/series',
    markers: ['ki-shell-series', 'series-status-tabs', 'series-list', 'series-detail-legacy-content'],
    maxScreenshotMs: 8000,
    maxDomDumpMs: 5500,
    expectedCanvasCount: 1,
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
    markers: ['ki-shell-chains', 'chain-index-list', 'chain-detail-embedded', 'chain-list-summary'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 6000,
    expectedCanvasCount: 1,
    virtualTimeBudgetMs: 16000,
  },
  {
    key: 'brainstorm',
    path: '/#/brainstorm',
    markers: ['cinematic-ingest-shell', '脑暴问答', 'brainstorm-detail-embedded is-ready', 'brainstorm-core-box'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 6500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 16000,
  },
  {
    key: 'tasks',
    path: '/#/tasks',
    markers: ['cinematic-ingest-shell', '行动中枢', 'task-detail-reader', 'task-core-box'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 6500,
    expectedCanvasCount: 2,
    virtualTimeBudgetMs: 16000,
  },
  {
    key: 'library',
    path: '/#/events',
    markers: ['cinematic-ingest-shell', '万象资料', 'ingest-detail-reader', 'library-core-box'],
    maxScreenshotMs: 9000,
    maxDomDumpMs: 6500,
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

export function buildCinematicVisitSequence(pageKeys, revisitFirstPage = false, warmRevisitCount = 1) {
  const selected = selectCinematicPages(pageKeys);
  const visits = selected.map((page, index) => ({
    ...page,
    visit: index === 0 ? 'cold' : 'route',
  }));
  if (revisitFirstPage && selected[0]) {
    for (let index = 0; index < Math.max(1, warmRevisitCount); index += 1) {
      visits.push({ ...selected[0], visit: `warm-revisit-${index + 1}` });
      if (index < warmRevisitCount - 1 && selected[1]) {
        visits.push({ ...selected[1], visit: `route-repeat-${index + 1}` });
      }
    }
  }
  return visits;
}

export function summarizeNavigationResources(resources) {
  return resources.reduce((summary, resource) => {
    const transferSize = Number(resource.transferSize || 0);
    const encodedBodySize = Number(resource.encodedBodySize || 0);
    const decodedBodySize = Number(resource.decodedBodySize || 0);
    summary.resourceCount += 1;
    summary.transferBytes += transferSize;
    summary.encodedBytes += encodedBodySize;
    summary.decodedBytes += decodedBodySize;
    if (transferSize === 0 && decodedBodySize > 0) summary.cacheHitCount += 1;
    if (/\.(?:js|css)(?:$|\?)/.test(resource.name || '')) summary.jsCssTransferBytes += transferSize;
    return summary;
  }, {
    resourceCount: 0,
    cacheHitCount: 0,
    transferBytes: 0,
    encodedBytes: 0,
    decodedBytes: 0,
    jsCssTransferBytes: 0,
  });
}

export function summarizeDocumentNavigation(navigation, includeDocumentNavigation) {
  if (!includeDocumentNavigation) {
    return {
      navigationKind: 'spa-route',
      browserNavigationMs: null,
      domInteractiveMs: null,
      domContentLoadedMs: null,
      loadEventEndMs: null,
    };
  }
  return {
    navigationKind: 'document',
    browserNavigationMs: Number((navigation?.duration || 0).toFixed(2)),
    domInteractiveMs: Number((navigation?.domInteractive || 0).toFixed(2)),
    domContentLoadedMs: Number((navigation?.domContentLoaded || 0).toFixed(2)),
    loadEventEndMs: Number((navigation?.loadEventEnd || 0).toFixed(2)),
  };
}

export async function stopChildProcess(child, timeoutMs = 3000) {
  if (!child || child.exitCode !== null) return;
  const waitForExit = () => Promise.race([
    once(child, 'exit').then(() => true),
    new Promise((resolveWait) => setTimeout(() => resolveWait(false), timeoutMs)),
  ]);

  child.kill('SIGTERM');
  if (await waitForExit()) return;
  if (child.exitCode === null) child.kill('SIGKILL');
  await waitForExit();
}

function pageUrl(baseUrl, path) {
  return new URL(path, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`).toString();
}

export async function findFreePort() {
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
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || 'Runtime.evaluate failed');
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

async function collectRuntimePerformance(cdp, sampleMs = 3000, exercise) {
  const beforeResult = await cdp.send('Performance.getMetrics');
  const beforeMetrics = Object.fromEntries((beforeResult.metrics || []).map((metric) => [metric.name, metric.value]));
  const runtimePromise = evaluate(cdp, `
    return new Promise((resolve) => {
      const frameDurations = [];
      const longTasks = [];
      let previousFrame = null;
      let observer = null;
      try {
        observer = new PerformanceObserver((list) => {
          list.getEntries().forEach((entry) => longTasks.push(entry.duration));
        });
        observer.observe({ entryTypes: ['longtask'] });
      } catch (_) {
        observer = null;
      }

      const startedAt = performance.now();
      const finish = () => {
        observer?.disconnect();
        const sortedFrames = [...frameDurations].sort((a, b) => a - b);
        const averageFrameDurationMs = frameDurations.length
          ? frameDurations.reduce((total, value) => total + value, 0) / frameDurations.length
          : 0;
        const p95Index = sortedFrames.length ? Math.min(sortedFrames.length - 1, Math.floor(sortedFrames.length * .95)) : 0;
        const resources = performance.getEntriesByType('resource');
        const routeAssets = resources.filter((entry) => /\\.(?:js|css)(?:$|\\?)/.test(entry.name));
        const canvas = document.querySelector('.cinematic-scene-canvas');
        resolve({
          sampleMs: ${sampleMs},
          viewportWidth: window.innerWidth,
          viewportHeight: window.innerHeight,
          frameCount: frameDurations.length,
          averageFps: averageFrameDurationMs ? Number((1000 / averageFrameDurationMs).toFixed(2)) : 0,
          averageFrameDurationMs: Number(averageFrameDurationMs.toFixed(2)),
          frameDurationP95Ms: Number((sortedFrames[p95Index] || 0).toFixed(2)),
          longestFrameMs: Number((sortedFrames.at(-1) || 0).toFixed(2)),
          longTaskCount: longTasks.length,
          longTaskTotalMs: Number(longTasks.reduce((total, value) => total + value, 0).toFixed(2)),
          longestLongTaskMs: Number(Math.max(0, ...longTasks).toFixed(2)),
          resourceTransferBytes: routeAssets.reduce((total, entry) => total + (entry.transferSize || 0), 0),
          resourceEncodedBytes: routeAssets.reduce((total, entry) => total + (entry.encodedBodySize || 0), 0),
          routeAssetCount: routeAssets.length,
          rendererCalls: Number(canvas?.dataset.renderCalls || 0),
          rendererFps: Number(canvas?.dataset.renderFps || 0),
          rendererTriangles: Number(canvas?.dataset.renderTriangles || 0),
          rendererLines: Number(canvas?.dataset.renderLines || 0),
          rendererPoints: Number(canvas?.dataset.renderPoints || 0),
          rendererQualityScale: Number(canvas?.dataset.qualityScale || 1),
          rendererPixelRatio: Number(canvas?.dataset.pixelRatio || 0),
          rendererShaderOctaves: canvas?.dataset.shaderOctaves || '',
          gpuRenderer: canvas?.dataset.gpuRenderer || '',
          gpuVendor: canvas?.dataset.gpuVendor || '',
        });
      };
      const sampleFrame = (now) => {
        if (previousFrame !== null) frameDurations.push(now - previousFrame);
        previousFrame = now;
        if (now - startedAt >= ${sampleMs}) finish();
        else requestAnimationFrame(sampleFrame);
      };
      requestAnimationFrame(sampleFrame);
    });
  `, sampleMs + 5000);
  if (exercise) await exercise(cdp, sampleMs);
  const runtime = await runtimePromise;
  const cdpResult = await cdp.send('Performance.getMetrics');
  const cdpMetrics = Object.fromEntries((cdpResult.metrics || []).map((metric) => [metric.name, metric.value]));
  return {
    ...runtime,
    jsHeapUsedBytes: Math.round(cdpMetrics.JSHeapUsedSize || 0),
    jsHeapTotalBytes: Math.round(cdpMetrics.JSHeapTotalSize || 0),
    taskDurationMs: Number((((cdpMetrics.TaskDuration || 0) - (beforeMetrics.TaskDuration || 0)) * 1000).toFixed(2)),
    scriptDurationMs: Number((((cdpMetrics.ScriptDuration || 0) - (beforeMetrics.ScriptDuration || 0)) * 1000).toFixed(2)),
    layoutDurationMs: Number((((cdpMetrics.LayoutDuration || 0) - (beforeMetrics.LayoutDuration || 0)) * 1000).toFixed(2)),
  };
}

const wait = (durationMs) => new Promise((resolveWait) => setTimeout(resolveWait, durationMs));

async function sweepPointer(cdp, sampleMs, viewport) {
  const steps = 24;
  for (let index = 0; index < steps; index += 1) {
    const progress = index / Math.max(1, steps - 1);
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved',
      x: Math.round(viewport.width * (0.18 + progress * 0.64)),
      y: Math.round(viewport.height * (0.32 + Math.sin(progress * Math.PI * 2) * 0.18)),
    });
    await wait(sampleMs / steps);
  }
}

async function scrollWorkspace(cdp, sampleMs, viewport) {
  const steps = 18;
  for (let index = 0; index < steps; index += 1) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x: Math.round(viewport.width * 0.3),
      y: Math.round(viewport.height * 0.54),
      deltaX: 0,
      deltaY: index < steps / 2 ? 110 : -110,
    });
    await wait(sampleMs / steps);
  }
}

async function switchSeries(cdp, sampleMs) {
  await evaluate(cdp, `
    const buttons = [...document.querySelectorAll('.series-list-row')];
    buttons[1]?.click();
    return buttons.length;
  `);
  await wait(sampleMs);
}

async function scrollSeriesDetail(cdp, sampleMs, viewport) {
  const steps = 18;
  for (let index = 0; index < steps; index += 1) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x: Math.round(viewport.width * 0.68),
      y: Math.round(viewport.height * 0.54),
      deltaX: 0,
      deltaY: index < steps / 2 ? 120 : -120,
    });
    await wait(sampleMs / steps);
  }
}

async function openSeriesKnowledge(cdp, sampleMs) {
  await evaluate(cdp, `
    const button = [...document.querySelectorAll('.series-detail-legacy-content button')]
      .find((item) => item.textContent?.trim() === '知识网络');
    button?.click();
    return Boolean(button);
  `);
  await wait(sampleMs);
}

async function openQueueModal(cdp, sampleMs) {
  await evaluate(cdp, `
    const button = document.querySelector('button[aria-label="处理队列"]');
    button?.click();
    return Boolean(button);
  `);
  await wait(sampleMs);
}

async function closeInteractionModal(cdp) {
  await evaluate(cdp, `
    document.querySelector('button[aria-label="关闭"]')?.click();
    return true;
  `);
}

async function switchSystemControl(cdp, sampleMs) {
  const groupFound = await evaluate(cdp, `
    const groupButton = [...document.querySelectorAll('.system-group-tabs button')]
      .find((item) => item.textContent?.includes('控制'));
    groupButton?.click();
    return Boolean(groupButton);
  `);
  if (!groupFound) throw new Error('System performance interaction failed: control group not found');
  await wait(Math.min(240, sampleMs / 4));
  const moduleFound = await evaluate(cdp, `
    const moduleButton = [...document.querySelectorAll('.system-function-row')]
      .find((item) => item.textContent?.includes('内容采集'));
    moduleButton?.click();
    return Boolean(moduleButton);
  `);
  if (!moduleFound) throw new Error('System performance interaction failed: ingest module not found');
  await waitFor(cdp, 'system ingest module selection', `
    return document.querySelector('.system-detail-header h2')?.textContent?.trim() === '内容采集';
  `, Math.max(1000, sampleMs));
  await wait(Math.max(0, sampleMs - Math.min(240, sampleMs / 4)));
}

async function scrollSystemDetail(cdp, sampleMs, viewport) {
  const steps = 18;
  const initialScrollTop = await evaluate(cdp, `
    return document.querySelector('.system-detail-body')?.scrollTop ?? null;
  `);
  if (initialScrollTop === null) throw new Error('System performance interaction failed: detail scroller not found');
  for (let index = 0; index < steps; index += 1) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x: Math.round(viewport.width * 0.76),
      y: Math.round(viewport.height * 0.54),
      deltaX: 0,
      deltaY: index < steps / 2 ? 110 : -110,
    });
    await wait(sampleMs / steps);
    if (index === steps / 2 - 1) {
      const scrolledTop = await evaluate(cdp, `
        return document.querySelector('.system-detail-body')?.scrollTop ?? null;
      `);
      if (scrolledTop === null || scrolledTop <= initialScrollTop) {
        throw new Error('System performance interaction failed: detail scroller did not move');
      }
    }
  }
}

async function switchIndustryChain(cdp, sampleMs) {
  const targetName = await evaluate(cdp, `
    const buttons = [...document.querySelectorAll('.chain-list-row')];
    const target = buttons[1];
    target?.click();
    return target?.querySelector('strong')?.textContent?.trim() || '';
  `);
  if (!targetName) throw new Error('Chain performance interaction failed: second chain not found');
  await waitFor(cdp, 'industry chain selection', `
    const header = document.querySelector('.chain-detail-embedded-shell > div:first-child');
    return Boolean(header?.textContent?.includes(${JSON.stringify(targetName)}));
  `, Math.max(1000, sampleMs));
}

async function expandIndustryChainNode(cdp, sampleMs) {
  const nodeFound = await evaluate(cdp, `
    const flow = document.querySelector('.chain-detail-embedded-shell > div:nth-child(2) > div:first-child');
    const button = [...(flow?.querySelectorAll('button') || [])]
      .find((item) => item.textContent?.trim());
    button?.click();
    return Boolean(button);
  `);
  if (!nodeFound) throw new Error('Chain performance interaction failed: expandable node not found');
  await waitFor(cdp, 'industry chain node expansion', `
    return Boolean(document.querySelector('.chain-detail-embedded-shell .mx-3.mb-3'));
  `, Math.max(1000, sampleMs));
}

async function scrollIndustryChainDetail(cdp, sampleMs, viewport) {
  const selector = '.chain-detail-embedded-shell > div:nth-child(2) > div:first-child';
  const initialScrollTop = await evaluate(cdp, `
    return document.querySelector(${JSON.stringify(selector)})?.scrollTop ?? null;
  `);
  if (initialScrollTop === null) throw new Error('Chain performance interaction failed: detail scroller not found');
  const steps = 18;
  for (let index = 0; index < steps; index += 1) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseWheel',
      x: Math.round(viewport.width * 0.72),
      y: Math.round(viewport.height * 0.36),
      deltaX: 0,
      deltaY: index < steps / 2 ? 110 : -110,
    });
    await wait(sampleMs / steps);
    if (index === steps / 2 - 1) {
      const scrolledTop = await evaluate(cdp, `
        return document.querySelector(${JSON.stringify(selector)})?.scrollTop ?? null;
      `);
      if (scrolledTop === null || scrolledTop <= initialScrollTop) {
        throw new Error('Chain performance interaction failed: detail scroller did not move');
      }
    }
  }
}

async function clickIndustryChainReport(cdp, sampleMs) {
  const qaReport = 'KI QA 产业链报告已生成';
  const reportFound = await evaluate(cdp, `
    globalThis.__chainQaOriginalFetch ??= globalThis.fetch;
    globalThis.__chainQaReportRequested = false;
    globalThis.fetch = async (input, init) => {
      const url = typeof input === 'string' ? input : input?.url || String(input);
      if (url.includes('/api/chains/report')) {
        globalThis.__chainQaReportRequested = true;
        return new Response(JSON.stringify({ report: ${JSON.stringify(qaReport)}, cached: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return globalThis.__chainQaOriginalFetch(input, init);
    };
    const button = [...document.querySelectorAll('.chain-detail-embedded-shell button')]
      .find((item) => item.textContent?.trim() === '重新分析');
    if (button) button.click();
    if (!button) {
      globalThis.fetch = globalThis.__chainQaOriginalFetch;
      delete globalThis.__chainQaOriginalFetch;
    }
    return Boolean(button);
  `);
  if (!reportFound) throw new Error('Chain performance interaction failed: report action not found');
  try {
    await waitFor(cdp, 'industry chain report request', `return globalThis.__chainQaReportRequested === true;`, Math.max(1000, sampleMs));
    await waitFor(cdp, 'industry chain report render', `
      return document.querySelector('.chain-detail-embedded-shell')?.textContent?.includes(${JSON.stringify(qaReport)}) || false;
    `, Math.max(1000, sampleMs));
  } finally {
    await evaluate(cdp, `
      if (globalThis.__chainQaOriginalFetch) globalThis.fetch = globalThis.__chainQaOriginalFetch;
      delete globalThis.__chainQaOriginalFetch;
      delete globalThis.__chainQaReportRequested;
      return true;
    `);
  }
}

export function buildInteractionScenarioNames(pageKey) {
  const names = ['idle'];
  if (pageKey === 'today' || pageKey === 'ingest') names.push('pointer');
  if (pageKey === 'ingest') names.push('scroll', 'modal');
  if (pageKey === 'system') names.push('system-switch', 'system-scroll');
  if (pageKey === 'series') names.push('series-switch', 'series-scroll', 'series-knowledge');
  if (pageKey === 'chains') names.push('chain-switch', 'chain-expand', 'chain-scroll', 'chain-report');
  return names;
}

async function collectInteractionPerformance(cdp, pageKey, viewport) {
  const exercises = {
    pointer: (client, sampleMs) => sweepPointer(client, sampleMs, viewport),
    scroll: (client, sampleMs) => scrollWorkspace(client, sampleMs, viewport),
    modal: openQueueModal,
    'system-switch': switchSystemControl,
    'system-scroll': (client, sampleMs) => scrollSystemDetail(client, sampleMs, viewport),
    'series-switch': switchSeries,
    'series-scroll': (client, sampleMs) => scrollSeriesDetail(client, sampleMs, viewport),
    'series-knowledge': openSeriesKnowledge,
    'chain-switch': switchIndustryChain,
    'chain-expand': expandIndustryChainNode,
    'chain-scroll': (client, sampleMs) => scrollIndustryChainDetail(client, sampleMs, viewport),
    'chain-report': clickIndustryChainReport,
  };
  const scenarios = buildInteractionScenarioNames(pageKey).map((name) => ({
    name,
    exercise: exercises[name],
  }));

  const samples = [];
  for (const scenario of scenarios) {
    const metrics = await collectRuntimePerformance(cdp, 1800, scenario.exercise);
    samples.push({ name: scenario.name, ...metrics });
    if (scenario.name === 'modal') await closeInteractionModal(cdp);
  }
  return samples;
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
      const briefingTerminalReady = () => {
        const historyError = document.querySelector('.briefing-history-list .ki-ingest-pane-state.is-error');
        if (historyError) throw new Error('Briefing QA failed: history error: ' + historyError.textContent.trim());
        const detailError = document.querySelector('.briefing-detail-state.is-error');
        if (detailError) throw new Error('Briefing QA failed: detail error: ' + detailError.textContent.trim());

        const loadingLabels = ['快报历史加载中', '快报详情加载中'];
        const loadingStates = [...document.querySelectorAll('.ki-ingest-pane-state, .briefing-detail-state')]
          .filter((element) => loadingLabels.some((label) => element.textContent.includes(label)));
        if (loadingStates.length) return false;

        const historyState = document.querySelector('.briefing-history-list .ki-ingest-pane-state');
        const historyLoaded = Boolean(document.querySelector('.briefing-history-row'));
        const historyEmpty = Boolean(historyState && historyState.textContent.includes('暂无快报'));
        const detailState = document.querySelector('.briefing-detail-state');
        const detailLoaded = Boolean(document.querySelector('.briefing-detail-header'));
        const detailEmpty = Boolean(detailState && detailState.textContent.includes('选择一份快报查看详情'));
        return (historyLoaded && detailLoaded) || (historyEmpty && detailEmpty);
      };
      if (${JSON.stringify(page.readyState || '')} === 'briefings' && !briefingTerminalReady()) return false;
      const readySelectors = ${JSON.stringify(page.readySelectors || [])};
      if (readySelectors.length) {
        const snapshot = () => readySelectors.map((selector) => {
          const element = document.querySelector(selector);
          if (!element) return null;
          const bounds = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return {
            selector,
            top: bounds.top,
            left: bounds.left,
            width: bounds.width,
            height: bounds.height,
            visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0,
          };
        });
        const before = snapshot();
        if (before.some((item) => !item || !item.visible || item.width <= 0 || item.height <= 0)) return false;
        return new Promise((resolveReady, rejectReady) => requestAnimationFrame(() => requestAnimationFrame(() => {
          try {
            const after = snapshot();
            const rectanglesStable = after.every((item, index) => item && before[index] &&
              Math.abs(item.top - before[index].top) < 0.5 &&
              Math.abs(item.left - before[index].left) < 0.5 &&
              Math.abs(item.width - before[index].width) < 0.5 &&
              Math.abs(item.height - before[index].height) < 0.5);
            resolveReady(rectanglesStable &&
              (${JSON.stringify(page.readyState || '')} !== 'briefings' || briefingTerminalReady()));
          } catch (error) {
            rejectReady(error);
          }
        })));
      }
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

  const readyMs = Math.round(performance.now() - startedAt);
  if (page.screenshotSettleMs) await wait(page.screenshotSettleMs);
  const html = await evaluate(cdp, `return document.documentElement.outerHTML;`);
  const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  writeFileSync(screenshotPath, Buffer.from(screenshot.data, 'base64'));
  return {
    readyMs,
    durationMs: Math.round(performance.now() - startedAt),
    html,
  };
}

async function collectNavigationPerformance(cdp, readyMs, includeDocumentNavigation) {
  const snapshot = await evaluate(cdp, `
    const navigation = performance.getEntriesByType('navigation').at(-1);
    const resources = performance.getEntriesByType('resource').map((entry) => ({
      name: entry.name,
      initiatorType: entry.initiatorType,
      transferSize: entry.transferSize,
      encodedBodySize: entry.encodedBodySize,
      decodedBodySize: entry.decodedBodySize,
    }));
    return {
      navigation: navigation ? {
        duration: navigation.duration,
        domInteractive: navigation.domInteractive,
        domContentLoaded: navigation.domContentLoadedEventEnd,
        loadEventEnd: navigation.loadEventEnd,
      } : null,
      resources,
    };
  `);
  return {
    readyMs,
    ...summarizeDocumentNavigation(snapshot.navigation, includeDocumentNavigation),
    ...summarizeNavigationResources(snapshot.resources || []),
  };
}

async function collectPageLayoutGeometry(cdp, pageKey) {
  if (pageKey !== 'chains') return null;
  return evaluate(cdp, `
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const bounds = element.getBoundingClientRect();
      return {
        top: Number(bounds.top.toFixed(2)),
        right: Number(bounds.right.toFixed(2)),
        bottom: Number(bounds.bottom.toFixed(2)),
        left: Number(bounds.left.toFixed(2)),
        width: Number(bounds.width.toFixed(2)),
        height: Number(bounds.height.toFixed(2)),
      };
    };
    const stage = rect('.ki-ingest-split-stage');
    const workspace = document.querySelector('.ki-shell-content');
    const list = rect('.ki-ingest-list-pane');
    const detail = rect('.ki-ingest-detail-pane');
    const detailHeader = rect('.chain-detail-embedded-shell > div:first-child');
    const navigation = rect('.dual-nav-demo__top');
    const gallery = rect('.dual-nav-demo__gallery');
    const dock = rect('.dual-nav-action-menu.is-dock');
    const detailHeaderElement = document.querySelector('.chain-detail-embedded-shell > div:first-child');
    const detailHeaderChildren = detailHeaderElement
      ? [...detailHeaderElement.children].map((element) => {
          const bounds = element.getBoundingClientRect();
          return { top: bounds.top, right: bounds.right, bottom: bounds.bottom, left: bounds.left };
        })
      : [];
    const viewport = { width: innerWidth, height: innerHeight };
    const detailHeaderVisible = Boolean(
      detailHeader &&
      detailHeader.width > 0 &&
      detailHeader.height > 0 &&
      detailHeader.top >= 0 &&
      detailHeader.bottom <= viewport.height
    );
    const workspaceScrollStable = Boolean(workspace && workspace.scrollTop === 0);
    const stageInsideViewport = Boolean(
      stage && stage.left >= 0 && stage.right <= viewport.width
    );
    const detailHeaderClearsNavigation = Boolean(navigation && detailHeader && detailHeader.top >= navigation.bottom - 1);
    const detailHeaderContentFits = Boolean(
      detail &&
      detailHeader &&
      detailHeaderChildren.length > 0 &&
      detailHeader.left >= detail.left - 1 &&
      detailHeader.right <= detail.right + 1 &&
      detailHeaderChildren.every((child) => (
        child.top >= detailHeader.top - 1 &&
        child.right <= detailHeader.right + 1 &&
        child.bottom <= detailHeader.bottom + 1 &&
        child.left >= detailHeader.left - 1
      ))
    );
    const listDoesNotCrossDetail = Boolean(list && detail && list.right <= detail.left + 1);
    const detailClearsDock = Boolean(detail && dock && detail.bottom <= dock.top - 4);
    const stageContainsColumns = Boolean(
      stage && list && detail &&
      list.top >= stage.top - 1 && list.right <= stage.right + 1 &&
      list.bottom <= stage.bottom + 1 && list.left >= stage.left - 1 &&
      detail.top >= stage.top - 1 && detail.right <= stage.right + 1 &&
      detail.bottom <= stage.bottom + 1 && detail.left >= stage.left - 1
    );
    const dockInsideGallery = Boolean(
      gallery && dock &&
      dock.top >= gallery.top - 1 && dock.right <= gallery.right + 1 &&
      dock.bottom <= gallery.bottom + 1 && dock.left >= gallery.left - 1
    );
    return {
      viewport,
      stage,
      list,
      detail,
      detailHeader,
      navigation,
      gallery,
      dock,
      detailHeaderVisible,
      workspaceScrollStable,
      stageInsideViewport,
      detailHeaderClearsNavigation,
      detailHeaderContentFits,
      listDoesNotCrossDetail,
      detailClearsDock,
      stageContainsColumns,
      dockInsideGallery,
      pass: workspaceScrollStable && stageInsideViewport && detailHeaderVisible && detailHeaderClearsNavigation && detailHeaderContentFits &&
        listDoesNotCrossDetail && detailClearsDock && stageContainsColumns && dockInsideGallery,
    };
  `);
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
  gpuMode = 'swiftshader',
  revisitFirstPage = false,
  warmRevisitCount = 1,
} = {}) {
  const resolvedOutDir = resolve(outDir);
  mkdirSync(resolvedOutDir, { recursive: true });

  const health = await fetchHealth(baseUrl);
  const reports = [];
  const port = await findFreePort();
  const userDataDir = mkdtempSync(resolve(tmpdir(), 'ki-cinematic-pages-'));
  const gpuArgs = gpuMode === 'metal'
    ? ['--use-angle=metal', '--ignore-gpu-blocklist', '--enable-gpu-rasterization']
    : ['--disable-gpu', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
  const chrome = spawn(chromePath, [
    '--headless=new',
    ...gpuArgs,
    '--hide-scrollbars',
    '--no-first-run',
    '--no-default-browser-check',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    `--window-size=${viewport.width},${viewport.height}`,
    'about:blank',
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
    await cdp.send('Performance.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: 1,
      mobile: false,
    });

    for (const page of buildCinematicVisitSequence(pageKeys, revisitFirstPage, warmRevisitCount)) {
      const url = pageUrl(baseUrl, page.path);
      const viewportLabel = `${viewport.width}x${viewport.height}`;
      const visitSuffix = revisitFirstPage ? `-${page.visit}` : '';
      const screenshotPath = resolve(resolvedOutDir, `${page.key}${visitSuffix}-${viewportLabel}.png`);
      await evaluate(cdp, `performance.clearResourceTimings(); return true;`);
      const capture = await capturePageWithCdp({ cdp, url, page, screenshotPath });
      const navigationPerformance = await collectNavigationPerformance(cdp, capture.readyMs, page.visit === 'cold');
      const layoutGeometry = await collectPageLayoutGeometry(cdp, page.key);
      const screenshotVisual = readPngVisualStats(screenshotPath);
      if (mode === 'performance') await wait(performanceSettleMs);
      const interactionPerformance = mode === 'performance'
        ? await collectInteractionPerformance(cdp, page.key, viewport)
        : null;
      const runtimePerformance = interactionPerformance?.find((sample) => sample.name === 'idle') || null;
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
        layoutGeometry: layoutGeometry?.pass ?? true,
      };
      const renderPass = Boolean(
        Object.values(markerStatus).every(Boolean) &&
        thresholds.canvasCount &&
        thresholds.screenshotVisual &&
        thresholds.layoutGeometry &&
        !html.includes('加载中...')
      );

      reports.push({
        key: page.key,
        visit: page.visit,
        url,
        screenshotPath,
        readyMs: capture.readyMs,
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
        layoutGeometry,
        navigationPerformance,
        runtimePerformance,
        interactionPerformance,
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
    await stopChildProcess(chrome);
  }

  const report = {
    mode,
    gpuMode,
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
    if (page.runtimePerformance) console.log(`${page.key}_runtime=${JSON.stringify(page.runtimePerformance)}`);
    console.log(`${page.key}_screenshot=${page.screenshotPath}`);
  }
  console.log(`pass=${report.pass}`);

  if (!report.pass) throw new Error(`Cinematic page QA failed: ${reportPath}`);
  return report;
}
