import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import ts from 'typescript';

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_ROOT = path.join(FRONTEND_ROOT, 'src');
const BASELINE_PATH = path.join(FRONTEND_ROOT, 'explicit-any-baseline.json');
const REPOSITORY_ROOT = path.resolve(FRONTEND_ROOT, '..', '..');
const BASELINE_REPOSITORY_PATH = 'app/frontend/explicit-any-baseline.json';

export function countExplicitAnyNodes(source, filename) {
  const scriptKind = ts.getScriptKindFromFileName(filename);
  const sourceFile = ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    true,
    scriptKind,
  );
  let count = 0;

  function visit(node) {
    if (node.kind === ts.SyntaxKind.AnyKeyword) count += 1;
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return count;
}

export function findExplicitAnyRegressions(current, baseline) {
  return Object.entries(current)
    .filter(([file, count]) => count > (baseline[file] ?? 0))
    .map(([file, count]) => ({
      path: file,
      baseline: baseline[file] ?? 0,
      current: count,
    }))
    .sort((left, right) => left.path.localeCompare(right.path));
}

export function findCountDrift(current, baseline) {
  return [...new Set([...Object.keys(current), ...Object.keys(baseline)])]
    .filter((file) => (current[file] ?? 0) !== (baseline[file] ?? 0))
    .map((file) => ({
      path: file,
      baseline: baseline[file] ?? 0,
      current: current[file] ?? 0,
    }))
    .sort((left, right) => left.path.localeCompare(right.path));
}

export function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const absolute = path.join(directory, entry.name);
      if (entry.isDirectory()) return sourceFiles(absolute);
      return /\.(?:[cm]?ts|tsx)$/.test(entry.name) ? [absolute] : [];
    })
    .sort();
}

function currentCounts() {
  return Object.fromEntries(
    sourceFiles(SOURCE_ROOT)
      .map((absolute) => {
        const relative = path.relative(FRONTEND_ROOT, absolute).split(path.sep).join('/');
        const source = fs.readFileSync(absolute, 'utf8');
        return [relative, countExplicitAnyNodes(source, relative)];
      })
      .filter(([, count]) => count > 0)
      .sort(([left], [right]) => left.localeCompare(right)),
  );
}

function readBaseline(text, label) {
  const value = JSON.parse(text);
  if (!value || Array.isArray(value) || typeof value !== 'object') {
    throw new Error(`${label} must be a JSON object`);
  }
  for (const [file, count] of Object.entries(value)) {
    if (!file.startsWith('src/') || !/\.(?:[cm]?ts|tsx)$/.test(file)) {
      throw new Error(`${label} contains an invalid source path: ${file}`);
    }
    if (!Number.isInteger(count) || count <= 0) {
      throw new Error(`${label} contains an invalid count for ${file}`);
    }
  }
  return value;
}

function referenceBaseline(reference) {
  if (!reference) return null;
  execFileSync('git', ['rev-parse', '--verify', `${reference}^{commit}`], {
    cwd: REPOSITORY_ROOT,
    stdio: 'ignore',
  });
  try {
    execFileSync('git', ['cat-file', '-e', `${reference}:${BASELINE_REPOSITORY_PATH}`], {
      cwd: REPOSITORY_ROOT,
      stdio: 'ignore',
    });
  } catch {
    return null;
  }
  const text = execFileSync(
    'git',
    ['show', `${reference}:${BASELINE_REPOSITORY_PATH}`],
    { cwd: REPOSITORY_ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] },
  );
  return readBaseline(text, `explicit-any baseline at ${reference}`);
}

function main() {
  const current = currentCounts();
  if (process.argv.includes('--write-baseline')) {
    fs.writeFileSync(BASELINE_PATH, `${JSON.stringify(current, null, 2)}\n`);
    const total = Object.values(current).reduce((sum, count) => sum + count, 0);
    console.log(`wrote explicit-any baseline: ${total}`);
    return;
  }

  if (!fs.existsSync(BASELINE_PATH)) {
    throw new Error(`missing explicit-any baseline: ${BASELINE_PATH}`);
  }
  const baseline = readBaseline(
    fs.readFileSync(BASELINE_PATH, 'utf8'),
    'explicit-any baseline',
  );
  const drift = findCountDrift(current, baseline);
  if (drift.length > 0) {
    for (const regression of drift) {
      console.error(
        `${regression.path}: explicit any baseline is stale `
        + `${regression.baseline} -> ${regression.current}`,
      );
    }
    process.exitCode = 1;
    return;
  }

  const reference = referenceBaseline(process.env.ZHIJI_EXPLICIT_ANY_BASE_REF);
  const regressions = reference
    ? findExplicitAnyRegressions(baseline, reference)
    : [];
  if (regressions.length > 0) {
    for (const regression of regressions) {
      console.error(
        `${regression.path}: explicit any baseline exceeds target branch `
        + `${regression.baseline} -> ${regression.current}`,
      );
    }
    process.exitCode = 1;
    return;
  }

  const total = Object.values(current).reduce((sum, count) => sum + count, 0);
  console.log(`explicit-any baseline ok: ${total}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
