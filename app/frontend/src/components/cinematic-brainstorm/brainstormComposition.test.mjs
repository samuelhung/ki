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

test('brainstorm bypasses the global curtain on initial and internal navigation', () => {
  assert.match(app, /location\.pathname === '\/brainstorm'/);
  assert.match(app, /location\.pathname\.startsWith\('\/brainstorm\/'\)/);
  assert.match(curtain, /pathname === '\/brainstorm'/);
  assert.match(curtain, /pathname\.startsWith\('\/brainstorm\/'\)/);
});

test('brainstorm exposes four focused topic tabs and defaults to 格局', () => {
  const topicConfig = page.match(/const TOPICS = \[([\s\S]*?)\] as const;/)?.[1] || '';

  assert.doesNotMatch(topicConfig, /key: '全部'/);
  assert.match(topicConfig, /key: '格局'/);
  assert.match(topicConfig, /key: '财富'/);
  assert.match(topicConfig, /key: '认知'/);
  assert.match(topicConfig, /key: '前瞻'/);
  assert.match(page, /useState<TopicKey>\('格局'\)/);
});
