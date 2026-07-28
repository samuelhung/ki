import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { escapeHtml, sanitizeHtml } from '../../safeHtml.ts';
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

const pageUrl = new URL('../../pages/StudyDetail.tsx', import.meta.url);
const formatUrl = new URL('./studyDetailFormat.tsx', import.meta.url);
const hookUrl = new URL('./useStudyDetail.ts', import.meta.url);
const materialPanelUrl = new URL('./StudyMaterialPanel.tsx', import.meta.url);
const lessonPanelUrl = new URL('./StudyLessonPanel.tsx', import.meta.url);
const workspaceUrl = new URL('./studyWorkspace.mjs', import.meta.url);
const cinematicStudyUrl = new URL('../../pages/CinematicStudy.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, formatUrl, hookUrl, materialPanelUrl, lessonPanelUrl, workspaceUrl, cinematicStudyUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'StudyDetail.tsx');
const hookModule = modules.find((module) => module.name === 'useStudyDetail.ts');
const cinematicStudyModule = modules.find((module) => module.name === 'CinematicStudy.tsx');
assert.ok(pageModule);
assert.ok(hookModule);
assert.ok(cinematicStudyModule);
const page = pageModule.source;
const hook = hookModule.source;

function callsNamed(module, name, root = module.sourceFile) {
  const calls = [];
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(module.sourceFile) === name) calls.push(node);
    ts.forEachChild(node, visit);
  }
  visit(root);
  return calls;
}

function functionNamed(module, name) {
  let match = null;
  function visit(node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === name) match = node;
    if (!match) ts.forEachChild(node, visit);
  }
  visit(module.sourceFile);
  assert.ok(match, `Expected function ${name}`);
  return match;
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

test('study detail preserves the exact exported material type and callbacks', () => {
  assertExportedObjectType(modules, 'StudyMaterial', {
    id: { type: 'string', optional: false },
    subject: { type: 'string', optional: false },
    grade: { type: 'string', optional: false },
    textbook: { type: 'string', optional: false },
    study_type: { type: 'string', optional: false },
    title: { type: 'string', optional: false },
    source_type: { type: 'string', optional: false },
    raw_content: { type: 'string', optional: false },
    child_version: { type: 'string', optional: false },
    parent_version: { type: 'string', optional: false },
    formats_json: { type: 'Record<string,string>', optional: false },
    lessons_json: { type: 'TextbookLesson[]', optional: false },
    status: { type: 'string', optional: false },
    score: { type: 'number|null', optional: false },
    is_correct: { type: 'number|null', optional: false },
    mistake_tags: { type: 'string[]', optional: false },
    created_at: { type: 'string', optional: false },
    updated_at: { type: 'string', optional: false },
    review_content: { type: 'string', optional: true },
  });
  assert.match(page, /const id = materialId \|\| routeId/);
  assert.match(implementation, /onMaterialChange\?\.\(/);
  assert.match(implementation, /onDeleted\?\.\(/);
});

test('study character markdown and unit helpers can move while preserving behavior', () => {
  const helpers = loadPureDeclarations(
    modules,
    ['parseChars', 'mdToHtml', 'UNIT_REGISTRY', 'resolveUnits'],
    { escapeHtml, sanitizeHtml },
  );
  assert.deepEqual(helpers.parseChars('zá:杂 lí:篱'), [{ py: 'zá', hz: '杂' }, { py: 'lí', hz: '篱' }]);
  assert.deepEqual(helpers.parseChars('   '), []);
  const registered = helpers.resolveUnits('统编四年级下册语文教材', []);
  assert.equal(registered.length, 8);
  assert.equal(registered[0].items[0].title, '古诗词三首');
  const fallback = helpers.resolveUnits('自定义教材', [{ lesson_num: 3, title: '分数', content: '', analysis_md: '' }]);
  assert.deepEqual(fallback, [{ unit_num: 1, theme: '', items: [{ type: '课文', title: '分数', lesson_num: 3 }] }]);
  const html = helpers.mdToHtml('## 标题\n- **重点**\n<script>alert(1)</script>');
  assert.match(html, /<h3 class="text-base font-bold/);
  assert.doesNotMatch(html, /<script>/);
});

test('study endpoints preserve generation review deletion and file preview lifecycle', () => {
  const calls = callsNamed(hookModule, 'apiFetch').map((call) => call.arguments.map((argument) => argument.getText(hookModule.sourceFile)));
  const includesCall = (endpoint, options) => calls.some(([actualEndpoint, actualOptions = '']) => (
    actualEndpoint === endpoint && (!options || options.test(actualOptions))
  ));
  assert.equal(includesCall('`/api/study/${id}`', /signal/), true);
  assert.equal(includesCall('`/api/study/${selectedId}/generate`', /method:\s*'POST'/), true);
  assert.equal(includesCall('`/api/study/${selectedId}`', /method:\s*'DELETE'/), true);
  assert.equal(includesCall('`/api/study/${selectedId}/review`', /method:\s*'POST'/), true);
  assert.equal(includesCall('path', /signal/), true);
  const templates = [];
  function collectTemplates(node) {
    if (ts.isTemplateExpression(node)) templates.push(node.getText(hookModule.sourceFile));
    ts.forEachChild(node, collectTemplates);
  }
  collectTemplates(hookModule.sourceFile);
  assert.ok(templates.includes('`/api/study/${id}/file/${format}`'));
});

test('study labels css hooks and format definitions can move together', () => {
  for (const label of ['MD', 'HTML', 'PDF', '原始PDF', '课文目录', '孩子版', '家长版', '错题复盘', '教材结构']) {
    assert.match(implementation, new RegExp(label));
  }
  for (const hook of ['study-detail-legacy-embedded is-loading', 'study-detail-legacy-embedded is-error', 'study-detail-legacy-embedded is-ready', 'study-detail-back', 'study-review-form', 'study-preview-frame']) {
    assert.match(implementation, new RegExp(hook));
  }
  assert.match(page, /embedded/);
});

test('study extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.5 must add useStudyDetail.ts');
  assert.equal(readFileSync(hookUrl, 'utf8'), hook);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));

  assert.ok(existsSync(formatUrl), 'Task 5.5 must add studyDetailFormat.tsx');
  assert.ok(existsSync(materialPanelUrl), 'Task 5.5 must add StudyMaterialPanel.tsx');
  assert.ok(existsSync(lessonPanelUrl), 'Task 5.5 must add StudyLessonPanel.tsx');
  const format = readFileSync(formatUrl, 'utf8');
  for (const helper of ['parseChars', 'mdToHtml', 'resolveUnits']) {
    assert.match(format, new RegExp(`export function ${helper}\\b`));
  }
  assert.match(format, /export const FORMATS\b/);
  assertForwardedCallbacks(pageModule, 'StudyMaterialPanel', {
    onGenerate: 'handleGenerate',
    onDelete: 'handleDelete',
    onReview: 'handleReview',
    onVersionChange: 'setVersion',
    onFormatChange: 'setFormat',
  });
  assertForwardedCallbacks(pageModule, 'StudyLessonPanel', {
    onToggleUnit: 'toggleUnit',
    onToggleLesson: 'toggleLesson',
  });
  assert.match(page, /useStudyDetail\(/);
  assert.match(hook, /signal/);
  assert.match(hook, /isCurrent|sequence/);
});

test('study material lock and selection ownership remain authoritative across A-B-A', () => {
  const { createSelectedStudyOwner, createActiveStudyActionRegistry } = loadPureDeclarations(
    modules,
    ['createSelectedStudyOwner', 'createActiveStudyActionRegistry'],
  );
  const owners = createSelectedStudyOwner();
  const staleMaterialA = owners.select('material-a');
  owners.invalidate(staleMaterialA);
  const materialB = owners.select('material-b');
  owners.invalidate(materialB);
  const currentMaterialA = owners.select('material-a');
  assert.equal(owners.isCurrent(staleMaterialA), false);
  assert.equal(owners.isCurrent(currentMaterialA), true);

  const actions = createActiveStudyActionRegistry();
  const generateA = actions.begin('generate', 'material-a');
  assert.equal(actions.isActive('generate', 'material-a'), true);
  assert.equal(actions.isLocked('material-a'), true);
  assert.equal(actions.begin('review', 'material-a'), null);
  assert.equal(actions.begin('delete', 'material-a'), null);
  assert.equal(actions.isActive('generate', 'material-b'), false);
  const reviewB = actions.begin('review', 'material-b');
  assert.notEqual(reviewB, null);
  actions.end(generateA);
  const deleteA = actions.begin('delete', 'material-a');
  assert.notEqual(deleteA, null);
  actions.end(deleteA);
  actions.end(reviewB);
  assert.equal(actions.isActive('generate', 'material-a'), false);

  assert.match(hook, /useSyncExternalStore\(activeActions\.subscribe, activeActions\.getSnapshot, activeActions\.getSnapshot\)/);
  assert.match(hook, /const mutationLocked = activeActions\.isLocked\(id\)/);
  const materialPanel = modules.find((module) => module.name === 'StudyMaterialPanel.tsx')?.source || '';
  assert.equal((materialPanel.match(/disabled=\{mutationLocked\}/g) || []).length, 2);
  assert.match(materialPanel, /disabled=\{mutationLocked \|\| !reviewForm\.child_answer/);
  for (const staleSetter of ['setGenerating', 'setDeleting', 'setReviewing']) {
    assert.doesNotMatch(hook, new RegExp(staleSetter));
  }
});

test('review commits only the authoritative refresh result', async () => {
  const commits = [];
  const coordinator = loadRequestCoordinatorFactory(hookModule)({
    onCommit: (value) => commits.push(value),
    onError: assert.fail,
  });
  const owner = coordinator.start('material-a');
  const staleSnapshot = { id: 'material-a', title: 'stale' };
  const authoritative = { id: 'material-a', title: 'authoritative', status: 'reviewed' };
  await coordinator.mutateAndRefresh({
    owner,
    selectedId: 'material-a',
    mutate: async () => staleSnapshot,
    refresh: async () => authoritative,
  });
  assert.deepEqual(commits, [authoritative]);

  const review = functionNamed(hookModule, 'handleReview');
  const reviewSource = review.getText(hookModule.sourceFile);
  assert.match(reviewSource, /coordinator\.mutateAndRefresh/);
  assert.doesNotMatch(reviewSource, /currentMaterial|\.\.\.result/);
  const reviewCalls = callsNamed(hookModule, 'apiFetch', review)
    .map((call) => call.arguments.map((argument) => argument.getText(hookModule.sourceFile)));
  assert.ok(reviewCalls.some(([endpoint, options]) => endpoint === '`/api/study/${selectedId}/review`' && /method:\s*'POST'/.test(options)));
  assert.ok(reviewCalls.some(([endpoint, options]) => endpoint === '`/api/study/${selectedId}`' && /signal/.test(options)));
});

test('successful mutation reconciles its original material across a POST-time A-B-A switch', async () => {
  const createRequestCoordinator = loadRequestCoordinatorFactory(hookModule);
  const { createMutationReconciler } = loadPureDeclarations(
    modules,
    ['createMutationReconciler'],
    { createRequestCoordinator },
  );
  const { createSelectedStudyOwner } = loadPureDeclarations(modules, ['createSelectedStudyOwner']);
  const owners = createSelectedStudyOwner();
  const selection = owners.select('material-a');
  const post = deferred();
  const parentCommits = [];
  const localCommits = [];
  let refreshes = 0;
  const viewCoordinator = createRequestCoordinator({ onCommit: assert.fail, onError: assert.fail });
  viewCoordinator.start('material-a');
  const coordinator = createMutationReconciler({
    isCurrent: () => owners.isCurrent(selection),
    onReconcile: (value) => parentCommits.push(value),
    onCurrentCommit: (value) => localCommits.push(value),
    onCurrentError: assert.fail,
  });
  const owner = coordinator.start('material-a');
  const authoritative = { id: 'material-a', title: 'authoritative' };
  const run = coordinator.mutateAndRefresh({
    owner,
    selectedId: 'material-a',
    mutate: () => post.promise,
    refresh: async () => { refreshes += 1; return authoritative; },
  });
  owners.invalidate(selection);
  const materialB = owners.select('material-b');
  owners.invalidate(materialB);
  owners.select('material-a');
  viewCoordinator.abort();
  assert.equal(owner.signal.aborted, false);
  post.resolve();
  await run;
  assert.equal(refreshes, 1);
  assert.deepEqual(parentCommits, [authoritative]);
  assert.deepEqual(localCommits, []);

  for (const handlerName of ['handleGenerate', 'handleReview']) {
    const source = functionNamed(hookModule, handlerName).getText(hookModule.sourceFile);
    assert.match(source, /createMutationReconciler/);
    assert.match(source, /onReconcile:\s*cacheMaterial/);
    assert.match(source, /selectedOwner\.isCurrent\(selection\)/);
  }
  assert.doesNotMatch(hook, /mutationCoordinatorsRef/);
});

test('stale delete uses the real parent eviction path without changing its selection', () => {
  const workspaceHelpers = loadPureDeclarations(modules, ['evictStudyItems', 'removeStudyItem']);
  const { finishStudyDelete, evictStudyItems, resolveStudyDeletionSelection } = loadPureDeclarations(
    modules,
    ['finishStudyDelete', 'evictStudyItems', 'resolveStudyDeletionSelection'],
    { removeStudyItem: workspaceHelpers.removeStudyItem },
  );
  let materials = [{ id: 'material-old' }, { id: 'material-a' }, { id: 'material-b' }];
  let mistakes = [{ id: 'material-old' }, { id: 'material-b' }];
  const cache = new Map(materials.map((item) => [item.id, item]));
  let selectedId = 'material-a';
  const navigations = [];
  const onMaterialEvicted = (id) => {
    materials = evictStudyItems(materials, id);
    mistakes = evictStudyItems(mistakes, id);
    cache.delete(id);
  };
  const onDeleted = (id) => {
    selectedId = resolveStudyDeletionSelection(materials, id);
    navigations.push(selectedId ? `/study/${selectedId}` : '/study');
  };
  finishStudyDelete('material-old', false, onMaterialEvicted, onDeleted, () => navigations.push('/study'));
  assert.deepEqual(materials.map((item) => item.id), ['material-a', 'material-b']);
  assert.deepEqual(mistakes.map((item) => item.id), ['material-b']);
  assert.equal(cache.has('material-old'), false);
  assert.equal(selectedId, 'material-a');
  assert.deepEqual(navigations, []);

  materials = [{ id: 'material-a' }, { id: 'material-current' }, { id: 'material-b' }];
  mistakes = [{ id: 'material-current' }];
  materials.forEach((item) => cache.set(item.id, item));
  selectedId = 'material-current';
  finishStudyDelete('material-current', true, onMaterialEvicted, onDeleted, () => {});
  assert.equal(selectedId, 'material-b');
  assert.deepEqual(navigations, ['/study/material-b']);
  assert.deepEqual(materials.map((item) => item.id), ['material-a', 'material-b']);
  assert.deepEqual(mistakes, []);
  assert.equal(cache.has('material-current'), false);

  const detailDelete = functionNamed(hookModule, 'handleDelete').getText(hookModule.sourceFile);
  assert.match(detailDelete, /finishStudyDelete\(selectedId, selectedOwner\.isCurrent\(selection\)/);
  const evicted = functionNamed(cinematicStudyModule, 'handleMaterialEvicted').getText(cinematicStudyModule.sourceFile);
  assert.match(evicted, /setMaterials|setMistakes/);
  assert.match(evicted, /detailCacheRef\.current\.delete/);
  assert.doesNotMatch(evicted, /setSelectedId|navigate/);
  const deleted = functionNamed(cinematicStudyModule, 'handleDeleted').getText(cinematicStudyModule.sourceFile);
  assert.match(deleted, /resolveStudyDeletionSelection/);
  assert.match(deleted, /setSelectedId|navigate/);
  assert.doesNotMatch(deleted, /setMaterials|setMistakes|detailCacheRef/);
  assertForwardedCallbacks(cinematicStudyModule, 'LegacyStudyDetail', {
    onMaterialEvicted: 'handleMaterialEvicted',
    onDeleted: 'handleDeleted',
  });
});

test('preview lifecycle clears before replacement and revokes every owned URL', () => {
  const { createPreviewUrlLifecycle } = loadPureDeclarations(modules, ['createPreviewUrlLifecycle']);
  const events = [];
  const lifecycle = createPreviewUrlLifecycle({
    createObjectUrl: (blob) => `blob:${blob}`,
    revokeObjectUrl: (url) => events.push(['revoke', url]),
    onChange: (url) => events.push(['state', url]),
  });
  const ownerA = lifecycle.start('material-a:pdf');
  assert.deepEqual(events, [['state', '']]);
  assert.equal(lifecycle.commit(ownerA, 'a'), 'blob:a');
  assert.deepEqual(events.at(-1), ['state', 'blob:a']);

  const ownerB = lifecycle.start('material-a:html');
  assert.deepEqual(events.slice(-2), [['state', ''], ['revoke', 'blob:a']]);
  assert.equal(lifecycle.isCurrent(ownerA), false);
  assert.equal(lifecycle.commit(ownerA, 'stale'), undefined);
  assert.equal(lifecycle.commit(ownerB, 'b'), 'blob:b');
  lifecycle.clear(ownerB);
  assert.deepEqual(events.slice(-2), [['state', ''], ['revoke', 'blob:b']]);
  assert.equal(lifecycle.isCurrent(ownerB), false);
  assert.equal(lifecycle.commit(ownerB, 'after-cleanup'), undefined);

  const ownerC = lifecycle.start('material-b:pdf');
  lifecycle.fail(ownerC);
  assert.deepEqual(events.at(-1), ['state', '']);
  assert.equal(lifecycle.isCurrent(ownerC), false);
  assert.equal(lifecycle.commit(ownerC, 'after-failure'), undefined);
});
