import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../pages/CinematicIndustryChains.tsx', import.meta.url), 'utf8');
const legacy = readFileSync(new URL('../../pages/IndustryChains.tsx', import.meta.url), 'utf8');

test('industry chains use the shared cinematic workspace', () => {
  assert.match(page, /CinematicTemplatePage/);
  assert.match(page, /CinematicLaserWorkspace/);
  assert.match(page, /LegacyChainDetail/);
  assert.match(page, /LaserFlow/);
});

test('embedded chain detail only reads cached AI reports on mount', () => {
  assert.match(legacy, /cache_only: embedded && !force/);
});

test('industry chains preserve explicit legacy comparison routes', () => {
  assert.match(app, /path="industry-chains-old"/);
  assert.match(app, /path="chains-old"/);
});
