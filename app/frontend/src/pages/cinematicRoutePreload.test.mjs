import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { scheduleCinematicRoutePreload } from './cinematicRoutePreload.ts';

const home = readFileSync(new URL('./CinematicHome.tsx', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('./LegacyIngestShellPreview.tsx', import.meta.url), 'utf8');

test('route preload uses cancellable browser idle time', async () => {
  const originalRequestIdleCallback = globalThis.requestIdleCallback;
  const originalCancelIdleCallback = globalThis.cancelIdleCallback;
  let idleCallback;
  let cancelledHandle;
  let loadCount = 0;

  globalThis.requestIdleCallback = (callback) => {
    idleCallback = callback;
    return 17;
  };
  globalThis.cancelIdleCallback = (handle) => {
    cancelledHandle = handle;
  };

  try {
    const cancel = scheduleCinematicRoutePreload(async () => {
      loadCount += 1;
    });

    assert.equal(typeof idleCallback, 'function');
    idleCallback({ didTimeout: false, timeRemaining: () => 12 });
    await Promise.resolve();
    assert.equal(loadCount, 1);

    cancel();
    assert.equal(cancelledHandle, 17);
  } finally {
    globalThis.requestIdleCallback = originalRequestIdleCallback;
    globalThis.cancelIdleCallback = originalCancelIdleCallback;
  }
});

test('route preload fallback can be cancelled before its timer runs', async () => {
  const originalRequestIdleCallback = globalThis.requestIdleCallback;
  const originalCancelIdleCallback = globalThis.cancelIdleCallback;
  let loadCount = 0;

  delete globalThis.requestIdleCallback;
  delete globalThis.cancelIdleCallback;

  try {
    const cancel = scheduleCinematicRoutePreload(async () => {
      loadCount += 1;
    }, { fallbackDelay: 0 });
    cancel();
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.equal(loadCount, 0);
  } finally {
    globalThis.requestIdleCallback = originalRequestIdleCallback;
    globalThis.cancelIdleCallback = originalCancelIdleCallback;
  }
});

test('homepage and ingestion preload each other without mounting a second scene', () => {
  assert.match(home, /scheduleCinematicRoutePreload/);
  assert.match(home, /import\('\.\/LegacyIngestShellPreview'\)/);
  assert.match(ingest, /scheduleCinematicRoutePreload/);
  assert.match(ingest, /import\('\.\/CinematicHome'\)/);
  assert.doesNotMatch(home, /<LegacyIngestShellPreview/);
  assert.doesNotMatch(ingest, /<CinematicHome/);
});
