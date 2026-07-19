import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicBrainstorm.tsx', import.meta.url), 'utf8');
const css = readFileSync(new URL('./cinematic-brainstorm.css', import.meta.url), 'utf8');

test('brainstorm composes the finalized KI split workspace and embedded detail', () => {
  assert.match(page, /<KiNavigationShell/);
  assert.match(page, /ki-ingest-split-stage/);
  assert.match(page, /ki-ingest-list-pane/);
  assert.match(page, /ki-ingest-detail-pane/);
  assert.match(page, /<SpotlightListRow/);
  assert.match(page, /topAccessory=/);
  assert.match(page, /lazy\(\(\) => import\('\.\/BrainstormDetailPage'\)\)/);
  assert.match(page, /<LegacyBrainstormDetail\s+embedded/);
  assert.doesNotMatch(page, /CinematicTemplatePage|CinematicLaserWorkspace|LaserFlow/);
  assert.match(css, /\.brainstorm-detail-embedded\s*\{[^}]*position:\s*relative/s);
});

test('brainstorm preserves explicit legacy routes', () => {
  assert.match(app, /path="brainstorm-old"/);
  assert.match(app, /path="brainstorm-old\/:id"/);
});

test('brainstorm bypasses the global curtain on initial and internal navigation', () => {
  assert.match(app, /location\.pathname === '\/brainstorm'/);
  assert.match(app, /location\.pathname\.startsWith\('\/brainstorm\/'\)/);
  assert.match(curtain, /pathname === '\/brainstorm'/);
  assert.match(curtain, /pathname\.startsWith\('\/brainstorm\/'\)/);
});
