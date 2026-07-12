import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicLibrary.tsx', import.meta.url), 'utf8');

test('library composes the cinematic shell with shared content detail', () => {
  assert.match(page, /CinematicTemplatePage/);
  assert.match(page, /CinematicLaserWorkspace/);
  assert.match(page, /ContentDetailPanel/);
  assert.match(page, /library-core-box/);
});

test('events and sources share the new workspace while legacy routes remain explicit', () => {
  assert.match(app, /path="events" element={<CinematicLibrary/);
  assert.match(app, /path="sources" element={<CinematicLibrary/);
  assert.match(app, /path="events-old" element={<Events/);
  assert.match(app, /path="sources-old" element={<Sources/);
});
