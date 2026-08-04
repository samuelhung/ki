import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { formatTimeBeijing } from '../../utils.ts';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const productionPage = readFileSync(new URL('../../pages/LegacyIngestShellPreview.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const dockItems = readFileSync(new URL('../../pages/globalDockItems.ts', import.meta.url), 'utf8');
const dockOverlay = readFileSync(new URL('../../pages/GlobalDockOverlay.tsx', import.meta.url), 'utf8');
const dockAccessOverlayUrl = new URL('../../pages/GlobalDockAccessOverlay.tsx', import.meta.url);
const dockQueueOverlayUrl = new URL('../../pages/GlobalDockQueueOverlay.tsx', import.meta.url);
const dockDiscoveryOverlayUrl = new URL('../../pages/GlobalDockDiscoveryOverlay.tsx', import.meta.url);
const dockConceptOverlayUrl = new URL('../../pages/GlobalDockConceptOverlay.tsx', import.meta.url);
const dockSourcesOverlayUrl = new URL('../../pages/GlobalDockSourcesOverlay.tsx', import.meta.url);
const dockEventsOverlayUrl = new URL('../../pages/GlobalDockEventsOverlay.tsx', import.meta.url);
const dockQuestionOverlayUrl = new URL('../../pages/GlobalDockQuestionOverlay.tsx', import.meta.url);
const dockTaskOverlayUrl = new URL('../../pages/GlobalDockTaskOverlay.tsx', import.meta.url);
const dockOverviewOverlayUrl = new URL('../../pages/GlobalDockOverviewOverlay.tsx', import.meta.url);
const dockWorkspaceFrameUrl = new URL('../../pages/GlobalDockWorkspaceFrame.tsx', import.meta.url);
const cinematicEventDetailUrl = new URL('../../pages/CinematicEventDetail.tsx', import.meta.url);
const eventDetailPageUrl = new URL('../../pages/EventDetailPage.tsx', import.meta.url);
const eventDetailHeaderUrl = new URL('../cinematic-ingest/EventDetailHeader.tsx', import.meta.url);
const eventDetailBodyUrl = new URL('../cinematic-ingest/EventDetailBody.tsx', import.meta.url);
const knowledgeGraphUrl = new URL('../../pages/KnowledgeGraph.tsx', import.meta.url);
const industryFlowUrl = new URL('../../pages/IndustryFlow.tsx', import.meta.url);
const digestUrl = new URL('../../pages/Digest.tsx', import.meta.url);
const magicBentoFrameUrl = new URL('./KiMagicBentoFrame.tsx', import.meta.url);
const pageCss = readFileSync(new URL('../../pages/DualNavigationDemo.css', import.meta.url), 'utf8');
const homeCss = readFileSync(new URL('../../pages/CinematicHome.css', import.meta.url), 'utf8');
const variants = readFileSync(new URL('../../pages/DualNavigationActionMenu.tsx', import.meta.url), 'utf8');
const gooeyNav = readFileSync(new URL('./GooeyNav.tsx', import.meta.url), 'utf8');
const gooeyCss = readFileSync(new URL('./GooeyNav.css', import.meta.url), 'utf8');
const dockQueueCss = readFileSync(new URL('../../pages/GlobalDockQueueOverlay.css', import.meta.url), 'utf8');
const dockPopupCss = [
  'GlobalDockWorkspaceFrame.css',
  'GlobalDockAccessOverlay.css',
  'GlobalDockFormOverlays.css',
  'GlobalDockEventsOverlay.css',
  'GlobalDockQueueOverlay.css',
  'GlobalDockDiscoveryOverlay.css',
  'GlobalDockSourcesOverlay.css',
  'GlobalDockOverviewOverlay.css',
].map((file) => readFileSync(new URL(`../../pages/${file}`, import.meta.url), 'utf8')).join('\n');

function cssBlockBody(source, marker) {
  const markerIndex = source.indexOf(marker);
  if (markerIndex < 0) throw new Error(`CSS marker not found: ${marker}`);

  const blockStart = source.indexOf('{', markerIndex + marker.length);
  if (blockStart < 0) throw new Error(`CSS block start not found: ${marker}`);

  let depth = 0;
  for (let index = blockStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(blockStart + 1, index);
    }
  }

  throw new Error(`CSS block is not closed: ${marker}`);
}

function normalizeCssSelector(selector) {
  return selector.trim().replace(/\s+/g, ' ').replace(/\s*([>+~])\s*/g, '$1');
}

function cssSelectors(selectorText) {
  return selectorText.split(',').map(normalizeCssSelector).filter(Boolean);
}

function cssRuleWithDeclarations(source, selector, declarations) {
  const normalizedSelector = normalizeCssSelector(selector);
  let selectorIndex = source.indexOf(selector);
  while (selectorIndex >= 0) {
    const previousRuleEnd = source.lastIndexOf('}', selectorIndex);
    const blockStart = source.indexOf('{', selectorIndex + selector.length);
    if (blockStart < 0) break;

    const selectorText = source.slice(previousRuleEnd + 1, blockStart);
    const blockEnd = source.indexOf('}', blockStart + 1);
    const body = source.slice(blockStart + 1, blockEnd);
    if (cssSelectors(selectorText).includes(normalizedSelector) && declarations.every((declaration) => declaration.test(body))) return body;

    selectorIndex = source.indexOf(selector, selectorIndex + selector.length);
  }

  throw new Error(`CSS rule with declarations not found: ${selector}`);
}

function cssSelectorsWithDeclaration(source, declaration) {
  const rules = [];
  const cssRule = /([^{}]+)\{([^{}]*)\}/g;
  let match;
  while ((match = cssRule.exec(source))) {
    if (declaration.test(match[2])) rules.push(...cssSelectors(match[1]));
  }
  return rules;
}

function tsObjectBlock(source, marker) {
  const markerIndex = source.indexOf(marker);
  if (markerIndex < 0) throw new Error(`TS object marker not found: ${marker}`);

  const blockStart = source.indexOf('{', markerIndex + marker.length);
  if (blockStart < 0) throw new Error(`TS object block start not found: ${marker}`);

  let depth = 0;
  let quote = '';
  let escaped = false;
  for (let index = blockStart; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = '';
      continue;
    }
    if (character === '\'' || character === '"' || character === '`') {
      quote = character;
      continue;
    }
    if (character === '{') depth += 1;
    if (character === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(blockStart + 1, index);
    }
  }

  throw new Error(`TS object block is not closed: ${marker}`);
}

function jsxDivBlock(source, marker) {
  const start = source.indexOf(marker);
  if (start < 0) throw new Error(`JSX div marker not found: ${marker}`);

  const divTag = /<\/?div\b[^>]*>/g;
  divTag.lastIndex = start;
  let depth = 0;
  let match;
  while ((match = divTag.exec(source))) {
    depth += match[0].startsWith('</') ? -1 : 1;
    if (depth === 0) return source.slice(start, divTag.lastIndex);
  }

  throw new Error(`JSX div is not closed: ${marker}`);
}

function jsxElementBlock(source, className) {
  const openingTag = new RegExp(`<([a-z][\\w-]*)\\b[^>]*\\bclassName="${className}"[^>]*>`).exec(source);
  if (!openingTag) throw new Error(`JSX element not found: ${className}`);

  const tagName = openingTag[1];
  const tag = new RegExp(`<\\/?${tagName}\\b[^>]*>`, 'g');
  tag.lastIndex = openingTag.index;
  let depth = 0;
  let match;
  while ((match = tag.exec(source))) {
    depth += match[0].startsWith('</') ? -1 : 1;
    if (depth === 0) return source.slice(openingTag.index, tag.lastIndex);
  }

  throw new Error(`JSX element is not closed: ${className}`);
}

test('production navigation shell keeps the top and bottom menus independent', () => {
  assert.match(productionPage, /<KiNavigationShell/);
  assert.match(shell, /<GooeyNav/);
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /activeIndex=.*DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /onActiveChange=.*DualNavigationActionMenu/);
});

test('production navigation shell keeps the approved gooey navigation parameters', () => {
  assert.match(shell, /particleCount=\{15\}/);
  assert.match(shell, /const GOOEY_PARTICLE_DISTANCES: \[number, number\] = \[90, 10\]/);
  assert.match(shell, /particleDistances=\{GOOEY_PARTICLE_DISTANCES\}/);
  assert.match(shell, /particleR=\{100\}/);
  assert.match(shell, /animationTime=\{600\}/);
  assert.match(shell, /timeVariance=\{300\}/);
});

test('the primary navigation exposes the formal chinese information architecture', () => {
  const items = shell.match(/const TOP_ITEMS:[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/label:/g) || []).length, 6);
  assert.doesNotMatch(items, /label: '首页'/);
  assert.match(items, /label: '内容采集', href: '\/ingest'[\s\S]*label: '专题系列', href: '\/series'[\s\S]*label: '头脑风暴', href: '\/brainstorm'[\s\S]*label: '产业链', href: '\/industry-chains'[\s\S]*label: '工具箱', href: '\/toolbox'[\s\S]*label: '系统中枢', href: '\/system'/);
  assert.doesNotMatch(items, /事件列表|信息源/);
  assert.doesNotMatch(items, /label: 'INGEST'/);
  assert.match(shell, /pathname\.startsWith\('\/brainstorm'\)/);
});

test('the global dock is consolidated into nine stable workspaces', () => {
  const items = dockItems.match(/export const GLOBAL_DOCK_ITEMS[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/key:/g) || []).length, 9);
  for (const key of ['overview', 'access', 'concept', 'sources', 'events', 'discovery', 'question', 'task', 'queue']) {
    assert.match(items, new RegExp(`key: '${key}'`));
  }
  assert.doesNotMatch(items, /key: 'douyin'|key: 'file'|key: 'global'|key: 'topic'|key: 'compose'/);
  assert.match(shell, /GLOBAL \/ 9/);
});

test('queue timestamps convert stored UTC values to Beijing time', () => {
  assert.equal(formatTimeBeijing('2026-08-03 09:56:03'), '2026/8/3 17:56:03');
});

test('queue overlay renders the full progress track with accessible current-stage focus', () => {
  const dockQueueOverlay = readFileSync(dockQueueOverlayUrl, 'utf8');
  const progressTrack = dockQueueOverlay.match(/function QueueProgressTrack[\s\S]*?\n}\n\nexport default/)?.[0] || '';

  assert.match(progressTrack, /const stages = queueProgressStages\(item\);/);
  assert.match(progressTrack, /const current = stages\.find\(\(stage\) => stage\.status === 'active' \|\| stage\.status === 'error'\);/);
  assert.match(progressTrack, /const isCurrent = current === stage;/);
  assert.match(progressTrack, /const trackRef = useRef<HTMLDivElement \| null>\(null\);/);
  assert.match(progressTrack, /ref=\{isCurrent \? currentStageRef : undefined\}/);
  assert.match(progressTrack, /const track = trackRef\.current;/);
  assert.match(progressTrack, /if \(!node \|\| !track \|\| !window\.matchMedia\('\(max-width: 760px\)'\)\.matches\) return;/);
  assert.match(progressTrack, /const trackRect = track\.getBoundingClientRect\(\);/);
  assert.match(progressTrack, /const nodeRect = node\.getBoundingClientRect\(\);/);
  assert.match(progressTrack, /Math\.max\(\s*0,[\s\S]*track\.scrollLeft[\s\S]*track\.clientWidth[\s\S]*\)/);
  assert.match(progressTrack, /track\.scrollTo\(\{\s*left,\s*behavior: 'smooth',?\s*\}\)/s);
  assert.doesNotMatch(progressTrack, /scrollIntoView/);
  assert.doesNotMatch(progressTrack, /track\.scrollTo\(\{[\s\S]*?top:/);
  assert.match(progressTrack, /}, \[current\?\.key, current\?\.status\]\);/);
  assert.match(progressTrack, /if \(stages\.length === 0\) return null;/);
  assert.match(progressTrack, /const currentLabel = current \? `\$\{current\.label\}，\$\{stageLabel\(current\.status\)\}` : '等待更新';/);
  assert.match(progressTrack, /className="global-dock-queue-progress"[\s\S]*ref=\{trackRef\}[\s\S]*aria-label=\{currentLabel\}[\s\S]*tabIndex=\{0\}[\s\S]*'--queue-progress-stage-count': stages\.length/s);
  assert.match(progressTrack, /stages\.map\(\(stage, index\) =>/);
  assert.match(progressTrack, /key=\{`\$\{stage\.key\}-\$\{index\}`\}/);
  assert.match(progressTrack, /className=\{`is-\$\{stage\.status\}\$\{isCurrent \? ' is-current' : ''\}`\}/);
  assert.match(progressTrack, /title=\{`\$\{label\} · \$\{statusLabel\}`\}/);
  assert.match(progressTrack, /aria-label=\{`\$\{label\}，\$\{statusLabel\}`\}/);
  assert.match(progressTrack, /<b>\{label\}<\/b>/);
  assert.match(progressTrack, /<small>\{statusLabel\}<\/small>/);

  const actionsStart = dockQueueOverlay.indexOf('<div className="global-dock-queue-actions">');
  const actionsEnd = dockQueueOverlay.indexOf('</div>', actionsStart);
  const progressTrackRender = dockQueueOverlay.indexOf('<QueueProgressTrack item={item} />');
  const articleEnd = dockQueueOverlay.indexOf('</article>', progressTrackRender);
  assert.ok(actionsStart >= 0 && actionsEnd >= 0 && progressTrackRender >= 0 && articleEnd >= 0);
  assert.ok(actionsEnd < progressTrackRender && progressTrackRender < articleEnd);
});

test('queue progress track keeps exact desktop and mobile geometry', () => {
  const desktopProgress = dockQueueCss.match(/\.global-dock-queue-progress \{[\s\S]*?\n\}/)?.[0] || '';
  const stage = dockQueueCss.match(/\.global-dock-queue-progress > div \{[\s\S]*?\n\}/)?.[0] || '';
  const stageText = dockQueueCss.match(/\.global-dock-queue-progress > div > (?:b|small),[\s\S]*?\n\}/)?.[0] || '';
  const mobileCss = cssBlockBody(dockQueueCss, '@media (max-width: 760px)');
  const mobileProgress = cssBlockBody(mobileCss, '.global-dock-queue-progress');

  assert.match(dockQueueCss, /\.global-dock-queue-stage \{\s*width:\s*min\(820px, calc\(100vw - 48px\)\);/);
  assert.match(desktopProgress, /grid-column:\s*2\s*\/\s*-1;/);
  assert.match(desktopProgress, /display:\s*grid;/);
  assert.match(desktopProgress, /width:\s*100%;/);
  assert.match(desktopProgress, /min-width:\s*0;/);
  assert.match(desktopProgress, /grid-template-columns:\s*repeat\(var\(--queue-progress-stage-count\),\s*minmax\(0,\s*1fr\)\);/);
  assert.match(desktopProgress, /gap:\s*6px;/);
  assert.match(desktopProgress, /padding-bottom:\s*13px;/);

  assert.match(stage, /display:\s*grid;/);
  assert.match(stage, /min-width:\s*0;/);
  assert.match(stage, /gap:\s*4px;/);
  assert.match(stage, /padding-top:\s*7px;/);
  assert.match(stage, /border-top:\s*2px solid rgba\(255, 255, 255, \.12\);/);
  assert.match(stageText, /overflow:\s*hidden;/);
  assert.match(stageText, /text-overflow:\s*ellipsis;/);
  assert.match(stageText, /white-space:\s*nowrap;/);
  assert.match(stageText, /letter-spacing:\s*0;/);
  assert.match(stageText, /font-size:\s*var\(--dock-font-micro\);/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div > b \{[\s\S]*?font-weight:\s*500;/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div > small \{[\s\S]*?color:\s*rgba\(255, 255, 255, \.28\);/);

  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-done \{\s*border-top-color:\s*#76e6b7;\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-active \{\s*border-top-color:\s*#74c7ff;\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-error \{\s*border-top-color:\s*#fb7185;\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-pending \{\s*border-top-color:\s*rgba\(255, 255, 255, \.28\);\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-done > b,[\s\S]*?\.global-dock-queue-progress > div\.is-done > small \{\s*color:\s*#76e6b7;\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-active > b,[\s\S]*?\.global-dock-queue-progress > div\.is-active > small \{\s*color:\s*#74c7ff;\s*\}/);
  assert.match(dockQueueCss, /\.global-dock-queue-progress > div\.is-error > b,[\s\S]*?\.global-dock-queue-progress > div\.is-error > small \{\s*color:\s*#fb7185;\s*\}/);

  assert.match(mobileCss, /\.global-dock-queue-stage \{\s*width:\s*calc\(100vw - 28px\);/);
  assert.match(mobileProgress, /display:\s*flex;/);
  assert.match(mobileProgress, /overflow-x:\s*auto;/);
  assert.match(mobileProgress, /overscroll-behavior-x:\s*contain;/);
  assert.match(mobileProgress, /scrollbar-width:\s*thin;/);
  assert.doesNotMatch(mobileProgress, /touch-action\s*:/);
  assert.match(mobileCss, /\.global-dock-queue-progress > div \{[\s\S]*?flex:\s*0 0 84px;/);
  assert.equal((dockQueueCss.match(/overflow-x\s*:/g) || []).length, 1);
  assert.doesNotMatch(dockQueueCss, /\.global-dock-queue-(?:backdrop|page|dialog|list|stage)(?: article)?[^{]*\{[^}]*overflow-x:/);
  assert.doesNotMatch(dockQueueCss, /font-size:\s*(?:[0-9]|10)px;/);
  assert.doesNotMatch(dockQueueCss, /letter-spacing:\s*-/);
});

test('queue task summary keeps title, lifecycle, runtime, time, and actions on one line', () => {
  const dockQueueOverlay = readFileSync(dockQueueOverlayUrl, 'utf8');
  const taskSummary = jsxDivBlock(dockQueueOverlay, '<div className="global-dock-queue-summary">');
  const task = jsxElementBlock(taskSummary, 'global-dock-queue-task');
  const message = jsxElementBlock(taskSummary, 'global-dock-queue-message');
  const state = jsxElementBlock(taskSummary, 'global-dock-queue-state');
  const statusLabels = tsObjectBlock(dockQueueOverlay, "const TASK_STATUS_LABELS: Record<QueueItem['status'], string> =");

  assert.match(dockQueueOverlay, /const TASK_STATUS_LABELS: Record<QueueItem\['status'\], string> = \{/);
  assert.match(statusLabels, /running:\s*'处理中'/);
  assert.match(statusLabels, /pending:\s*'等待处理'/);
  assert.match(statusLabels, /error:\s*'处理异常'/);
  assert.match(statusLabels, /done:\s*'处理完成'/);
  assert.match(dockQueueOverlay, /const taskMessage = item\.error \|\| TASK_STATUS_LABELS\[item\.status\];/);
  assert.match(taskSummary, /global-dock-queue-task[\s\S]*global-dock-queue-message[\s\S]*global-dock-queue-state[\s\S]*formatTimeBeijing\(item\.created_at\)[\s\S]*global-dock-queue-actions/);
  assert.match(task, /^<\w+\b(?=[^>]*className="global-dock-queue-task")(?=[^>]*title=\{title\})[^>]*>/);
  assert.match(task, /<b>\{title\}<\/b>/);
  assert.match(message, /^<\w+\b(?=[^>]*className="global-dock-queue-message")(?=[^>]*title=\{taskMessage\})[^>]*>/);
  assert.match(message, />\s*\{taskMessage\}\s*<\//);
  assert.match(state, />\s*\{status\.label\}\s*<\//);
});

test('queue task summary has stable desktop and compact geometry', () => {
  const desktopArticle = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-list article', [/grid-template-columns:\s*18px minmax\(0, 1fr\);/]);
  const summary = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-summary', [/display:\s*flex;/, /align-items:\s*center;/, /min-width:\s*0;/, /white-space:\s*nowrap;/]);
  const task = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-task', [/flex:\s*1 1 auto;/, /min-width:\s*0;/]);
  const message = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-message', [/flex:\s*0 0 auto;/, /max-width:\s*32%;/]);
  const messageEllipsis = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-message', [/overflow:\s*hidden;/, /text-overflow:\s*ellipsis;/]);
  const taskTitle = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-task b', [/display:\s*block;/, /overflow:\s*hidden;/, /text-overflow:\s*ellipsis;/, /white-space:\s*nowrap;/]);
  const state = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-state', [/flex:\s*0 0 auto;/]);
  const time = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-summary > em', [/flex:\s*0 0 auto;/]);
  const actions = cssRuleWithDeclarations(dockQueueCss, '.global-dock-queue-actions', [/flex:\s*0 0 auto;/]);
  const mobileCss = cssBlockBody(dockQueueCss, '@media (max-width: 760px)');
  const mobileArticle = cssRuleWithDeclarations(mobileCss, '.global-dock-queue-list article', [/grid-template-columns:\s*16px minmax\(0, 1fr\);/]);

  assert.match(desktopArticle, /grid-template-columns:\s*18px minmax\(0, 1fr\);/);
  assert.match(summary, /display:\s*flex;/);
  assert.match(summary, /align-items:\s*center;/);
  assert.match(summary, /min-width:\s*0;/);
  assert.match(summary, /white-space:\s*nowrap;/);
  assert.match(task, /flex:\s*1 1 auto;/);
  assert.match(task, /min-width:\s*0;/);
  assert.match(message, /flex:\s*0 0 auto;/);
  assert.match(message, /max-width:\s*32%;/);
  assert.match(messageEllipsis, /overflow:\s*hidden;/);
  assert.match(messageEllipsis, /text-overflow:\s*ellipsis;/);
  assert.match(taskTitle, /display:\s*block;/);
  assert.match(taskTitle, /overflow:\s*hidden;/);
  assert.match(taskTitle, /text-overflow:\s*ellipsis;/);
  assert.match(taskTitle, /white-space:\s*nowrap;/);
  assert.match(state, /flex:\s*0 0 auto;/);
  assert.match(time, /flex:\s*0 0 auto;/);
  assert.match(actions, /flex:\s*0 0 auto;/);

  assert.match(mobileArticle, /grid-template-columns:\s*16px minmax\(0, 1fr\);/);
  const desktopCss = dockQueueCss.slice(0, dockQueueCss.indexOf('@media (max-width: 760px)'));
  const hiddenMobileSelectors = cssSelectorsWithDeclaration(mobileCss, /display:\s*none(?:\s*!important)?\s*;/)
    .filter((selector) => selector.includes('.global-dock-queue-'))
    .sort();
  const hiddenDesktopSelectors = cssSelectorsWithDeclaration(desktopCss, /display:\s*none(?:\s*!important)?\s*;/);

  const timeSelector = normalizeCssSelector('.global-dock-queue-summary > em');
  assert.deepEqual(hiddenMobileSelectors, [timeSelector]);
  assert.equal(hiddenDesktopSelectors.includes(timeSelector), false);
});

test('dock workspaces are lazy loaded and preserve merged modes inside one overlay', () => {
  assert.match(shell, /lazy\(\(\) => import\('\.\/GlobalDockOverlay'\)\)/);
  assert.equal(existsSync(dockAccessOverlayUrl), true);
  assert.equal(existsSync(dockQueueOverlayUrl), true);
  assert.equal(existsSync(dockDiscoveryOverlayUrl), true);
  assert.equal(existsSync(magicBentoFrameUrl), true);
  const dockAccessOverlay = readFileSync(dockAccessOverlayUrl, 'utf8');
  const dockQueueOverlay = readFileSync(dockQueueOverlayUrl, 'utf8');
  const dockDiscoveryOverlay = readFileSync(dockDiscoveryOverlayUrl, 'utf8');
  const magicBentoFrame = readFileSync(magicBentoFrameUrl, 'utf8');
  assert.match(dockOverlay, /lazy\(\(\) => import\('\.\/GlobalDockAccessOverlay'\)\)/);
  assert.match(dockOverlay, /action\.key === 'access'/);
  assert.match(dockOverlay, /lazy\(\(\) => import\('\.\/GlobalDockQueueOverlay'\)\)/);
  assert.match(dockOverlay, /action\.key === 'queue'/);
  assert.match(dockOverlay, /lazy\(\(\) => import\('\.\/GlobalDockDiscoveryOverlay'\)\)/);
  assert.match(dockOverlay, /action\.key === 'discovery'/);
  assert.doesNotMatch(dockOverlay, /function AccessWorkspace/);
  assert.doesNotMatch(dockOverlay, /function QueueWorkspace/);
  assert.doesNotMatch(dockOverlay, /function DiscoveryWorkspace/);
  assert.match(dockAccessOverlay, /抖音分享/);
  assert.match(dockAccessOverlay, /文件上传/);
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/douyin'/);
  assert.match(dockAccessOverlay, /apiFetch\('\/api\/ingest\/file'/);
  assert.match(dockAccessOverlay, /<KiMagicBentoFrame/);
  assert.match(dockQueueOverlay, /<KiMagicBentoFrame/);
  assert.match(dockQueueOverlay, /useIngestQueue/);
  assert.match(dockQueueOverlay, /retryQueueTask/);
  assert.match(dockQueueOverlay, /deleteQueueTask/);
  assert.match(dockQueueOverlay, /queueStatusCounts\.done/);
  assert.match(dockQueueOverlay, /import \{ formatTimeBeijing \} from '\.\.\/utils';/);
  assert.match(dockQueueOverlay, /formatTimeBeijing\(item\.created_at\)/);
  assert.doesNotMatch(dockQueueOverlay, /item\.created_at\?\.slice\(0, 19\)/);
  assert.match(dockDiscoveryOverlay, /<KiMagicBentoFrame/);
  assert.match(dockDiscoveryOverlay, /buildStage2Payload/);
  assert.match(dockDiscoveryOverlay, /全局发现/);
  assert.match(dockDiscoveryOverlay, /主题发现/);
  assert.match(dockDiscoveryOverlay, /自由组题/);
  assert.match(dockDiscoveryOverlay, /apiFetch\('\/api\/ingest\/series\/discover\/stage1'/);
  assert.match(dockDiscoveryOverlay, /apiFetch\('\/api\/ingest\/series\/discover\/stage2'/);
  assert.match(dockDiscoveryOverlay, /apiFetch\('\/api\/ingest\/series\/discover\/by-topic'/);
  assert.match(dockDiscoveryOverlay, /apiFetch\('\/api\/events\?limit=80&offset=0&content_type=event'/);
  assert.match(dockDiscoveryOverlay, /apiFetch\('\/api\/ingest\/series'/);
  assert.match(magicBentoFrame, /particleCount=\{18\}/);
  assert.match(magicBentoFrame, /spotlightRadius=\{420\}/);
  assert.match(magicBentoFrame, /tiltMax=\{2\.5\}/);
  assert.match(magicBentoFrame, /magnetismStrength=\{0\.02\}/);
});

test('the remaining dock workspaces use independent bento overlays without losing business APIs', () => {
  const overlayFiles = [
    dockConceptOverlayUrl,
    dockSourcesOverlayUrl,
    dockEventsOverlayUrl,
    dockQuestionOverlayUrl,
    dockTaskOverlayUrl,
    dockWorkspaceFrameUrl,
  ];
  for (const file of overlayFiles) assert.equal(existsSync(file), true);

  const conceptOverlay = readFileSync(dockConceptOverlayUrl, 'utf8');
  const sourcesOverlay = readFileSync(dockSourcesOverlayUrl, 'utf8');
  const eventsOverlay = readFileSync(dockEventsOverlayUrl, 'utf8');
  const questionOverlay = readFileSync(dockQuestionOverlayUrl, 'utf8');
  const taskOverlay = readFileSync(dockTaskOverlayUrl, 'utf8');
  const workspaceFrame = readFileSync(dockWorkspaceFrameUrl, 'utf8');

  for (const [key, component] of [
    ['concept', 'GlobalDockConceptOverlay'],
    ['sources', 'GlobalDockSourcesOverlay'],
    ['events', 'GlobalDockEventsOverlay'],
    ['question', 'GlobalDockQuestionOverlay'],
    ['task', 'GlobalDockTaskOverlay'],
  ]) {
    assert.match(dockOverlay, new RegExp(`lazy\\(\\(\\) => import\\('\\.\\/${component}'\\)\\)`));
    assert.match(dockOverlay, new RegExp(`action\\.key === '${key}'`));
  }

  assert.doesNotMatch(dockOverlay, /function (ConceptWorkspace|SourcesWorkspace|EventsWorkspace|QuestionWorkspace|TaskWorkspace)/);
  assert.match(workspaceFrame, /<KiMagicBentoFrame/);
  assert.match(workspaceFrame, /data-bento-suspend/);
  assert.match(conceptOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(conceptOverlay, /apiFetch\('\/api\/ingest\/concept'/);
  assert.match(sourcesOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(sourcesOverlay, /apiFetch\('\/api\/sources'/);
  assert.match(sourcesOverlay, /apiFetch\(`\/api\/sources\/\$\{selected\.id\}\/toggle`/);
  assert.match(sourcesOverlay, /apiFetch\(`\/api\/sources\/\$\{id\}\/collect`/);
  assert.match(sourcesOverlay, /apiFetch\('\/api\/collect'/);
  assert.match(eventsOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(eventsOverlay, /apiFetch\(`\/api\/events\?\$\{params\}`/);
  assert.match(eventsOverlay, /apiFetch\(`\/api\/events\/\$\{selectedId\}`/);
  assert.match(eventsOverlay, /RequestLifecycle/);
  assert.match(questionOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(questionOverlay, /apiFetch\('\/api\/brainstorm'/);
  assert.match(taskOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(taskOverlay, /apiFetch\('\/api\/tasks'/);
});

test('today overview is an independent bento workspace backed by the legacy dashboard APIs', () => {
  assert.equal(existsSync(dockOverviewOverlayUrl), true);
  const overviewOverlay = readFileSync(dockOverviewOverlayUrl, 'utf8');
  assert.match(dockOverlay, /lazy\(\(\) => import\('\.\/GlobalDockOverviewOverlay'\)\)/);
  assert.match(dockOverlay, /action\.key === 'overview'/);
  assert.match(overviewOverlay, /<GlobalDockWorkspaceFrame/);
  assert.match(overviewOverlay, /size="wide"/);
  for (const endpoint of [
    '/api/dashboard/summary',
    '/api/events?offset=0&limit=5&count=1',
    '/api/usage/dashboard',
    '/api/dashboard/trend?days=84',
    '/api/tasks/stats',
    '/api/sources',
  ]) {
    assert.match(overviewOverlay, new RegExp(endpoint.replace(/[?]/g, '\\?')));
  }
  assert.match(overviewOverlay, /Promise\.allSettled/);
  assert.match(overviewOverlay, /data-bento-suspend/);
  assert.match(overviewOverlay, /Math\.round\(data\.usage\?\.today\.cache_hit_rate \|\| 0\)/);
});

test('all dock popups share the approved readable typography floor', () => {
  assert.match(pageCss, /\.global-dock-backdrop\s*\{[^}]*--dock-font-micro:\s*11px[^}]*--dock-font-meta:\s*12px[^}]*--dock-font-body:\s*13px[^}]*--dock-font-emphasis:\s*14px/s);
  assert.match(dockPopupCss, /\.global-dock-workspace-header h2\s*\{[^}]*font:\s*500 24px/s);
  assert.match(dockPopupCss, /var\(--dock-font-micro\)/);
  assert.match(dockPopupCss, /var\(--dock-font-meta\)/);
  assert.match(dockPopupCss, /var\(--dock-font-body\)/);
  assert.match(dockPopupCss, /var\(--dock-font-emphasis\)/);
  assert.match(dockPopupCss, /\.global-dock-overview dd\s*\{[^}]*font:\s*500 var\(--dock-font-body\)/s);
  assert.doesNotMatch(dockPopupCss, /(?:font-size|font):[^;}]*?(?<!\d)(?:7|8|9|10|11)px/);
});

test('standalone event detail uses the cinematic shell and preserves the legacy business surface', () => {
  assert.equal(existsSync(cinematicEventDetailUrl), true);
  const cinematicEventDetail = readFileSync(cinematicEventDetailUrl, 'utf8');
  const eventDetailPage = readFileSync(eventDetailPageUrl, 'utf8');
  const eventDetailImplementation = [eventDetailPageUrl, eventDetailHeaderUrl, eventDetailBodyUrl]
    .map((url) => readFileSync(url, 'utf8')).join('\n');
  assert.match(app, /const CinematicEventDetail = lazy/);
  assert.match(app, /path="events\/:id" element=\{<CinematicEventDetail \/>\}/);
  assert.match(cinematicEventDetail, /<CinematicTemplatePage/);
  assert.match(cinematicEventDetail, /<CinematicLaserWorkspace/);
  assert.match(cinematicEventDetail, /<EventDetailPage[^>]*embedded[^>]*eventId=\{id\}/);
  assert.match(eventDetailPage, /embedded\?: boolean/);
  assert.match(eventDetailPage, /eventId\?: string/);
  assert.match(app, /location\.pathname\.startsWith\('\/events\/'\)/);
  assert.match(curtain, /pathname\.startsWith\('\/events\/'\)/);
  for (const feature of ['转写原文', 'AI 总结', '关联问题', '产业分析', '添加待办']) {
    assert.match(eventDetailImplementation, new RegExp(feature));
  }
});

test('retired standalone surfaces are removed while brainstorm stays intact', () => {
  assert.equal(existsSync(knowledgeGraphUrl), false);
  assert.equal(existsSync(industryFlowUrl), false);
  assert.equal(existsSync(digestUrl), false);
  assert.doesNotMatch(app, /KnowledgeGraph|knowledge-graph/);
  assert.doesNotMatch(app, /IndustryFlow|industry-flow/);
  assert.doesNotMatch(app, /Digest/);
  assert.doesNotMatch(readFileSync(new URL('../../pages/CinematicIndustryChains.tsx', import.meta.url), 'utf8'), /navigate\('\/industry-flow'\)/);
  const seriesDetail = readFileSync(new URL('../../pages/SeriesDetail.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(seriesDetail, /SeriesKnowledgeNetwork|tab === 'knowledge'|setTab\('knowledge'\)/);
  assert.match(app, /path="brainstorm" element=\{<CinematicBrainstorm \/>\}/);
  assert.match(app, /path="brainstorm\/:id" element=\{<CinematicBrainstorm \/>\}/);
  assert.match(dockItems, /key: 'question'/);
});

test('the enlarged cinematic brand replaces home and navigates to the dashboard', () => {
  assert.match(shell, /className="dual-nav-demo__brand"[^>]*onClick=\{\(\) => navigate\('\/'\)\}/);
  assert.match(shell, /<span className="dual-nav-demo__brand-title">知几<\/span>/);
  assert.match(shell, /import TextType from/);
  assert.match(shell, /dual-nav-demo__brand-star-track[^>]*><i \/><\/span>/);
  assert.match(shell, /<TextType[\s\S]*className="dual-nav-demo__brand-tagline"[\s\S]*text="其神乎 见微知著"[\s\S]*showCursor=\{false\}/);
  assert.match(pageCss, /\.dual-nav-demo__brand-title\s*\{[^}]*font-size:\s*60px/s);
  assert.match(pageCss, /\.dual-nav-demo__brand-tagline\s*\{[^}]*color:\s*#fff[^}]*font-size:\s*12px[^}]*font-style:\s*normal/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__brand-title:(?:before|after)/);
  assert.match(pageCss, /\.dual-nav-demo__brand-star-track i\s*\{[^}]*animation:\s*dual-nav-brand-star-travel 4\.5s/s);
  assert.match(pageCss, /@keyframes dual-nav-brand-star-travel/);
  assert.match(pageCss, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.dual-nav-demo__brand-star-track i\s*\{[^}]*animation:\s*none/s);
  assert.match(pageCss, /\.dual-nav-demo__primary\s*\{[^}]*display:\s*flex[^}]*gap:\s*clamp\(20px,\s*2vw,\s*36px\)/s);
});

test('top brand and search align to the ingest workspace edges', () => {
  assert.match(pageCss, /\.dual-nav-demo__top\s*\{[^}]*width:\s*min\(1536px,[^}]*transform:\s*translateX\(calc\(-50% \+ var\(--ki-center-shift\)\)\)/s);
  assert.match(pageCss, /\.dual-nav-demo__primary\s*\{[^}]*position:\s*absolute[^}]*left:\s*calc\(14\.44% - 18px\)/s);
  assert.match(pageCss, /\.dual-nav-demo__top-accessory\s*\{[^}]*position:\s*absolute[^}]*right:\s*0/s);
});

test('top workspace and dock share the viewport center axis', () => {
  assert.match(pageCss, /\.dual-nav-demo\s*\{[^}]*--ki-center-shift:\s*clamp\(-102px,\s*calc\(-5vw - 7px\),\s*-79px\)/s);
  assert.match(pageCss, /\.dual-nav-demo__top\s*\{[^}]*transform:\s*translateX\(calc\(-50% \+ var\(--ki-center-shift\)\)\)/s);
  assert.match(pageCss, /\.ki-shell-content\s*\{[^}]*transform:\s*translateX\(var\(--ki-center-shift\)\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock\s*\{[^}]*inset:\s*auto 50%[^}]*transform:\s*translateX\(-50%\)/s);
});

test('gooey nav prevents route changes and cleans up particle timers', () => {
  assert.match(gooeyNav, /event\.preventDefault\(\)/);
  assert.match(gooeyNav, /timerIdsRef/);
  assert.match(gooeyNav, /window\.clearTimeout/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--start-x'/);
  assert.match(gooeyNav, /particle\.style\.setProperty\('--time'/);
  assert.match(gooeyNav, /useEffect\(\(\) => \{[\s\S]*if \(filterRef\.current\) makeParticlesRef\.current\(filterRef\.current\)/);
});

test('top navigation lets the gooey particles start before route navigation unmounts them', () => {
  assert.match(gooeyNav, /navigationDelay\?: number/);
  assert.match(gooeyNav, /setPendingActiveIndex\(index\)/);
  assert.match(gooeyNav, /window\.setTimeout\(\(\) => onNavigate\?\.\(items\[index\], index\), navigationDelay\)/);
  assert.match(shell, /navigationDelay=\{480\}/);
});

test('gooey nav replaces the browser focus outline with its own item focus style', () => {
  assert.match(gooeyCss, /\.gooey-nav a:focus\s*\{[^}]*outline:\s*none/);
  assert.match(gooeyCss, /focus-within:has\(:focus-visible\)/);
});

test('the full bento study uses the supplied GSAP Magic Bento interaction kernel', () => {
  const sourceUrl = new URL('./KiMagicBento.tsx', import.meta.url);
  const cssUrl = new URL('./KiMagicBento.css', import.meta.url);
  assert.equal(existsSync(sourceUrl), true);
  assert.equal(existsSync(cssUrl), true);
  const source = readFileSync(sourceUrl, 'utf8');
  const css = readFileSync(cssUrl, 'utf8');
  const magicBentoFrame = readFileSync(magicBentoFrameUrl, 'utf8');
  assert.match(source, /import \{ gsap \} from 'gsap'/);
  assert.match(source, /const DEFAULT_PARTICLE_COUNT = 12/);
  assert.match(source, /const DEFAULT_SPOTLIGHT_RADIUS = 300/);
  assert.match(source, /width: 800px/);
  assert.match(source, /const DEFAULT_TILT_MAX = 10/);
  assert.match(source, /const DEFAULT_MAGNETISM_STRENGTH = 0\.05/);
  assert.match(source, /\* -config\.tiltMax/);
  assert.match(source, /\* config\.tiltMax/);
  assert.match(source, /\* config\.magnetismStrength/);
  assert.match(source, /tiltMax\?: number/);
  assert.match(source, /magnetismStrength\?: number/);
  assert.match(source, /suspendSelector\?: string/);
  assert.match(source, /back\.out\(1\.7\)/);
  assert.match(source, /power2\.inOut/);
  assert.match(source, /if \(!isHoveredRef\.current\)[\s\S]*animateParticles\(\)/);
  assert.match(source, /document\.addEventListener\('pointermove', handleDocumentPointerMove/);
  assert.match(source, /duration: 0\.8/);
  assert.match(source, /calculateSpotlightValues/);
  assert.match(source, /requestAnimationFrame/);
  assert.match(source, /gsap\.quickTo/);
  assert.match(source, /gsap\.killTweensOf\(particle\)/);
  assert.match(source, /visibilitychange/);
  assert.match(source, /prefers-reduced-motion: reduce/);
  assert.match(source, /pointer: coarse/);
  assert.match(css, /\.ki-magic-bento-card--border-glow::after/);
  assert.match(css, /padding:\s*6px/);
  assert.doesNotMatch(css, /transition:\s*all/);
  assert.match(magicBentoFrame, /<MagicBentoGrid/);
  assert.equal((magicBentoFrame.match(/<MagicBentoCard/g) || []).length, 1);
  assert.match(magicBentoFrame, /particleCount=\{18\}/);
  assert.match(magicBentoFrame, /spotlightRadius=\{420\}/);
  assert.match(magicBentoFrame, /tiltMax=\{2\.5\}/);
  assert.match(magicBentoFrame, /magnetismStrength=\{0\.02\}/);
  assert.match(magicBentoFrame, /suspendSelector="input, textarea, select, \[data-bento-suspend\]"/);
  assert.match(magicBentoFrame, /enableTilt/);
  assert.match(magicBentoFrame, /enableMagnetism/);
});

test('top navigation uses the reduced viewport inset', () => {
  assert.match(pageCss, /top:\s*clamp\(48px,\s*4vh,\s*64px\)/);
  assert.match(pageCss, /top:\s*46px/);
});

test('dual navigation reuses the reduced cinematic Three.js background', () => {
  assert.match(app, /CinematicBackdropProvider/);
  assert.match(shell, /useCinematicBackdrop/);
  assert.match(shell, /sceneVariant = 'ingest'/);
  assert.match(shell, /laserPrimary = true/);
  assert.match(shell, /setBackdrop\(\{[\s\S]*variant: sceneVariant,[\s\S]*laserPrimary,[\s\S]*focus: 0/);
  assert.doesNotMatch(shell, /<CinematicScene/);
  assert.match(shell, /sceneVariant === 'today' \? 'cinematic-film' : 'dual-nav-demo__film'/);
  assert.match(pageCss, /\.cinematic-backdrop-host > \.cinematic-scene-canvas/);
  assert.match(pageCss, /\.cinematic-backdrop-host\s*\{[^}]*z-index:\s*1/s);
  assert.match(pageCss, /\.dual-nav-demo__film\s*\{[^}]*z-index:\s*2/s);
  assert.match(shell, /is-\$\{sceneVariant\}-backdrop-active/);
  assert.match(pageCss, /\.cinematic-backdrop-host\.is-ingest-backdrop-active > \.cinematic-scene-canvas\s*\{[^}]*opacity:\s*1[^}]*brightness\(1\.16\)/s);
  assert.match(pageCss, /\.ki-shell-ingest-preview \.dual-nav-demo__reveal\s*\{[^}]*radial-gradient[^}]*backdrop-filter:\s*none/s);
  assert.match(pageCss, /\.ki-shell-ingest-preview \.dual-nav-demo__film\s*\{[^}]*mask-image:\s*none/s);
  assert.match(pageCss, /\.dual-nav-demo__film/);
});

test('film layer reveals the live scene around the pointer', () => {
  assert.match(shell, /style\.setProperty\('--reveal-x'/);
  assert.match(shell, /style\.setProperty\('--reveal-y'/);
  assert.match(shell, /'--reveal-x', '-9999px'/);
  assert.match(shell, /addEventListener\('pointermove', handlePointerMove, \{ passive: true \}\)/);
  assert.match(shell, /addEventListener\('pointerleave', handlePointerLeave\)/);
  assert.match(shell, /removeEventListener\('pointermove', handlePointerMove\)/);
  assert.doesNotMatch(shell, /onPointerMove=/);
  assert.match(pageCss, /radial-gradient\(\s*circle at var\(--reveal-x\) var\(--reveal-y\)/);
  assert.match(pageCss, /-webkit-mask-image:/);
  assert.match(pageCss, /mask-image:/);
});

test('pointer reveal locally brightens the existing scene without another canvas', () => {
  assert.match(shell, /className="dual-nav-demo__reveal"/);
  assert.match(pageCss, /\.dual-nav-demo__reveal/);
  assert.match(pageCss, /-webkit-backdrop-filter:\s*brightness\(2\.6\)/);
  assert.match(pageCss, /backdrop-filter:\s*brightness\(2\.6\)/);
  assert.doesNotMatch(shell, /<canvas/);
});

test('gooey navigation portals the original filter outside transformed navigation ancestors', () => {
  const filter = gooeyCss.match(/\.gooey-nav__filter\s*\{([^}]*)\}/s)?.[1] || '';
  assert.match(gooeyNav, /import \{ createPortal \} from 'react-dom'/);
  assert.match(gooeyNav, /closest\('main'\)/);
  assert.match(gooeyNav, /const hostRect = effectHost\.getBoundingClientRect\(\)/);
  assert.match(gooeyNav, /left: `\$\{itemRect\.left - hostRect\.left\}px`/);
  assert.match(gooeyNav, /createPortal\([\s\S]*effectHost/);
  assert.match(filter, /filter:\s*blur\(7px\) contrast\(100\) blur\(0\)/);
  assert.match(filter, /mix-blend-mode:\s*lighten/);
  assert.match(gooeyCss, /\.gooey-nav__filter::before\s*\{[^}]*inset:\s*-75px[^}]*background:\s*#000/s);
  assert.match(gooeyCss, /--gooey-color-1:[^;]+;[\s\S]*--gooey-color-4:/);
  assert.doesNotMatch(gooeyNav, /<feGaussianBlur|<feColorMatrix|<feBlend/);
});

test('gooey particles keep the original pill and particle timing', () => {
  assert.match(gooeyCss, /animation:\s*gooey-nav-pill \.3s ease both/);
  assert.match(gooeyCss, /@keyframes gooey-nav-pill\s*\{[\s\S]*to\s*\{\s*opacity:\s*1;/);
});

test('home backdrop uses opacity reveal instead of a full-canvas css filter', () => {
  const activeCanvas = pageCss.match(/\.cinematic-backdrop-host\.is-home-active > \.cinematic-scene-canvas\s*\{([^}]*)\}/s)?.[1] || '';
  const lightKeyframes = homeCss.match(/@keyframes cinematic-home-backdrop-light\s*\{([\s\S]*?)\n\}/)?.[1] || '';
  assert.match(activeCanvas, /filter:\s*none/);
  assert.match(activeCanvas, /animation:\s*cinematic-home-backdrop-light 1s/);
  assert.match(lightKeyframes, /opacity:/);
  assert.doesNotMatch(lightKeyframes, /filter:/);
});

test('ingest pointer reveal uses a lightweight radial glow instead of backdrop filtering', () => {
  const ingestReveal = pageCss.match(/\.ki-shell-ingest-preview \.dual-nav-demo__reveal\s*\{([^}]*)\}/s)?.[1] || '';
  assert.match(ingestReveal, /radial-gradient/);
  assert.match(ingestReveal, /backdrop-filter:\s*none/);
  assert.match(ingestReveal, /mask-image:\s*none/);
  assert.doesNotMatch(ingestReveal, /mix-blend-mode/);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*translate3d/s);
});

test('dual navigation uses one fixed nine-item semantic dock', () => {
  const items = dockItems.match(/export const GLOBAL_DOCK_ITEMS[^=]+= \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal((items.match(/text:/g) || []).length, 9);
  assert.match(items, /key: 'overview'/);
  assert.match(items, /key: 'queue'/);
  assert.match(pageCss, /\.dual-nav-action-menu\s*\{[^}]*grid-template-columns:\s*repeat\(9,\s*minmax\(0,\s*1fr\)\)/s);
  assert.doesNotMatch(items, /key: 'study'/);
  assert.match(shell, /DOCK \/ LOCKED/);
  assert.doesNotMatch(shell, /LOOP 2\.7/);
});

test('pointer reveal coalesces updates and bounds the filtered area', () => {
  assert.match(shell, /requestAnimationFrame/);
  assert.match(shell, /cancelAnimationFrame/);
  assert.match(shell, /revealFrameRef/);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*width:\s*560px/s);
  assert.match(pageCss, /\.dual-nav-demo__reveal\s*\{[^}]*height:\s*560px/s);
  assert.match(pageCss, /transform:\s*translate3d\(/);
  assert.match(pageCss, /circle at center/);
  assert.match(shell, /matchMedia\('\(pointer: fine\)'\)/);
  assert.match(shell, /matchMedia\('\(prefers-reduced-motion: reduce\)'\)/);
});

test('production shell exposes nine consolidated global workspaces in the dock', () => {
  for (const label of ['今日总览', '内容接入', '概念沉淀', '信息源', '事件列表', '专题发现', '新建问题', '新建任务', '处理队列']) {
    assert.match(dockItems, new RegExp(`text: '${label}'`));
  }
  assert.match(shell, /onSelect=\{handleActionSelect\}/);
  assert.match(shell, /GlobalDockOverlay/);
  assert.match(readFileSync(dockWorkspaceFrameUrl, 'utf8'), /role="dialog"/);
});

test('production shell keeps only the selected curved semantic dock', () => {
  assert.match(shell, /<DualNavigationActionMenu/);
  assert.doesNotMatch(shell, /ACTION_MENU_VARIANTS|actionMenuVariant|setActionMenuVariant/);
  assert.doesNotMatch(variants, /ActionMenuVariant|variant ===|--spotlight/);
  assert.doesNotMatch(pageCss, /is-spotlight|is-reel|dual-nav-variant-switcher/);
});

test('dock keeps semantic labels icons colors and modal actions in one data source', () => {
  assert.match(variants, /item\.icon/);
  assert.match(variants, /item\.text/);
  assert.match(variants, /onSelect\(item\)/);
  assert.match(variants, /--action-accent/);
  assert.match(variants, /aria-label=\{item\.text\}/);
  assert.match(dockItems, /code: 'CONTENT UPLINK'/);
  assert.match(readFileSync(dockWorkspaceFrameUrl, 'utf8'), /action\.description/);
  assert.doesNotMatch(shell, /ACTION_META/);
});

test('semantic dock is memoized while the shell keeps a stable selection callback', () => {
  assert.match(variants, /export default memo\(DualNavigationActionMenu\)/);
  assert.match(shell, /const handleActionSelect = useCallback/);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock/);
  assert.match(pageCss, /prefers-reduced-motion/);
});

test('semantic dock follows a shallow circular gallery arc without losing hover focus', () => {
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock \.dual-nav-action-item\s*\{[^}]*translateY\(calc\(var\(--action-distance\) \* 4px\)\)[^}]*rotateZ\(calc\(var\(--action-offset\) \* \.8deg\)\)[^}]*scale\(calc\(1 - var\(--action-distance\) \* \.018\)\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock \.dual-nav-action-item:hover\s*\{[^}]*translateY\(calc\(var\(--action-distance\) \* 4px - 10px\)\)[^}]*scale\(1\.16\)/s);
  assert.match(pageCss, /\.dual-nav-action-menu\.is-dock::before\s*\{[^}]*display:\s*none/s);
  assert.doesNotMatch(pageCss, /\.is-dock[^}]*rotateZ\(calc\(var\(--action-offset\) \* -/s);
});

test('the stage uses a fading planetary horizon instead of crosshair lines', () => {
  assert.doesNotMatch(pageCss, /\.dual-nav-demo::before/);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery\s*\{[^}]*border-top:/s);
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*width:\s*min\(1040px,\s*calc\(100vw - 80px\)\)[^}]*height:\s*60px[^}]*border-top:[^}]*border-radius:\s*50%/s);
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*mask-image:\s*linear-gradient\(90deg,\s*transparent/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*width:\s*72px/s);
});

test('the planetary horizon stays below the dock at compact and wide sizes', () => {
  assert.match(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*top:\s*clamp\(150px,\s*18vh,\s*280px\)/s);
  assert.match(pageCss, /@media \(min-width:\s*1800px\)[\s\S]*\.dual-nav-demo__gallery::before\s*\{[^}]*top:\s*clamp\(240px,\s*18vh,\s*280px\)/s);
  assert.doesNotMatch(pageCss, /\.dual-nav-demo__gallery::before\s*\{[^}]*clip-path:/s);
});
