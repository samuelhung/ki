import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { createSystemPromptCache } from './systemPromptCache.ts';

const pageUrl = new URL('../../pages/CinematicSystemCenter.tsx', import.meta.url);
const panelsUrl = new URL('./SystemCenterPanels.tsx', import.meta.url);
const assetsUrl = new URL('./SystemAssetBox.tsx', import.meta.url);
const usageUrl = new URL('../UsageWidget.tsx', import.meta.url);
const hudUrl = new URL('../cinematic/CinematicHud.tsx', import.meta.url);
const cssUrl = new URL('./cinematic-system.css', import.meta.url);
const appUrl = new URL('../../App.tsx', import.meta.url);
const curtainUrl = new URL('../../CurtainContext.tsx', import.meta.url);
const configHookUrl = new URL('./useSystemConfig.ts', import.meta.url);
const databaseHookUrl = new URL('./useSystemDatabase.ts', import.meta.url);

test('system prompt cache coalesces concurrent loads and reuses the result', async () => {
  let calls = 0;
  const cache = createSystemPromptCache(async () => {
    calls += 1;
    return { ingest_pipeline: { summarize: { system: 'cached prompt' } } };
  });

  const [first, second] = await Promise.all([cache.load(), cache.load()]);
  const third = await cache.load();

  assert.equal(calls, 1);
  assert.equal(first, second);
  assert.equal(second, third);
});

test('system prompt cache retries after a failed load', async () => {
  let calls = 0;
  const cache = createSystemPromptCache(async () => {
    calls += 1;
    if (calls === 1) throw new Error('temporary failure');
    return { series: { discover: { system: 'ready' } } };
  });

  await assert.rejects(cache.load(), /temporary failure/);
  const prompts = await cache.load();

  assert.equal(calls, 2);
  assert.equal(prompts.series.discover.system, 'ready');
});

test('clearing the system prompt cache invalidates an active request', async () => {
  let calls = 0;
  let resolveFirst;
  const firstLoad = new Promise((resolve) => {
    resolveFirst = resolve;
  });
  const cache = createSystemPromptCache(async () => {
    calls += 1;
    if (calls === 1) return firstLoad;
    return { series: { discover: { system: 'fresh prompt' } } };
  });

  const staleRequest = cache.load();
  cache.clear();
  resolveFirst({ series: { discover: { system: 'stale prompt' } } });
  await staleRequest;
  const prompts = await cache.load();

  assert.equal(calls, 2);
  assert.equal(prompts.series.discover.system, 'fresh prompt');
});

test('system center uses the finalized KI navigation workspace shell', async () => {
  const page = await readFile(pageUrl, 'utf8');

  assert.match(page, /import KiNavigationShell from ['"]\.\/KiNavigationShell['"]/);
  assert.match(page, /<KiNavigationShell[\s\S]*className="ki-shell-ingest-preview ki-shell-system"[\s\S]*sceneVariant="ingest"/);
  assert.match(page, /className="ki-shell-content"/);
  assert.match(page, /className="ki-shell-legacy-ingest"/);
  assert.match(page, /className="ki-ingest-split-stage"/);
  assert.match(page, /className="ki-ingest-list-pane"/);
  assert.match(page, /className="ki-ingest-detail-pane"/);
  assert.doesNotMatch(page, /CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow/);
});

test('system center routes skip initial and navigation curtain animations', async () => {
  const [app, curtain] = await Promise.all([
    readFile(appUrl, 'utf8'),
    readFile(curtainUrl, 'utf8'),
  ]);
  const skipExpression = app.match(/const skipInitialCurtain = ([^;]+);/)?.[1] || '';
  const bypassFunction = curtain.match(/function shouldBypassCurtain[\s\S]*?\n\}/)?.[0] || '';

  assert.match(skipExpression, /location\.pathname === '\/system'/);
  assert.match(skipExpression, /location\.pathname === '\/settings'/);
  assert.match(bypassFunction, /pathname === '\/system'/);
  assert.match(bypassFunction, /pathname === '\/settings'/);
});

test('system center exposes four observation entries and seven direct control entries', async () => {
  const [page, panels] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(panelsUrl, 'utf8'),
  ]);

  assert.match(page, /label: '观测'/);
  assert.match(page, /label: '控制'/);
  const observationItems = page.match(/key: 'observe'[\s\S]*?items:\s*\[([\s\S]*?)\n\s*\],/)?.[1] || '';
  const moduleItems = panels.match(/export const MODULE_CONFIG_ITEMS = \[([\s\S]*?)\n\];/)?.[1] || '';
  assert.equal(observationItems.match(/\{ key:/g)?.length, 4);
  assert.equal(moduleItems.match(/\{ key:/g)?.length, 6);
  for (const key of ['boundary', 'changelog', 'logs', 'assets', 'base_config']) {
    assert.match(page, new RegExp(`key: '${key}'`));
  }
  for (const key of ['ingest_pipeline', 'series', 'brainstorm', 'briefing', 'tasks', 'concept']) {
    assert.match(panels, new RegExp(`key: '${key}'`));
  }
  assert.doesNotMatch(panels, /digest_briefing|knowledge_graph|知识图谱|实体深度分析|每日摘要/);
  assert.doesNotMatch(page, /key: 'portrait'/);
  assert.doesNotMatch(page, /key: 'flow'/);
  assert.doesNotMatch(page, /key: 'ai_modules'/);
  assert.match(page, /MODULE_CONFIG_ITEMS\.map/);
  assert.match(page, /location\.pathname === '\/settings' \? 'base_config' : 'boundary'/);
  assert.match(page, /<SpotlightListRow/);
});

test('system observation pages have distinct names and semantic responsibilities', async () => {
  const [page, panels, assets] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(panelsUrl, 'utf8'),
    readFile(assetsUrl, 'utf8'),
  ]);

  for (const [key, label] of [
    ['boundary', '工程规范'],
    ['assets', '资产台账'],
  ]) {
    assert.match(page, new RegExp(`key: '${key}', label: '${label}'`));
  }
  assert.doesNotMatch(page, /数据链路/);
  assert.doesNotMatch(page, /能力版图/);
  assert.doesNotMatch(panels, /CoreModules|system-module-constellation/);
  assert.match(panels, /label: '工程规范'/);
  assert.doesNotMatch(panels, /const RUNTIME_LAYERS/);
  assert.doesNotMatch(panels, /ARCHITECTURE_FEATURES/);
  assert.doesNotMatch(panels, /INGEST_FLOW_STEPS|RuntimeFlow|system-runtime-branches/);
  assert.match(panels, /TECH_STACK/);
  assert.match(panels, /RELEASE_GUARDRAILS/);
  assert.match(panels, /ENGINEERING_CONTRACTS/);
  assert.match(assets, /aria-label="资产台账"/);
  assert.match(assets, /<b>资产台账<\/b>/);
});

test('system center keeps focused panels and renders each AI module directly', async () => {
  const [page, panels, assets] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(panelsUrl, 'utf8'),
    readFile(assetsUrl, 'utf8'),
  ]);

  assert.doesNotMatch(page, /^function render/m);
  assert.match(panels, /export const SystemDocsPanel/);
  assert.match(panels, /export const SystemLogsPanel/);
  assert.match(panels, /export const SystemBaseConfigPanel/);
  assert.match(panels, /export const SystemAiModulesPanel/);
  assert.match(page, /<SystemDocsPanel activePane=\{activeSection\}/);
  assert.match(assets, /export function SystemAssetsPanel/);
  assert.match(page, /activeSection === 'assets'[\s\S]*<SystemAssetsPanel/);
  assert.match(page, /isAiModuleSection\(activeSection\)[\s\S]*<SystemAiModulesPanel[\s\S]*activeModule=\{activeSection\}/);
  assert.doesNotMatch(panels, /className="system-module-switcher"/);
  assert.doesNotMatch(page, /activeAiPane|setActiveAiPane/);
  assert.doesNotMatch(panels, /AI_MODULE_PANES|system-ai-pane-switcher|activeAiPane|setActiveAiPane/);
  assert.match(panels, /className="system-ai-module-stack system-composite-view"[\s\S]*<ModuleConfig[\s\S]*<PromptSection key=\{activeModule\}/);
  assert.match(panels, /<PromptSection key=\{activeModule\}[\s\S]*defaultExpanded/);
  assert.match(panels, /React\.memo\(function SystemAiModulesPanel/);
  assert.match(panels, /React\.memo\(function SystemDocsPanel/);
  assert.match(panels, /React\.memo\(function SystemLogsPanel/);
  assert.match(panels, /React\.memo\(function SystemBaseConfigPanel/);
  assert.doesNotMatch(page, /<SystemAssetBox/);
});

test('system data loads only when its owning section is active', async () => {
  const [page, configHook, databaseHook] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(configHookUrl, 'utf8'),
    readFile(databaseHookUrl, 'utf8'),
  ]);

  assert.match(page, /const needsConfig = activeSection === 'base_config' \|\| isAiModuleSection\(activeSection\)/);
  assert.match(page, /useSystemConfig\(needsConfig\)/);
  assert.match(page, /useSystemDatabase\(activeSection === 'assets'\)/);
  assert.match(configHook, /export function useSystemConfig\(enabled: boolean\)/);
  assert.match(configHook, /if \(!enabled \|\| config\) return/);
  assert.match(databaseHook, /export function useSystemDatabase\(enabled: boolean\)/);
  assert.match(databaseHook, /if \(enabled && !dbInfo\) loadDbInfo\(\)/);
});

test('asset inventory uses semantic icons and tones for every metric', async () => {
  const [assets, css] = await Promise.all([
    readFile(assetsUrl, 'utf8'),
    readFile(cssUrl, 'utf8'),
  ]);

  assert.match(assets, /items:\s*\[[\s\S]*icon:\s*HardDrive[\s\S]*tone:\s*'violet'/);
  assert.match(assets, /className=\{`system-asset-item is-\$\{item\.tone\}`\}/);
  assert.match(assets, /<ItemIcon size=\{13\}/);
  assert.match(assets, /system-assets-summary-item is-/);
  const assetGroupSource = assets.match(/function buildAssetGroups[\s\S]*?\n\}\n\nfunction AssetGroups/)?.[0] || '';
  assert.equal(assetGroupSource.match(/icon:\s*\w+,\s*tone:\s*'/g)?.length, 15);
  assert.doesNotMatch(assetGroupSource, /digests|每日摘要|label:\s*'摘要'/);
  assert.match(css, /\.system-asset-group \.system-asset-item\s*\{[^}]*display:\s*grid/s);
  assert.match(css, /\.system-asset-item\.is-cyan/);
  assert.match(css, /\.system-asset-item\.is-gold/);
  assert.match(css, /\.system-asset-item\.is-blue/);
  assert.match(css, /\.system-asset-item\.is-violet/);
  assert.match(css, /\.system-asset-item\.is-rose/);
  assert.match(css, /@media \(max-width:\s*1180px\)[\s\S]*\.system-asset-group header small\s*\{[^}]*grid-column:\s*2/s);
});

test('active briefing config is renamed while usage keeps historical compatibility', async () => {
  const [panels, types, usage, hud] = await Promise.all([
    readFile(panelsUrl, 'utf8'),
    readFile(new URL('./systemTypes.ts', import.meta.url), 'utf8'),
    readFile(usageUrl, 'utf8'),
    readFile(hudUrl, 'utf8'),
  ]);

  assert.match(panels, /briefing:\s*\{\s*briefing_quick:[\s\S]*briefing_daily:/);
  assert.doesNotMatch(panels, /digest_briefing|\bdigest:\s*\{|每日摘要/);
  assert.match(types, /briefing:\s*ModuleConfig/);
  assert.doesNotMatch(types, /digest_briefing/);
  assert.match(usage, /briefing:\s*'即时快报'/);
  assert.match(usage, /digest_briefing:\s*'摘要快报'/);
  assert.match(hud, /briefing:\s*'即时快报'/);
  assert.match(hud, /digest_briefing:\s*'摘要快报'/);
});

test('system Prompt content shares one left alignment axis', async () => {
  const [controls, css] = await Promise.all([
    readFile(new URL('../SystemSettingsControls.tsx', import.meta.url), 'utf8'),
    readFile(cssUrl, 'utf8'),
  ]);

  assert.match(controls, /className="system-prompt-section/);
  assert.match(controls, /className="system-prompt-body/);
  assert.match(controls, /className="system-prompt-task/);
  assert.match(controls, /className="system-prompt-summary/);
  assert.match(controls, /<ChevronRight size=\{12\}/);
  assert.match(controls, /SYSTEM_PROMPT_CACHE\.load\(\)/);
  assert.match(controls, /function PromptTemplate/);
  assert.match(controls, /\{open && \(/);
  assert.match(css, /\.cinematic-system \.system-prompt-body\s*\{[^}]*padding-left:\s*0\s*!important[^}]*padding-right:\s*0\s*!important/s);
  assert.match(css, /\.cinematic-system \.system-prompt-task\s*\{[^}]*margin-left:\s*0/s);
  assert.match(css, /\.cinematic-system \.system-prompt-summary\s*\{[^}]*list-style:\s*none/s);
  assert.match(css, /\.cinematic-system \.system-prompt-summary::-webkit-details-marker\s*\{[^}]*display:\s*none/s);
  assert.match(css, /\.cinematic-system \.system-prompt-content\s*\{[^}]*padding-left:\s*0\s*!important/s);
});

test('system center preserves operational actions and compact status', async () => {
  const page = await readFile(pageUrl, 'utf8');

  for (const label of ['刷新状态', '刷新数据库', '检查更新', '保存配置']) {
    assert.match(page, new RegExp(`title="${label}"`));
  }
  assert.match(page, /className="system-shell-status"/);
  assert.match(page, /health\.data\?\.ok\s*\?\s*'在线'/);
  assert.match(page, /health\.data\?\.ok\s*\?\s*'is-online'/);
});

test('system shell CSS owns responsive split geometry without restoring the old bottom box', async () => {
  const css = await readFile(cssUrl, 'utf8');

  assert.match(css, /\.ki-shell-system \.ki-ingest-split-stage\s*\{/);
  assert.match(css, /\.ki-shell-system \.system-detail-reader\s*\{[^}]*position:\s*relative[^}]*width:\s*100%[^}]*height:\s*100%/s);
  assert.match(css, /\.ki-shell-system \.system-group-tabs\s*\{/);
  assert.match(css, /\.ki-shell-system \.cinematic-ingest\.cinematic-system \.system-function-list\s*\{[^}]*pointer-events:\s*auto !important[^}]*transform:\s*none !important/s);
  assert.match(css, /system-function-list\[data-group="control"\][\s\S]*min-height:\s*56px/);
  assert.match(css, /@media \(max-width:\s*1280px\)[\s\S]*system-function-list\[data-group="control"\][\s\S]*min-height:\s*46px/);
  assert.doesNotMatch(css, /system-ai-pane-switcher/);
  assert.match(css, /\.cinematic-system \.system-ai-module-stack\s*\{/);
  assert.match(css, /\.cinematic-system \.system-task-grid\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:/s);
  assert.match(css, /\.system-ai-module-stack\s*\{[^}]*container-type:\s*inline-size/s);
  assert.match(css, /@container\s*\(max-width:\s*660px\)[\s\S]*\.system-task-grid\s*>\s*div/);
  assert.match(css, /@media \(max-width:\s*1280px\)[\s\S]*\.ki-shell-system \.ki-ingest-split-stage/s);
});
