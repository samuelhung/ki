import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
const shell = readFileSync(new URL('../../pages/KiNavigationShell.tsx', import.meta.url), 'utf8');
const panels = readFileSync(new URL('../cinematic-system/SystemCenterPanels.tsx', import.meta.url), 'utf8');

test('instant briefing frontend is retired', () => {
  assert.doesNotMatch(app, /CinematicBriefings|\/briefings/);
  assert.doesNotMatch(shell, /即时快报|\/briefings/);
  assert.doesNotMatch(panels, /briefing_quick|briefing_daily|即时快报/);
  assert.equal(existsSync(new URL('../../pages/CinematicBriefings.tsx', import.meta.url)), false);
  assert.equal(existsSync(new URL('../cinematic-briefings', import.meta.url)), false);
});
