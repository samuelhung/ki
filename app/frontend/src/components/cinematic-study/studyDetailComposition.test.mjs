import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
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
const modules = readSourceModules([pageUrl, formatUrl, hookUrl, materialPanelUrl, lessonPanelUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'StudyDetail.tsx');
assert.ok(pageModule);
const page = pageModule.source;

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
  assert.match(implementation, /apiFetch\(`\/api\/study\/\$\{id\}`\)/);
  assert.match(implementation, /apiFetch\(`\/api\/study\/\$\{id\}\/generate`, \{ method: 'POST'/);
  assert.match(implementation, /apiFetch\(`\/api\/study\/\$\{id\}`, \{ method: 'DELETE' \}\)/);
  assert.match(implementation, /apiFetch\(`\/api\/study\/\$\{id\}\/review`, \{\s*method: 'POST'/);
  assert.match(implementation, /`\/api\/study\/\$\{id\}\/file\/\$\{format\}`/);
  assert.match(implementation, /apiFetch\(path\)/);
  assert.match(implementation, /if \(!active\) return;[\s\S]{0,120}setPreviewUrl\(objectUrl\)/);
  assert.match(implementation, /URL\.revokeObjectURL\(objectUrl\)/);
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
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useStudyDetail.ts');
  assert.ok(hookModule);
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
