import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
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
const answerPanelUrl = new URL('./BrainstormAnswerPanel.tsx', import.meta.url);
const conversationPanelUrl = new URL('./BrainstormConversationPanel.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, hookUrl, answerPanelUrl, conversationPanelUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'BrainstormDetailPage.tsx');
assert.ok(pageModule);
const page = pageModule.source;

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
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}`\)/);
  assert.match(implementation, /apiFetch\('\/api\/events\?source_id=douyin&limit=50'\)/);
  assert.match(implementation, /apiFetch\('\/api\/events\?source_id=user-upload&limit=50'\)/);
  assert.match(implementation, /apiFetch\('\/api\/events\?content_type=concept&limit=100'\)/);
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}\/conversation`\)/);
  assert.match(implementation, /apiFetch\(`\/api\/brainstorm\/\$\{id\}\/concepts`\)/);
  assert.match(implementation, /apiFetch\('\/api\/brainstorm\/concepts\/precipitate', \{[\s\S]{0,100}method: 'POST'/);
  for (const endpoint of ['contemplate', 'answer']) {
    assert.match(implementation, new RegExp(`apiFetch\\('/api/brainstorm/${endpoint}'[\\s\\S]{0,100}method: 'POST'`));
  }
  for (const endpoint of ['start', 'message', 'summary']) {
    assert.match(implementation, new RegExp(`apiFetch\\(\\\`/api/brainstorm/\\$\\{id\\}/conversation/${endpoint}\\\`[\\s\\S]{0,100}method: 'POST'`));
  }
  assert.match(implementation, /setSummaryConcepts\(data\.concepts \|\| \[\]\)/);
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
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useBrainstormDetail.ts');
  assert.ok(hookModule);
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
