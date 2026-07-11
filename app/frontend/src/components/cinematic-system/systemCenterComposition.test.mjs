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
