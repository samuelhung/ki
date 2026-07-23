import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const helperUrl = new URL('./chainShares.ts', import.meta.url);
const detailView = readFileSync(new URL('./ChainDetailView.tsx', import.meta.url), 'utf8');

test('grouped global shares round-trip without losing their sections', async () => {
  assert.equal(existsSync(helperUrl), true, 'chain share normalization helper must exist');
  const { flattenGlobalShares, isGroupedGlobalShares, serializeGlobalShares } = await import(helperUrl);
  const grouped = {
    groups: {
      production: [{ c: '中国', p: 60 }],
      supply: [{ c: '智利', p_export_global: 25 }],
      demand: [{ c: '德国', d_import_global: 18 }],
    },
  };

  assert.equal(isGroupedGlobalShares(grouped), true);
  assert.deepEqual(serializeGlobalShares(flattenGlobalShares(grouped), true), grouped);
});

test('legacy flat shares remain flat when saved', async () => {
  assert.equal(existsSync(helperUrl), true, 'chain share normalization helper must exist');
  const { flattenGlobalShares, isGroupedGlobalShares, serializeGlobalShares } = await import(helperUrl);
  const flat = [{ c: '中国', p: 60 }];

  assert.equal(isGroupedGlobalShares(flat), false);
  assert.deepEqual(serializeGlobalShares(flattenGlobalShares(flat), false), flat);
});

test('malformed grouped shares are rejected instead of normalized as valid data', async () => {
  assert.equal(existsSync(helperUrl), true, 'chain share normalization helper must exist');
  const { isGroupedGlobalShares, normalizeShareGroups } = await import(helperUrl);

  assert.equal(isGroupedGlobalShares({ groups: [] }), false);
  assert.equal(isGroupedGlobalShares({ groups: { production: [], supply: [] } }), false);
  assert.deepEqual(normalizeShareGroups({ groups: [] }), { production: [], supply: [], demand: [] });
});

test('share group panel calls hooks before its empty-state return', () => {
  const panel = detailView.split('function ShareGroupPanel', 2)[1]?.split('const TRANSITION_LABELS', 1)[0] || '';
  const hookIndex = panel.indexOf('useState<number | null>');
  const emptyReturnIndex = panel.indexOf('if (!items.length) return');

  assert.notEqual(hookIndex, -1);
  assert.notEqual(emptyReturnIndex, -1);
  assert.ok(hookIndex < emptyReturnIndex);
});
