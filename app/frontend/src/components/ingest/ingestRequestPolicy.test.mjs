import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('./ingestRequestPolicy.ts', import.meta.url), 'utf8');
const ingest = readFileSync(new URL('../../pages/Ingest.tsx', import.meta.url), 'utf8');

test('queue polling is scoped to visible work', () => {
  assert.match(source, /modalOpen/);
  assert.match(source, /Boolean\(pollId\)/);
  assert.match(source, /pending/);
  assert.match(source, /running/);
  assert.match(ingest, /shouldPollQueue/);
  assert.match(ingest, /document\.hidden/);
});

test('event search is debounced and only the latest response commits', () => {
  assert.match(ingest, /useDebouncedValue\(search, 250\)/);
  assert.match(ingest, /eventRequestSequenceRef/);
  assert.match(ingest, /eventRequestAbortRef\.current\?\.abort\(\)/);
  assert.match(ingest, /signal: requestController\.signal/);
  assert.match(ingest, /isLatestRequest/);
});

test('statistics are not reloaded by list navigation', () => {
  assert.doesNotMatch(ingest, /loadEvents\(\);\s*loadStats\(\);\s*\}, \[historyTab, page/);
  assert.match(ingest, /void loadStats\(\);\s*\}, \[loadStats\]\)/);
});

test('ingest request families abort stale work and clean up on unmount', () => {
  assert.match(ingest, /statusRequestLifecycleRef/);
  assert.match(ingest, /queueRequestLifecycleRef/);
  assert.match(ingest, /briefingRequestLifecycleRef/);
  assert.match(ingest, /topicCountRequestLifecycleRef/);
  assert.match(ingest, /abortableDelay\(2000, signal\)/);
  assert.match(ingest, /statusRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(ingest, /queueRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(ingest, /briefingRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(ingest, /topicCountRequestLifecycleRef\.current\.abort\(\)/);
});

test('queue and supporting requests only commit their latest response', () => {
  assert.match(ingest, /const loadQueue = useCallback/);
  assert.match(ingest, /const loadBriefing = useCallback/);
  assert.match(ingest, /const loadTopicCounts = useCallback/);
  assert.match(ingest, /queueRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(ingest, /briefingRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(ingest, /topicCountRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(ingest, /apiFetch\('\/api\/ingest\/queue\?limit=30', \{ signal \}\)/);
});
