import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import test from 'node:test';

const requestsUrl = new URL('./briefingRequests.mjs', import.meta.url);

function jsonResponse(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    async json() { return payload; },
  };
}

test('history request uses canonical pagination and returns newest valid items', async () => {
  assert.equal(existsSync(requestsUrl), true, 'briefingRequests.mjs should exist');
  const { fetchBriefingHistory } = await import(requestsUrl);
  const signal = new AbortController().signal;
  const calls = [];
  const apiFetch = async (...args) => {
    calls.push(args);
    return jsonResponse({
      total: 3,
      items: [
        { id: 'briefing-old', created_at: '2026-07-18 10:00:00' },
        null,
        { id: 'briefing-new', created_at: '2026-07-19 10:00:00' },
      ],
    });
  };

  const result = await fetchBriefingHistory({ apiFetch, signal });

  assert.deepEqual(result.items.map((item) => item.id), ['briefing-new', 'briefing-old']);
  assert.equal(result.total, 3);
  assert.deepEqual(calls, [['/api/briefing?limit=30&offset=0', { signal }]]);
});

test('history request surfaces backend errors', async () => {
  assert.equal(existsSync(requestsUrl), true, 'briefingRequests.mjs should exist');
  const { fetchBriefingHistory } = await import(requestsUrl);
  const apiFetch = async () => jsonResponse({ detail: '历史服务暂不可用' }, { ok: false, status: 503 });

  await assert.rejects(
    fetchBriefingHistory({ apiFetch, signal: new AbortController().signal }),
    /历史服务暂不可用/,
  );
});

test('detail request uses its briefingId argument and signal', async () => {
  assert.equal(existsSync(requestsUrl), true, 'briefingRequests.mjs should exist');
  const { fetchBriefingDetail } = await import(requestsUrl);
  const signal = new AbortController().signal;
  const calls = [];
  const apiFetch = async (...args) => {
    calls.push(args);
    return jsonResponse({ id: 'briefing-target', topics: [] });
  };

  const detail = await fetchBriefingDetail({ apiFetch, signal, briefingId: 'briefing-target' });

  assert.equal(detail.id, 'briefing-target');
  assert.deepEqual(calls, [['/api/briefing/briefing-target', { signal }]]);
});

test('generation rejects a successful payload without a non-empty string id', async () => {
  assert.equal(existsSync(requestsUrl), true, 'briefingRequests.mjs should exist');
  const { generateQuickBriefing } = await import(requestsUrl);
  const calls = [];
  const apiFetch = async (...args) => {
    calls.push(args);
    return jsonResponse({ id: '   ' });
  };

  await assert.rejects(
    generateQuickBriefing({ apiFetch, signal: new AbortController().signal }),
    /生成结果缺少有效快报 ID/,
  );
  assert.equal(calls[0][0], '/api/briefing/generate');
  assert.equal(calls[0][1].method, 'POST');
  assert.equal(calls[0][1].body, JSON.stringify({ type: 'quick' }));
});

test('request helpers propagate aborts and rejected fetches unchanged', async () => {
  assert.equal(existsSync(requestsUrl), true, 'briefingRequests.mjs should exist');
  const { fetchBriefingDetail, fetchBriefingHistory } = await import(requestsUrl);
  const abortError = new DOMException('Aborted', 'AbortError');
  const fetchError = new Error('network down');

  await assert.rejects(
    fetchBriefingHistory({ apiFetch: async () => { throw abortError; }, signal: new AbortController().signal }),
    (error) => error === abortError,
  );
  await assert.rejects(
    fetchBriefingDetail({ apiFetch: async () => { throw fetchError; }, signal: new AbortController().signal, briefingId: 'briefing-target' }),
    (error) => error === fetchError,
  );
});
