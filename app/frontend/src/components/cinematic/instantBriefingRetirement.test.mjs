import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const panels = readFileSync(new URL('../cinematic-system/SystemCenterPanels.tsx', import.meta.url), 'utf8');
const curtain = readFileSync(new URL('../../CurtainContext.tsx', import.meta.url), 'utf8');
const types = readFileSync(new URL('../../types.ts', import.meta.url), 'utf8');
const pagesQa = readFileSync(new URL('../../../scripts/qa-cinematic-pages-core.mjs', import.meta.url), 'utf8');
const productionPagesQa = readFileSync(new URL('../../../scripts/qa-cinematic-pages-production.mjs', import.meta.url), 'utf8');
const journeyQa = readFileSync(new URL('../../../scripts/qa-cinematic-user-path.mjs', import.meta.url), 'utf8');
const explicitAnyBaseline = readFileSync(new URL('../../../explicit-any-baseline.json', import.meta.url), 'utf8');
const ingestLayoutCss = readFileSync(new URL('../cinematic-ingest/cinematic-ingest-react-bits-layout.css', import.meta.url), 'utf8');

test('instant briefing frontend is retired', () => {
  assert.doesNotMatch(app, /CinematicBriefings|\/briefings/);
  assert.doesNotMatch(shell, /即时快报|\/briefings/);
  assert.doesNotMatch(panels, /briefing_quick|briefing_daily|即时快报/);
  assert.doesNotMatch(curtain, /\/briefings/);
  assert.doesNotMatch(types, /BriefingEvent|BriefingTopic|interface Briefing/);
  assert.doesNotMatch(pagesQa, /\/briefings|briefing_|Briefing|快报/);
  assert.doesNotMatch(journeyQa, /\/briefings|briefing_|Briefing|快报/);
  assert.doesNotMatch(explicitAnyBaseline, /CinematicBriefings/);
  assert.equal(existsSync(new URL('../../pages/CinematicBriefings.tsx', import.meta.url)), false);
  assert.equal(existsSync(new URL('../cinematic-briefings', import.meta.url)), false);
});

test('production cinematic QA does not request the retired briefing page', () => {
  assert.doesNotMatch(productionPagesQa, /['"]briefings['"]/);
});

test('runtime ingest CSS does not retain the retired briefing stream selector', () => {
  assert.doesNotMatch(ingestLayoutCss, /\.briefing-stream/);
});
