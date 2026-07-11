import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

async function importTypescriptModule(sourcePath, name) {
  const dir = mkdtempSync(join(tmpdir(), 'ki-cinematic-template-'));
  const source = readFileSync(sourcePath, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  }).outputText;
  const modulePath = join(dir, `${name}.mjs`);
  writeFileSync(modulePath, compiled);
  return import(modulePath);
}

const geometry = await importTypescriptModule(
  new URL('./cinematicNavigationGeometry.ts', import.meta.url),
  'cinematicNavigationGeometry',
);
const systemRequests = await importTypescriptModule(
  new URL('../cinematic-system/systemRequestUtils.ts', import.meta.url),
  'systemRequestUtils',
);

test('navigation child menu remains inside the shared 330px rail', () => {
  const top = geometry.computeCinematicNavigationGeometry(6, 0, 4);
  const bottom = geometry.computeCinematicNavigationGeometry(6, 5, 2);

  assert.ok(top.childMenuBottom >= 24);
  assert.ok(top.childMenuBottom + top.childMenuHeight <= 310);
  assert.ok(bottom.childMenuBottom >= 24);
  assert.ok(bottom.childMenuBottom + bottom.childMenuHeight <= 310);
});

test('system log requests are trimmed and capped by default', () => {
  const url = new URL(systemRequests.buildSystemLogPath('WARNING', ' timeout '), 'http://localhost');

  assert.equal(url.pathname, '/api/logs');
  assert.equal(url.searchParams.get('level'), 'WARNING');
  assert.equal(url.searchParams.get('search'), 'timeout');
  assert.equal(url.searchParams.get('limit'), '100');
});
