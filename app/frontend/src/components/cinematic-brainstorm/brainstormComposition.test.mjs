import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicBrainstorm.tsx', import.meta.url), 'utf8');

test('brainstorm composes the shared cinematic shell and embedded detail', () => {
  assert.match(page, /CinematicTemplatePage/);
  assert.match(page, /CinematicLaserWorkspace/);
  assert.match(page, /LegacyBrainstormDetail/);
  assert.match(page, /LaserFlow/);
});

test('brainstorm preserves explicit legacy routes', () => {
  assert.match(app, /path="brainstorm-old"/);
  assert.match(app, /path="brainstorm-old\/:id"/);
});
