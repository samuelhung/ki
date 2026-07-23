import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  countExplicitAnyNodes,
  findCountDrift,
  findExplicitAnyRegressions,
  sourceFiles,
} from './check-explicit-any.mjs';

test('counts explicit any type nodes without matching property names', () => {
  const source = `
    let value: any;
    const cast = input as any;
    const signal = AbortSignal.any([controller.signal]);
  `;

  assert.equal(countExplicitAnyNodes(source, 'fixture.ts'), 2);
});

test('requires the checked-in baseline to match current counts exactly', () => {
  const baseline = {
    'src/existing.ts': 3,
    'src/removed.ts': 1,
  };
  const current = {
    'src/existing.ts': 2,
    'src/increased.ts': 1,
  };

  assert.deepEqual(findCountDrift(current, baseline), [
    { path: 'src/existing.ts', baseline: 3, current: 2 },
    { path: 'src/increased.ts', baseline: 0, current: 1 },
    { path: 'src/removed.ts', baseline: 1, current: 0 },
  ]);
});

test('rejects baseline increases relative to the pull request base', () => {
  assert.deepEqual(
    findExplicitAnyRegressions(
      { 'src/existing.ts': 2, 'src/new.mts': 1 },
      { 'src/existing.ts': 3 },
    ),
    [{ path: 'src/new.mts', baseline: 0, current: 1 }],
  );
});

test('discovers every TypeScript source extension', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'explicit-any-'));
  try {
    for (const filename of ['a.ts', 'b.tsx', 'c.mts', 'd.cts', 'e.d.mts', 'ignored.js']) {
      fs.writeFileSync(path.join(root, filename), 'type Value = any;');
    }

    assert.deepEqual(
      sourceFiles(root).map((filename) => path.basename(filename)).sort(),
      ['a.ts', 'b.tsx', 'c.mts', 'd.cts', 'e.d.mts'],
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
