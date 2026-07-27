import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import {
  assertForwardedCallbacks,
  assertNamedImports,
  combinedSource,
  loadRequestCoordinatorFactory,
  objectArrayValues,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const pageUrl = new URL('../../pages/Ingest.tsx', import.meta.url);
const hookUrl = new URL('./useIngestEvents.ts', import.meta.url);
const workspaceUrl = new URL('./IngestWorkspaceContent.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, hookUrl, workspaceUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'Ingest.tsx');
assert.ok(pageModule);
const page = pageModule.source;

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function assertIngestRequestCoordinatorBehavior(createRequestCoordinator) {
  const commits = [];
  const errors = [];
  const coordinator = createRequestCoordinator({
    onCommit: (value) => commits.push(value),
    onError: (error) => errors.push(error),
  });
  for (const method of ['start', 'run', 'isCurrent', 'abort']) {
    assert.equal(typeof coordinator[method], 'function', `request coordinator must expose ${method}()`);
  }
  assert.equal('mutateAndRefresh' in coordinator, false);

  const stale = deferred();
  const staleOwner = coordinator.start();
  const staleRun = coordinator.run({ owner: staleOwner, request: () => stale.promise });
  const currentOwner = coordinator.start();
  assert.equal(staleOwner.signal.aborted, true);
  await coordinator.run({ owner: currentOwner, request: async () => ({ id: 'current' }) });
  stale.resolve({ id: 'stale' });
  await staleRun;
  assert.deepEqual(commits, [{ id: 'current' }]);

  const failure = new Error('request failed');
  const errorOwner = coordinator.start();
  await coordinator.run({ owner: errorOwner, request: async () => { throw failure; } });
  assert.deepEqual(errors, [failure]);

  const abortedOwner = coordinator.start();
  const abortedRun = coordinator.run({
    owner: abortedOwner,
    request: (signal) => new Promise((resolve, reject) => {
      assert.equal(signal, abortedOwner.signal);
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
    }),
  });
  coordinator.abort();
  await abortedRun;
  assert.equal(coordinator.isCurrent(abortedOwner), false);
  assert.deepEqual(errors, [failure]);
}

function assertCoordinatorUsedByHook(hookModule) {
  const hookDeclaration = hookModule.sourceFile.statements.find((statement) => (
    ts.isFunctionDeclaration(statement) && statement.name?.text === 'useIngestEvents'
  ));
  assert.ok(hookDeclaration);
  const calls = [];
  function visit(node) {
    if (ts.isCallExpression(node)) calls.push(node.expression.getText(hookModule.sourceFile));
    ts.forEachChild(node, visit);
  }
  visit(hookDeclaration);
  for (const expected of [
    'createRequestCoordinator',
    'eventRequestCoordinator.start',
    'eventRequestCoordinator.run',
    'eventRequestCoordinator.isCurrent',
    'eventRequestCoordinator.abort',
  ]) assert.ok(calls.includes(expected), `useIngestEvents must call ${expected}`);
}

test('ingest detail tabs can move while preserving exact definitions and order', () => {
  assert.deepEqual(objectArrayValues(modules, 'DETAIL_TABS'), [
    { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: 'FileText' },
    { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: 'Sparkles' },
    { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: 'Link2' },
    { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: 'Radio' },
  ]);
  assert.match(implementation, /DETAIL_TABS\.map\(\(tab\) =>/);
  assert.match(implementation, /ingest-tab-trigger launcher-action pixel-command/);
});

test('ingest endpoints preserve list mutation upload and status polling contracts', () => {
  assert.match(implementation, /const PAGE_SIZE = 15/);
  assert.match(implementation, /const API_BASE = '\/api\/events'/);
  assert.match(implementation, /sourceId = 'douyin,user-upload,user-concept'/);
  assert.match(implementation, /limit=\$\{PAGE_SIZE\}&offset=0&count=1/);
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/status\/\$\{eventId\}`, \{ signal \}\)/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/douyin', \{\s*method: 'POST'/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/file', \{ method: 'POST', timeoutMs: 900_000, body \}\)/);
  assert.match(implementation, /apiFetch\(`\$\{API_BASE\}\/\$\{eventId\}`, \{ method: 'DELETE' \}\)/);
  assert.match(implementation, /void loadEventsRef\.current\(\)/);
});

test('ingest lifecycle source preserves cancellation stale suppression refreshes and errors', () => {
  assert.match(implementation, /eventRequestCoordinator\.start\(\)/);
  assert.match(implementation, /eventRequestCoordinator\.run\(/);
  assert.match(implementation, /eventRequestCoordinator\.isCurrent\(owner\)/);
  assert.match(implementation, /eventRequestCoordinator\.abort\(\)/);
  assert.match(implementation, /error\?\.name !== 'AbortError'/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(implementation, /await loadEventsRef\.current\(\)/);
  assert.match(implementation, /setEventsError\(error\.message \|\| '加载事件列表失败'\)/);
});

test('ingest list queries are committed callback inputs instead of render-phase refs', () => {
  const hook = readFileSync(hookUrl, 'utf8');
  assert.doesNotMatch(hook, /listQueryRef/);
  assert.match(hook, /const topicFilter = [^\n]*historyTab/);
  assert.match(hook, /const searchParam = debouncedSearch/);
  assert.match(hook, /\}, \[debouncedSearch, eventRequestCoordinator, historyTab\]\);/);
});

test('ingest labels css hooks and embedded composition can move together', () => {
  for (const label of ['搜索内容标题', '提交抖音视频', '上传文件', '分享文本（从抖音复制）', '分类（可选）']) {
    assert.match(implementation, new RegExp(label));
  }
  assert.match(implementation, /legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(implementation, /<EmbeddedIngestList/);
  assert.match(implementation, /<ContentDetailPanel/);
  assert.match(implementation, /<EmbeddedIngestWorkspace/);
});

test('request coordinator loader transpiles typed hook exports without resolving React imports', () => {
  const source = `
    import React, { useState } from 'react';
    interface Options { onCommit: (value: string) => void; }
    export function createRequestCoordinator(options: Options) {
      return (value: string) => options.onCommit(value);
    }
  `;
  const module = {
    name: 'typedHook.ts',
    source,
    sourceFile: ts.createSourceFile('typedHook.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS),
  };
  let committed = '';
  const coordinator = loadRequestCoordinatorFactory(module)({ onCommit: (value) => { committed = value; } });
  coordinator('loaded');
  assert.equal(committed, 'loaded');
});

test('ingest extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.6 must add useIngestEvents.ts');
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useIngestEvents.ts');
  assert.ok(hookModule);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle', 'abortableDelay']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertIngestRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));
  assertCoordinatorUsedByHook(hookModule);

  assert.ok(existsSync(workspaceUrl), 'Task 5.6 must add IngestWorkspaceContent.tsx');
  assert.match(page, /useIngestEvents\(/);
  assertForwardedCallbacks(pageModule, 'IngestWorkspaceContent', {
    onRetry: 'loadEvents',
    onSelect: 'openDetail',
    onDelete: 'handleDelete',
    onTopicChange: 'handleEmbeddedTopicChange',
    onSearchChange: 'handleEmbeddedSearchChange',
    onSummarize: 'handleEmbeddedSummarize',
    onContemplate: 'details.handleContemplate',
    onLinkQuestions: 'details.handleContemplateLink',
    onChainAnalyze: 'details.handleChainAnalyze',
    onSyncHints: 'details.handleSyncHints',
  });
  assert.doesNotMatch(page, /new RequestLifecycle\(\)|new AbortController\(\)/);
  assert.match(hook, /isLatestRequest|isCurrent|sequence/);
});
