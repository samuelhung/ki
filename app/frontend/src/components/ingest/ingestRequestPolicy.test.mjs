import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const ingest = readFileSync(new URL('../cinematic-ingest/useIngestEvents.ts', import.meta.url), 'utf8');

test('event search is debounced and only the latest response commits', () => {
  assert.match(ingest, /useDebouncedValue\(search, 250\)/);
  assert.doesNotMatch(ingest, /listQueryRef/);
  assert.match(ingest, /eventRequestCoordinator\.start\(\)/);
  assert.match(ingest, /eventRequestCoordinator\.run\(/);
  assert.match(ingest, /\{ signal \}/);
  assert.match(ingest, /\[debouncedSearch, eventRequestCoordinator, historyTab\]/);
});

test('embedded list requests do not retain standalone statistics or pagination fetches', () => {
  assert.doesNotMatch(ingest, /loadStats|topic-counts|setTotal|setPage/);
  assert.match(ingest, /limit=\$\{PAGE_SIZE\}&offset=0&count=1/);
});

test('retained ingest request families abort stale work and clean up on unmount', () => {
  assert.match(ingest, /statusRequestLifecycleRef/);
  assert.match(ingest, /abortableDelay\(2000, signal\)/);
  assert.match(ingest, /statusRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(ingest, /eventRequestCoordinator\.abort\(\)/);
  assert.doesNotMatch(ingest, /briefingRequestLifecycleRef|\/api\/briefing\/latest/);
});

test('status polling keeps its endpoint delay latest-owner checks and completion refresh', () => {
  assert.match(ingest, /apiFetch\(`\/api\/ingest\/status\/\$\{eventId\}`, \{ signal \}\)/);
  assert.match(ingest, /for \(let attempt = 0; attempt < 120; attempt \+= 1\)/);
  assert.match(ingest, /statusRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(ingest, /completionTimerRef\.current = window\.setTimeout/);
  assert.match(ingest, /const loadEventsRef = useRef\(loadEvents\)/);
  assert.match(ingest, /loadEventsRef\.current = loadEvents/);
  assert.match(ingest, /void loadEventsRef\.current\(\)/);
  const completionCallback = ingest.match(/completionTimerRef\.current = window\.setTimeout\(\(\) => \{([\s\S]*?)\n          \}, 1500\)/)?.[1] || '';
  assert.doesNotMatch(completionCallback, /void loadEvents\(\)/);
});
