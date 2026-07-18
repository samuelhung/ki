import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';

import {
  buildCinematicVisitSequence,
  selectCinematicPages,
  summarizeDocumentNavigation,
  stopChildProcess,
  summarizeNavigationResources,
} from './qa-cinematic-pages-core.mjs';

test('selectCinematicPages returns only requested page keys', () => {
  assert.deepEqual(selectCinematicPages(['study']).map((page) => page.key), ['study']);
  assert.deepEqual(selectCinematicPages(['study', 'system']).map((page) => page.key), ['system', 'study']);
});

test('selectCinematicPages rejects unknown page keys', () => {
  assert.throws(() => selectCinematicPages(['missing']), /Unknown cinematic page key/);
});

test('toolbox performance baseline follows the migrated single-canvas shell', () => {
  const [toolbox] = selectCinematicPages(['toolbox']);
  assert.equal(toolbox.expectedCanvasCount, 1);
  assert.deepEqual(toolbox.markers, [
    'ki-shell-toolbox',
    'toolbox-tool-list',
    'toolbox-detail-reader',
    'toolbox-primary-results',
  ]);
});

test('series performance baseline follows the migrated single-canvas shell', () => {
  const [series] = selectCinematicPages(['series']);
  assert.equal(series.expectedCanvasCount, 1);
  assert.deepEqual(series.markers, [
    'ki-shell-series',
    'series-status-tabs',
    'series-list',
    'series-detail-legacy-content',
  ]);
});

test('production visits capture cold route and warm-revisit phases in one browser session', () => {
  assert.deepEqual(
    buildCinematicVisitSequence(['today', 'ingest'], true, 3).map(({ key, visit }) => ({ key, visit })),
    [
      { key: 'today', visit: 'cold' },
      { key: 'ingest', visit: 'route' },
      { key: 'today', visit: 'warm-revisit-1' },
      { key: 'ingest', visit: 'route-repeat-1' },
      { key: 'today', visit: 'warm-revisit-2' },
      { key: 'ingest', visit: 'route-repeat-2' },
      { key: 'today', visit: 'warm-revisit-3' },
    ],
  );
});

test('navigation resources distinguish transferred assets from cache hits', () => {
  assert.deepEqual(summarizeNavigationResources([
    { name: '/app.js', initiatorType: 'script', transferSize: 1200, encodedBodySize: 900, decodedBodySize: 1800 },
    { name: '/app.css', initiatorType: 'link', transferSize: 0, encodedBodySize: 500, decodedBodySize: 900 },
    { name: '/api/health', initiatorType: 'fetch', transferSize: 300, encodedBodySize: 80, decodedBodySize: 80 },
  ]), {
    resourceCount: 3,
    cacheHitCount: 1,
    transferBytes: 1500,
    encodedBytes: 1480,
    decodedBytes: 2780,
    jsCssTransferBytes: 1200,
  });
});

test('spa route visits do not reuse the original document navigation timing', () => {
  const navigation = { duration: 406.6, domInteractive: 272.7, domContentLoaded: 406.1, loadEventEnd: 406.6 };
  assert.deepEqual(summarizeDocumentNavigation(navigation, false), {
    navigationKind: 'spa-route',
    browserNavigationMs: null,
    domInteractiveMs: null,
    domContentLoadedMs: null,
    loadEventEndMs: null,
  });
  assert.deepEqual(summarizeDocumentNavigation(navigation, true), {
    navigationKind: 'document',
    browserNavigationMs: 406.6,
    domInteractiveMs: 272.7,
    domContentLoadedMs: 406.1,
    loadEventEndMs: 406.6,
  });
});

test('qa waits for Chrome to exit after sending the termination signal', async () => {
  const child = new EventEmitter();
  child.exitCode = null;
  child.killed = false;
  child.signals = [];
  child.kill = (signal) => {
    child.killed = true;
    child.signals.push(signal);
    queueMicrotask(() => {
      child.exitCode = 0;
      child.emit('exit', 0, signal);
    });
    return true;
  };

  await stopChildProcess(child, 50);

  assert.deepEqual(child.signals, ['SIGTERM']);
  assert.equal(child.exitCode, 0);
});
