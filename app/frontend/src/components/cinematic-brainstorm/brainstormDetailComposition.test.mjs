import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { isLatestRequest } from '../ingest/ingestRequestPolicy.ts';
import { RequestLifecycle } from '../ingest/requestLifecycle.ts';
import {
  assertExportedObjectType,
  assertForwardedCallbacks,
  assertNamedImports,
  assertRequestCoordinatorBehavior,
  combinedSource,
  loadPureDeclarations,
  loadRequestCoordinatorFactory,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const pageUrl = new URL('../../pages/BrainstormDetailPage.tsx', import.meta.url);
const hookUrl = new URL('./useBrainstormDetail.ts', import.meta.url);
const operationsUrl = new URL('./brainstormDetailOperations.ts', import.meta.url);
const answerPanelUrl = new URL('./BrainstormAnswerPanel.tsx', import.meta.url);
const conversationPanelUrl = new URL('./BrainstormConversationPanel.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, hookUrl, operationsUrl, answerPanelUrl, conversationPanelUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'BrainstormDetailPage.tsx');
const hookModule = modules.find((module) => module.name === 'useBrainstormDetail.ts');
const conversationPanelModule = modules.find((module) => module.name === 'BrainstormConversationPanel.tsx');
assert.ok(pageModule);
assert.ok(hookModule);
assert.ok(conversationPanelModule);
const page = pageModule.source;
const hook = hookModule.source;
const conversationPanel = conversationPanelModule.source;

test('brainstorm detail keeps the exact exported question type and page ownership', () => {
  assertExportedObjectType(modules, 'BrainstormQuestion', {
    id: { type: 'string', optional: false },
    event_id: { type: 'string', optional: false },
    question: { type: 'string', optional: false },
    status: { type: 'string', optional: false },
    topic: { type: 'string', optional: true },
    created_at: { type: 'string', optional: false },
    updated_at: { type: 'string', optional: true },
    title: { type: 'string|null', optional: false },
    title_cn: { type: 'string|null', optional: false },
    source_id: { type: 'string', optional: false },
    url: { type: 'string|null', optional: false },
    answered_event_ids: { type: 'string|null', optional: false },
  });
  assert.match(page, /interface BrainstormDetailPageProps\s*\{[\s\S]*embedded\?: boolean;[\s\S]*questionId\?: string;[\s\S]*onQuestionChange\?: \(question: BrainstormQuestion\) => void;[\s\S]*embeddedActions\?: React\.ReactNode;/);
  assert.match(page, /const id = questionId \|\| routeId/);
  assert.match(page, /onQuestionChange\?\.\(/);
});

test('brainstorm requests preserve endpoints methods refreshes and concepts', () => {
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}`/);
  assert.match(implementation, /apiFetch\('\/api\/events\?source_id=douyin&limit=50'/);
  assert.match(implementation, /apiFetch\('\/api\/events\?source_id=user-upload&limit=50'/);
  assert.match(implementation, /apiFetch\('\/api\/events\?content_type=concept&limit=100'/);
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}\/conversation`/);
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}\/concepts`/);
  assert.match(implementation, /apiFetch\('\/api\/brainstorm\/concepts\/precipitate', \{[\s\S]{0,100}method: 'POST'/);
  for (const endpoint of ['contemplate', 'answer']) {
    assert.match(implementation, new RegExp(`apiFetch\\('/api/brainstorm/${endpoint}'[\\s\\S]{0,100}method: 'POST'`));
  }
  for (const endpoint of ['start', 'message', 'summary']) {
    assert.match(implementation, new RegExp(`apiFetch\\(\\\`/api/brainstorm/\\$\\{id\\}/conversation/${endpoint}\\\`[\\s\\S]{0,100}method: 'POST'`));
  }
  assert.match(implementation, /setSummaryConcepts\(data\.concepts \|\| \[\]\)/);
});

test('every cancellable brainstorm request forwards its real owner signal', () => {
  const calls = [];
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(hookModule.sourceFile) === 'apiFetch') calls.push(node);
    ts.forEachChild(node, visit);
  }
  visit(hookModule.sourceFile);
  assert.equal(calls.length, 14, 'all brainstorm requests must remain covered by the signal contract');
  for (const call of calls) {
    const endpoint = call.arguments[0]?.getText(hookModule.sourceFile);
    const options = call.arguments[1];
    assert.ok(options && ts.isObjectLiteralExpression(options), `${endpoint} must pass apiFetch options`);
    const signal = options.properties.find((property) => (
      ts.isPropertyAssignment(property) && property.name.getText(hookModule.sourceFile) === 'signal'
    ));
    assert.ok(signal && ts.isPropertyAssignment(signal), `${endpoint} must pass options.signal`);
    assert.equal(signal.initializer.getText(hookModule.sourceFile), 'owner.signal', `${endpoint} must use its owner signal`);
  }
});

test('writes stay mutually exclusive while concept mutation cancels only stale reads', () => {
  const { createOperationGroup, createOperationLifecycle } = loadPureDeclarations(
    modules,
    ['createOperationGroup', 'createOperationLifecycle'],
    { RequestLifecycle, isLatestRequest },
  );
  const loading = { start: false, followUp: false, concepts: false, precipitate: false };
  const start = createOperationLifecycle('conversationStart', (value) => { loading.start = value; });
  const followUp = createOperationLifecycle('followUp', (value) => { loading.followUp = value; });
  const startOwner = start.start();
  assert.equal(startOwner.signal.aborted, false, 'an active POST must retain ownership until it completes');
  assert.equal(followUp.isActive(), false, 'the blocked writer must never be started');
  assert.deepEqual(loading, { start: true, followUp: false, concepts: false, precipitate: false });
  start.finish(startOwner);
  const followUpOwner = followUp.start();
  assert.equal(followUpOwner.signal.aborted, false);
  followUp.finish(followUpOwner);

  const conceptGroup = createOperationGroup();
  const concepts = createOperationLifecycle('conceptLoad', (value) => { loading.concepts = value; }, conceptGroup);
  const precipitate = createOperationLifecycle('conceptPrecipitate', (value) => { loading.precipitate = value; }, conceptGroup);
  const conceptOwner = concepts.start();
  const precipitateOwner = precipitate.start();
  assert.equal(conceptOwner.signal.aborted, true, 'concept mutation must abort the previous concept GET');
  concepts.finish(conceptOwner);
  assert.deepEqual(loading, { start: false, followUp: false, concepts: false, precipitate: true });
  precipitate.finish(precipitateOwner);

  assert.match(hook, /conversationStart: createOperationLifecycle\('conversationStart', setConversationLoading\)/);
  assert.match(hook, /followUp: createOperationLifecycle\('followUp', setFollowUpLoading\)/);
  assert.match(hook, /conversationLoad: createOperationLifecycle\('conversationLoad'/);
  assert.match(hook, /function startConversation[\s\S]{0,300}conversationStart\.isActive\(\)[\s\S]{0,100}followUp\.isActive\(\)[\s\S]{0,180}conversationLoad\.abort\(\)/);
  assert.match(hook, /function sendFollowUp[\s\S]{0,300}conversationStart\.isActive\(\)[\s\S]{0,100}followUp\.isActive\(\)[\s\S]{0,180}conversationLoad\.abort\(\)/);
  assert.match(hook, /actionOwner\('conversationLoad'\)[\s\S]{0,500}\/conversation`, \{ signal: owner\.signal \}/);
  assert.match(hook, /const conceptGroup = createOperationGroup\(\)/);
  assert.match(hook, /conceptLoad: createOperationLifecycle\('conceptLoad',[\s\S]{0,100}conceptGroup\)/);
  assert.match(hook, /conceptPrecipitate: createOperationLifecycle\('conceptPrecipitate',[\s\S]{0,140}conceptGroup/);
  assert.match(hook, /function loadConcepts[\s\S]{0,180}conceptPrecipitate\.isActive\(\)/);
  assert.match(hook, /function precipitateConcept[\s\S]{0,220}conceptPrecipitate\.isActive\(\)/);
});

test('failed follow-up restores input removes optimism and reports only on the current page', () => {
  const { recoverFailedFollowUp } = loadPureDeclarations(modules, ['recoverFailedFollowUp']);
  const messages = [
    { id: 1, content: 'existing' },
    { id: -2, content: 'pending' },
  ];
  for (const reason of [new Error('发送失败'), new TypeError('network down'), new Error('业务失败')]) {
    assert.deepEqual(recoverFailedFollowUp(messages, -2, '保留我的追问', reason), {
      messages: [{ id: 1, content: 'existing' }],
      text: '保留我的追问',
      error: reason.message,
    });
  }
  assert.equal(recoverFailedFollowUp(messages, -2, '不要污染新页面', new DOMException('Aborted', 'AbortError')), null);
  assert.match(hook, /if \(!response\.ok\) throw new Error\('发送失败'\)/);
  assert.match(hook, /if \(data\.error\) throw new Error\(data\.error\)/);
  assert.match(hook, /actionIsCurrent\('followUp', owner\)[\s\S]{0,260}recoverFailedFollowUp/);
  assert.match(hook, /recoverFailedFollowUp[\s\S]{0,500}setFollowUpText\(failure\.text\)[\s\S]{0,160}setContemplateError\(failure\.error\)/);
  assert.match(hook, /setFollowUpText\(''\)[\s\S]{0,600}setSummaryUpdated\(true\)/);
  assert.match(hook, /await reloadConversation\('followUp', owner\)/);
  assert.match(conversationPanel, /error: string;/);
  assert.match(conversationPanel, /props\.error &&[\s\S]{0,180}text-red-400/);
  assert.match(conversationPanel, /props\.error &&[\s\S]{0,180}text-red-400[\s\S]{0,100}\{props\.messages\.length > 0 &&/);
});

test('brainstorm source labels reference rendering visible labels and css hooks can move together', () => {
  const { sourceLabel } = loadPureDeclarations(modules, ['sourceLabel']);
  assert.equal(sourceLabel('douyin'), '抖音');
  assert.equal(sourceLabel('user-upload'), '上传');
  assert.equal(sourceLabel('user-concept'), '概念');
  assert.equal(sourceLabel('rss'), 'rss');
  assert.match(implementation, /function renderMarkdownWithRefs\(content: string, lockedIds: string\[\]/);
  assert.match(implementation, /navigate\(`\/events\/\$\{eventId\}`\)/);
  for (const label of ['发起问答', '凝神静思', '对话', '参考文档', 'AI 深度总结', '返回对话']) {
    assert.match(implementation, new RegExp(label));
  }
  for (const hook of ['brainstorm-detail-embedded is-loading', 'brainstorm-detail-embedded is-error', 'brainstorm-detail-embedded is-ready', 'brainstorm-detail-header', 'brainstorm-detail-actions']) {
    assert.match(implementation, new RegExp(hook));
  }
  assert.match(page, /\{embeddedActions\}/);
});

test('brainstorm extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.2 must add useBrainstormDetail.ts');
  assert.equal(readFileSync(hookUrl, 'utf8'), hook);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));

  assert.ok(existsSync(answerPanelUrl), 'Task 5.2 must add BrainstormAnswerPanel.tsx');
  assert.ok(existsSync(conversationPanelUrl), 'Task 5.2 must add BrainstormConversationPanel.tsx');
  assert.match(page, /useBrainstormDetail\(\{[\s\S]{0,800}(?:questionId|id):/);
  assertForwardedCallbacks(pageModule, 'BrainstormAnswerPanel', {
    onGenerateSummary: 'generateSummary',
    onLoadConcepts: 'loadConcepts',
    onPrecipitateConcept: 'precipitateConcept',
    onReferenceClick: 'handleReferenceClick',
  });
  assertForwardedCallbacks(pageModule, 'BrainstormConversationPanel', {
    onStartConversation: 'startConversation',
    onSendFollowUp: 'sendFollowUp',
    onReferenceClick: 'handleReferenceClick',
  });
  assert.match(hook, /signal/);
  assert.match(hook, /isCurrent|sequence/);
  assert.doesNotMatch(hook, /onQuestionChange/);
});
