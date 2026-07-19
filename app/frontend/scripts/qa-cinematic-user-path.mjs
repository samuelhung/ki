import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import net from 'node:net';

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const generateBriefing = /^(?:1|true)$/i.test(process.env.ZHIJI_QA_GENERATE_BRIEFING || '');

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
  const events = [];

  socket.addEventListener('message', (message) => {
    const payload = JSON.parse(message.data.toString());
    if (payload.id && pending.has(payload.id)) {
      const { resolveCommand, rejectCommand } = pending.get(payload.id);
      pending.delete(payload.id);
      if (payload.error) rejectCommand(new Error(payload.error.message || JSON.stringify(payload.error)));
      else resolveCommand(payload.result);
      return;
    }
    events.push(payload);
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
      }, 15000);
    });
  }

  return {
    events,
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

async function waitFor(cdp, label, source, timeoutMs = 15000) {
  const startedAt = performance.now();
  while (performance.now() - startedAt < timeoutMs) {
    const value = await evaluate(cdp, source);
    if (value) return value;
    await new Promise((resolveWait) => setTimeout(resolveWait, 180));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function waitForStableSelectors(cdp, label, selectors, timeoutMs = 20000) {
  await waitFor(cdp, label, `
    const selectors = ${JSON.stringify(selectors)};
    const snapshot = () => selectors.map((selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const bounds = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        top: bounds.top,
        left: bounds.left,
        width: bounds.width,
        height: bounds.height,
        visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0,
      };
    });
    const before = snapshot();
    if (before.some((item) => !item || !item.visible || item.width <= 0 || item.height <= 0)) return false;
    return new Promise((resolveStable) => requestAnimationFrame(() => requestAnimationFrame(() => {
      const after = snapshot();
      resolveStable(after.every((item, index) => item && before[index] &&
        Math.abs(item.top - before[index].top) < 0.5 &&
        Math.abs(item.left - before[index].left) < 0.5 &&
        Math.abs(item.width - before[index].width) < 0.5 &&
        Math.abs(item.height - before[index].height) < 0.5));
    })));
  `, timeoutMs);
}

async function waitForBriefingTerminalState(cdp, timeoutMs = 20000) {
  await waitFor(cdp, 'briefing history and detail terminal state', `
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
  `, timeoutMs);
}

async function navigate(cdp, url, markerSource) {
  await cdp.send('Page.navigate', { url });
  await waitFor(cdp, `page ${url}`, `return document.readyState === 'complete' || document.readyState === 'interactive';`);
  await waitFor(cdp, `marker ${url}`, markerSource, 20000);
}

async function capture(cdp, outDir, name) {
  const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  const filePath = resolve(outDir, `${name}.png`);
  writeFileSync(filePath, Buffer.from(screenshot.data, 'base64'));
  return filePath;
}

async function runJourneyQa(baseUrl, outDir) {
  const port = await findFreePort();
  const userDataDir = mkdtempSync(resolve(tmpdir(), 'ki-cinematic-journey-'));
  const resolvedOutDir = resolve(outDir);
  mkdirSync(resolvedOutDir, { recursive: true });

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
    '--window-size=1440,900',
    pageUrl(baseUrl, '/#/'),
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const stderr = [];
  chrome.stderr.on('data', (chunk) => stderr.push(chunk.toString()));

  let cdp;
  const assertions = [];
  const screenshots = [];

  try {
    const pages = await waitForJson(`http://127.0.0.1:${port}/json/list`);
    const page = pages.find((item) => item.type === 'page') || pages[0];
    if (!page?.webSocketDebuggerUrl) throw new Error('No debuggable Chrome page found');
    cdp = await connectCdp(page.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');

    await navigate(cdp, pageUrl(baseUrl, '/#/ingest'), `
      return Boolean(document.querySelector('.cinematic-ingest-shell') && document.querySelector('.ingest-detail-reader') && document.querySelector('.observation-queue-list'));
    `);
    assertions.push('ingest_shell_ready');

    await evaluate(cdp, `
      const entry = document.querySelector('.launcher-action.is-douyin');
      if (!entry) return false;
      entry.click();
      return true;
    `);
    await waitFor(cdp, 'douyin access dialog', `
      return Boolean(document.querySelector('.ingest-command-overlay .command-screen.is-access-box textarea') && document.querySelector('.ingest-command-overlay button[role="tab"]'));
    `);
    assertions.push('douyin_dialog_open');

    const submitStates = await evaluate(cdp, `
      const textarea = document.querySelector('.ingest-command-overlay textarea');
      const button = document.querySelector('.ingest-command-overlay form button[type="submit"]');
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      const before = Boolean(button?.disabled);
      setter.call(textarea, 'QA 路径验证：只检查输入态，不提交真实处理任务');
      textarea.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: 'QA' }));
      return new Promise((resolve) => {
        requestAnimationFrame(() => {
          const after = Boolean(button?.disabled);
          setter.call(textarea, '');
          textarea.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContentBackward' }));
          resolve({ before, after });
        });
      });
    `);
    if (!submitStates.before || submitStates.after) throw new Error(`Unexpected submit state: ${JSON.stringify(submitStates)}`);
    assertions.push('douyin_input_enables_submit');

    await evaluate(cdp, `
      const fileTab = Array.from(document.querySelectorAll('.ingest-command-overlay button[role="tab"]')).find((button) => button.textContent.includes('文件上传'));
      if (!fileTab) return false;
      fileTab.click();
      return true;
    `);
    await waitFor(cdp, 'file upload tab', `return Boolean(document.querySelector('.ingest-command-overlay input[type="file"]'));`);
    assertions.push('file_tab_switches');

    await evaluate(cdp, `document.querySelector('.ingest-command-overlay .command-screen-header button')?.click(); return true;`);
    await waitFor(cdp, 'dialog closed', `return !document.querySelector('.ingest-command-overlay');`);
    assertions.push('dialog_closes_without_submit');

    const detailTabs = await evaluate(cdp, `
      const labels = [];
      for (const button of document.querySelectorAll('.ingest-detail-tabs button')) {
        button.click();
        labels.push(button.textContent.trim());
      }
      return {
        labels,
        stillHasReader: Boolean(document.querySelector('.ingest-detail-reader')),
        stillHasBody: Boolean(document.querySelector('.ingest-detail-body, .detail-scroll, .ingest-detail-reader')),
      };
    `);
    if (!detailTabs.stillHasReader || detailTabs.labels.length < 4) {
      throw new Error(`Detail tabs did not stay mounted: ${JSON.stringify(detailTabs)}`);
    }
    assertions.push('detail_tabs_switch');
    screenshots.push(await capture(cdp, resolvedOutDir, 'ingest-journey'));

    await navigate(cdp, pageUrl(baseUrl, '/#/briefings'), `
      const selectors = ['.ki-shell-briefings', '.briefing-split-stage', '.briefing-history-pane', '.briefing-detail-pane'];
      return selectors.every((selector) => {
        const element = document.querySelector(selector);
        if (!element) return false;
        const bounds = element.getBoundingClientRect();
        return bounds.width > 0 && bounds.height > 0;
      });
    `);
    await waitForBriefingTerminalState(cdp);
    await waitForStableSelectors(cdp, 'stable briefing workspace', [
      '.ki-shell-briefings',
      '.briefing-split-stage',
      '.briefing-history-pane',
      '.briefing-detail-pane',
    ]);
    await waitForBriefingTerminalState(cdp);
    assertions.push('briefing_workspace_ready');

    if (generateBriefing) {
      const initialBriefingState = await evaluate(cdp, `
        const rows = [...document.querySelectorAll('.briefing-history-row')];
        return { count: rows.length, first: rows[0]?.textContent || '' };
      `);
      const generationStarted = await evaluate(cdp, `
        const button = document.querySelector('.briefing-generate-button');
        if (!button || button.disabled) return false;
        button.click();
        return true;
      `);
      if (!generationStarted) throw new Error('Briefing generation button was not available');
      await waitFor(cdp, 'briefing generation', `
        const button = document.querySelector('.briefing-generate-button');
        const rows = [...document.querySelectorAll('.briefing-history-row')];
        const first = rows[0]?.textContent || '';
        const changed = rows.length > ${initialBriefingState.count} || first !== ${JSON.stringify(initialBriefingState.first)};
        return Boolean(button && !button.disabled && !document.querySelector('.briefing-generate-error') && changed);
      `, 120000);
      assertions.push('briefing_generation_succeeds');
    } else {
      assertions.push('briefing_generation_skipped');
    }
    screenshots.push(await capture(cdp, resolvedOutDir, 'briefings-journey'));

    await navigate(cdp, pageUrl(baseUrl, '/#/system'), `
      return Boolean(document.querySelector('.system-detail-reader') && document.querySelector('.system-core-box'));
    `);
    assertions.push('system_shell_ready');

    await evaluate(cdp, `
      const refresh = Array.from(document.querySelectorAll('button')).find((button) => /刷新状态|REFRESH/i.test(button.textContent));
      if (refresh) refresh.click();
      return Boolean(refresh);
    `);
    await waitFor(cdp, 'system reader survives refresh', `return Boolean(document.querySelector('.system-detail-reader') && document.querySelector('.system-core-box'));`);
    assertions.push('system_refresh_survives');
    screenshots.push(await capture(cdp, resolvedOutDir, 'system-journey'));

    const report = {
      baseUrl,
      capturedAt: new Date().toISOString(),
      assertions,
      screenshots,
      pass: true,
    };
    const reportPath = resolve(resolvedOutDir, 'cinematic-user-path.json');
    writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
    console.log(`qa_report=${reportPath}`);
    console.log(`assertions=${assertions.join(',')}`);
    screenshots.forEach((filePath) => console.log(`screenshot=${filePath}`));
    console.log('pass=true');
  } catch (error) {
    const reportPath = resolve(resolvedOutDir, 'cinematic-user-path.json');
    writeFileSync(reportPath, `${JSON.stringify({
      baseUrl,
      capturedAt: new Date().toISOString(),
      assertions,
      stderr: stderr.join('').split('\n').slice(-40),
      error: error instanceof Error ? error.message : String(error),
      pass: false,
    }, null, 2)}\n`);
    console.log(`qa_report=${reportPath}`);
    console.log(`pass=false`);
    throw error;
  } finally {
    cdp?.close();
    chrome.kill('SIGTERM');
  }
}

await runJourneyQa(
  process.argv[2] || 'http://10.8.0.105:9120',
  process.argv[3] || 'tmp/cinematic-user-path-qa',
);
