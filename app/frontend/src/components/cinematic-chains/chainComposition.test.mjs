import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicIndustryChains.tsx', import.meta.url), 'utf8');
const workspaceTypes = readFileSync(new URL('./chainWorkspace.d.mts', import.meta.url), 'utf8');
const detailView = readFileSync(new URL('./ChainDetailView.tsx', import.meta.url), 'utf8');
const editorDialog = readFileSync(new URL('./ChainEditorDialog.tsx', import.meta.url), 'utf8');
const reviewDialogs = readFileSync(new URL('./ChainReviewDialogs.tsx', import.meta.url), 'utf8');
const detailPanels = readFileSync(new URL('./ChainDetailPanels.tsx', import.meta.url), 'utf8');
const report = readFileSync(new URL('../ChainReport.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./cinematic-chains.css', import.meta.url), 'utf8');

test('industry chain production code uses focused modules and retires the legacy page', () => {
  assert.equal(existsSync(new URL('./chainTypes.ts', import.meta.url)), true);
  assert.equal(existsSync(new URL('./ChainEditorDialog.tsx', import.meta.url)), true);
  assert.equal(existsSync(new URL('./ChainReviewDialogs.tsx', import.meta.url)), true);
  assert.equal(existsSync(new URL('./ChainDetailView.tsx', import.meta.url)), true);
  assert.match(page, /from ['"]\.\.\/components\/cinematic-chains\/chainTypes['"]/);
  assert.match(page, /from ['"]\.\.\/components\/cinematic-chains\/ChainEditorDialog['"]/);
  assert.match(page, /from ['"]\.\.\/components\/cinematic-chains\/ChainReviewDialogs['"]/);
  assert.match(page, /from ['"]\.\.\/components\/cinematic-chains\/ChainDetailView['"]/);
  assert.match(workspaceTypes, /from ['"]\.\/chainTypes['"]/);
  assert.equal(existsSync(new URL('../../pages/IndustryChains.tsx', import.meta.url)), false);

  const sourceRoot = fileURLToPath(new URL('../..', import.meta.url));
  const pending = [sourceRoot];
  while (pending.length > 0) {
    const directory = pending.pop();
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) pending.push(path);
      if (!entry.isFile() || !['.ts', '.tsx', '.mts'].includes(extname(entry.name)) || /\.test\.[^.]+$/.test(entry.name)) continue;
      assert.doesNotMatch(readFileSync(path, 'utf8'), /from ['"][^'"]*IndustryChains['"]/);
    }
  }
});

test('industry chains use the finalized KI split workspace', () => {
  assert.match(page, /import KiNavigationShell from ['"]\.\/KiNavigationShell['"]/);
  assert.match(page, /<KiNavigationShell[\s\S]*className="ki-shell-ingest-preview ki-shell-chains"[\s\S]*sceneVariant="ingest"/);
  assert.match(page, /className="ki-shell-content"/);
  assert.match(page, /className="ki-shell-legacy-ingest"/);
  assert.match(page, /className="ki-ingest-split-stage"/);
  assert.match(page, /className="ki-ingest-list-pane"/);
  assert.match(page, /className="ki-ingest-detail-pane[^"]*"/);
  assert.match(page, /<SpotlightListRow/);
  assert.match(page, /LegacyChainDetail/);
  assert.doesNotMatch(page, /CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow/);
});

test('industry chains keep search and page-specific actions in the shared shell', () => {
  assert.match(page, /className="ki-ingest-list-search"/);
  assert.doesNotMatch(page, /onGlobalAction=\{handleGlobalAction\}/);
  assert.doesNotMatch(page, /item\.key === 'concept'|item\.key === 'scan'|item\.key === 'global'/);
  assert.match(page, /<EditModal/);
  assert.match(page, /<HintsReviewModal/);
  assert.match(page, /<SuggestionDialog/);
  assert.match(page, /aria-label="新建产业链节点"/);
  assert.match(page, /aria-label="审核更新提示"/);
  assert.match(page, /aria-label="审核新链建议"/);
  assert.match(page, /disabled=\{hintCount === 0/);
  assert.match(page, /disabled=\{suggestionCount === 0/);
  assert.match(page, /aria-label="刷新产业链"/);
  assert.doesNotMatch(page, /aria-label="打开全景关系"/);
  assert.doesNotMatch(page, /navigate\('\/industry-flow'\)/);
});

test('suggestion actions recover from failed requests without leaving the dialog locked', () => {
  assert.match(page, /async function act[\s\S]*try\s*\{/);
  assert.match(page, /if \(!response\.ok\) throw new Error/);
  assert.match(page, /finally\s*\{\s*setBusy\(''\)/);
});

test('industry chain actions remain available before the first chain exists', () => {
  assert.match(page, /const chainActions = \(/);
  assert.match(page, /className="chain-empty-detail-actions"/);
  assert.match(page, /chainActions[\s\S]*chain-cinematic-loading/);
});

test('industry chains preserve overlap detection and merge actions', () => {
  assert.match(page, /aria-label="检测产业链重叠"/);
  assert.match(page, /apiFetch\('\/api\/chains\/overlap-check'/);
  assert.match(page, /apiFetch\('\/api\/chains\/merge'/);
  assert.match(page, /<OverlapDialog/);
  assert.match(page, /并入/);
  assert.match(page, /合并为新链/);
});

test('industry chain core data and review counts load independently', () => {
  assert.match(page, /const loadCoreData = useCallback/);
  assert.match(page, /const loadReviewCounts = useCallback/);
  assert.match(page, /apiFetch\('\/api\/chains\/hints\/count'/);
  assert.match(page, /apiFetch\('\/api\/chains\/suggestions\/count'/);
  assert.match(page, /const loadHints = useCallback/);
  assert.match(page, /const loadSuggestions = useCallback/);
  assert.doesNotMatch(page.match(/const loadCoreData[\s\S]*?\n  }, \[\]\);/)?.[0] || '', /hints\?status|suggestions\?status/);
});

test('industry chain refresh rejects failed HTTP snapshots before replacing valid data', () => {
  assert.match(page, /const responses = await Promise\.all/);
  assert.match(page, /const failedResponse = responses\.find\(\(response\) => !response\.ok\)/);
  assert.match(page, /if \(failedResponse\) throw new Error/);
  assert.match(page, /coreLifecycleRef\.current\.isCurrent\(request\.sequence\)/);
});

test('destructive chain merges require an in-dialog preview confirmation', () => {
  assert.match(page, /mergeConfirmation/);
  assert.match(page, /确认合并/);
  assert.match(page, /取消/);
  assert.match(page, /sharedNodes/);
});

test('industry chain collection exposes visible operation results', () => {
  assert.match(page, /operationStatus/);
  assert.match(page, /role="status"/);
  assert.match(page, /采集完成/);
  assert.match(page, /采集失败/);
});

test('industry chain detail isolates report and chat rendering with shared per-chain cache', () => {
  assert.match(detailView, /<ChainReportPanel/);
  assert.match(detailView, /<ChainChatPanel/);
  assert.match(page, /createChainDetailCache/);
  assert.doesNotMatch(page, /key=\{selected\.name\}/);
  assert.match(detailPanels, /memo\(function ChainReportPanel/);
  assert.match(detailPanels, /memo\(function ChainChatPanel/);
  assert.match(detailPanels, /new RequestLifecycle\(\)/);
});

test('chain report parsing is memoized by report content', () => {
  assert.match(report, /useMemo\(\(\) => chainReportToHtml\(report\), \[report\]\)/);
});

test('shared chain edit and review dialogs keep failures and delete confirmation inline', () => {
  assert.match(editorDialog, /actionError/);
  assert.match(editorDialog, /deleteArmed/);
  assert.doesNotMatch(editorDialog, /alert\(|confirm\(/);
  assert.match(reviewDialogs, /actionError/);
  assert.doesNotMatch(reviewDialogs, /alert\(/);
});

test('industry chain suggestions preserve structure and source evidence before adoption', () => {
  assert.match(page, /item\.source_quote/);
  assert.match(page, /item\.nodes_json\.map/);
  assert.match(page, /node\.description/);
  assert.match(page, /node\.initial_data/);
  assert.match(page, /className="chain-suggestion-nodes"/);
});

test('embedded chain detail only reads cached AI reports on mount', () => {
  assert.match(detailPanels, /cache_only: embedded && !force/);
  assert.match(detailView, /if \(embedded\) \{ setFlowSummary\(''\); return; \}/);
  assert.match(detailPanels, /embedded \? '正在读取分析报告…' : '正在生成分析报告…'/);
});

test('embedded chain chat scroll stays inside its own message pane', () => {
  assert.match(detailPanels, /const chatScrollRef = useRef<HTMLDivElement>\(null\)/);
  assert.match(detailPanels, /chatScrollRef\.current/);
  assert.match(detailPanels, /target\.scrollTo\(\{ top: target\.scrollHeight, behavior: 'smooth' \}\)/);
  assert.doesNotMatch(detailView, /chatEndRef\.current\?\.scrollIntoView/);
});

test('chain collection indicators follow the real request lifecycle instead of fixed timers', () => {
  assert.match(detailView, /await onCollectChain\(chainName\)/);
  assert.match(detailView, /await onCollectNode\(node\.id\)/);
  assert.doesNotMatch(detailView, /setTimeout\(\(\) => setCollectingChain\(false\), 30000\)/);
  assert.doesNotMatch(detailView, /setTimeout\(\(\) => setCollectingNode\(null\), 30000\)/);
});

test('industry chain routes bypass the retired full-screen curtain', () => {
  const skipExpression = app.match(/const skipInitialCurtain = ([^;]+);/)?.[1] || '';
  const bypassFunction = curtain.match(/function shouldBypassCurtain[\s\S]*?\n\}/)?.[0] || '';

  assert.match(skipExpression, /location\.pathname === '\/industry-chains'/);
  assert.match(skipExpression, /location\.pathname === '\/chains'/);
  assert.match(bypassFunction, /pathname === '\/industry-chains'/);
  assert.match(bypassFunction, /pathname === '\/chains'/);
});

test('industry chain detail becomes a continuous reader only inside the new shell', () => {
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded\s*\{[^}]*position:\s*relative[^}]*width:\s*100%[^}]*height:\s*100%/s);
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded-shell\s*\{[^}]*background:\s*transparent/s);
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded-shell \*\s*\{[^}]*min-width:\s*0[^}]*overflow-wrap:\s*anywhere/s);
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded-shell[^}]*scrollbar-width:\s*none/s);
  assert.match(css, /@media \(max-width:\s*1180px\)[\s\S]*\.ki-shell-chains \.chain-detail-embedded/s);
});

test('embedded chain flow only consumes space when node detail is expanded', () => {
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded-shell \.h-\\\[45\\%\\\][^{]*\{[^}]*height:\s*auto\s*!important[^}]*max-height:\s*45%/s);
  assert.match(css, /\.ki-shell-chains \.chain-detail-embedded-shell > div:nth-child\(2\)[^{]*\{[^}]*background:\s*linear-gradient/s);
});

test('embedded chain analysis stacks at compact template viewports', () => {
  assert.match(css, /@media \(max-width:\s*1500px\)/);
  assert.match(css, /@media \(max-width:\s*1500px\)[\s\S]*flex-direction:\s*column/s);
  assert.match(css, /scrollbar-width:\s*none/);
});

test('compact industry chain workspace inherits the shared shell translation', () => {
  assert.doesNotMatch(css, /\.ki-shell-chains \.ki-shell-content\s*\{[^}]*transform:/s);
});
