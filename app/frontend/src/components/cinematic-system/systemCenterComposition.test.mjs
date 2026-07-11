import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pageUrl = new URL('../../pages/CinematicSystemCenter.tsx', import.meta.url);
const panelsUrl = new URL('./SystemCenterPanels.tsx', import.meta.url);
const assetsUrl = new URL('./SystemAssetBox.tsx', import.meta.url);

test('system center delegates detail rendering to focused panel components', async () => {
  const [page, panels] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(panelsUrl, 'utf8'),
  ]);

  assert.doesNotMatch(page, /^function render/m);
  assert.match(panels, /export function SystemDocsPanel/);
  assert.match(panels, /export function SystemLogsPanel/);
  assert.match(panels, /export function SystemBaseConfigPanel/);
  assert.match(panels, /export function SystemAiModulesPanel/);
});

test('system assets are rendered by a dedicated box component', async () => {
  const [page, assets] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(assetsUrl, 'utf8'),
  ]);

  assert.match(page, /<SystemAssetBox/);
  assert.match(assets, /export function SystemAssetBox/);
});

test('ingest and system pages compose the shared cinematic template shell', async () => {
  const ingestUrl = new URL('../../pages/CinematicIngest.tsx', import.meta.url);
  const templateUrl = new URL('../cinematic/CinematicTemplatePage.tsx', import.meta.url);
  const workspaceUrl = new URL('../cinematic/CinematicLaserWorkspace.tsx', import.meta.url);
  const [systemPage, ingestPage, template, workspace] = await Promise.all([
    readFile(pageUrl, 'utf8'),
    readFile(ingestUrl, 'utf8'),
    readFile(templateUrl, 'utf8'),
    readFile(workspaceUrl, 'utf8'),
  ]);

  for (const page of [systemPage, ingestPage]) {
    assert.match(page, /<CinematicTemplatePage/);
    assert.match(page, /<CinematicLaserWorkspace/);
    assert.doesNotMatch(page, /<main className="cinematic-ingest-shell">/);
  }
  assert.match(template, /export default function CinematicTemplatePage/);
  assert.match(workspace, /export default function CinematicLaserWorkspace/);
});
