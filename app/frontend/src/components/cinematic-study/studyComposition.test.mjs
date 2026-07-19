import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const pageUrl = new URL('../../pages/CinematicStudy.tsx', import.meta.url);
const detailUrl = new URL('../../pages/StudyDetail.tsx', import.meta.url);
const appUrl = new URL('../../App.tsx', import.meta.url);

test('study composes the shared cinematic shell and embeds legacy detail', async () => {
  const [page, detail] = await Promise.all([readFile(pageUrl, 'utf8'), readFile(detailUrl, 'utf8')]);
  assert.match(page, /<CinematicTemplatePage/);
  assert.match(page, /<CinematicLaserWorkspace/);
  assert.match(page, /<LegacyStudyDetail embedded/);
  assert.match(detail, /embedded\?: boolean/);
});

test('study keeps production list detail and mistakes routes', async () => {
  const app = await readFile(appUrl, 'utf8');
  assert.match(app, /path="study" element={<CinematicStudy/);
  assert.match(app, /path="study\/:id" element={<CinematicStudy/);
  assert.match(app, /path="study-mistakes" element={<CinematicStudy/);
});
