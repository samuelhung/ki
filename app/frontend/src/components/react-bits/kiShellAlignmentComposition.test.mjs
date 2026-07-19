import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const readPage = (name) => readFileSync(new URL(`../../pages/${name}`, import.meta.url), 'utf8');
const readComponentCss = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

const seriesPage = readPage('CinematicSeries.tsx');
const brainstormPage = readPage('CinematicBrainstorm.tsx');
const detailPage = readPage('BrainstormDetailPage.tsx');
const seriesCss = readComponentCss('cinematic-series/cinematic-series.css');
const brainstormCss = readComponentCss('cinematic-brainstorm/cinematic-brainstorm.css');
const toolboxCss = readComponentCss('cinematic-toolbox/cinematic-toolbox.css');
const systemCss = readComponentCss('cinematic-system/cinematic-system.css');
const chainsCss = readComponentCss('cinematic-chains/cinematic-chains.css');

test('migrated pages use the content-ingest list width at default and compact sizes', () => {
  for (const css of [seriesCss, brainstormCss, toolboxCss, systemCss]) {
    assert.match(css, /--ki-list-width:\s*62%/);
    assert.match(css, /@media \(max-width:\s*1280px\)[\s\S]*--ki-list-width:\s*68%/);
    assert.doesNotMatch(css, /--ki-list-width:\s*(?:70|74|78|82)%/);
  }
});

test('series reserves the same category track above its list as content ingest', () => {
  assert.match(seriesPage, /className="ingest-topic-orbit ki-ingest-topic-orbit series-category-tabs"/);
  assert.match(seriesPage, /<Layers size=\{17\}/);
  assert.match(seriesCss, /\.ki-shell-series \.series-category-tabs\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/s);
});

test('brainstorm detail starts at the shared detail origin and moves actions into the legacy header', () => {
  assert.doesNotMatch(brainstormPage, /brainstorm-detail-toolbar/);
  assert.match(brainstormPage, /embeddedActions=\{/);
  assert.match(detailPage, /embeddedActions\?: React\.ReactNode/);
  assert.match(detailPage, /\{embeddedActions\}/);
  assert.match(brainstormCss, /\.brainstorm-detail-host\s*\{[^}]*height:\s*100%/s);
});

test('toolbox and system content use the same inner edges as content ingest', () => {
  assert.match(toolboxCss, /\.ki-shell-toolbox \.toolbox-detail-reader\s*\{[^}]*width:\s*auto\s*!important[^}]*left:\s*12px\s*!important[^}]*right:\s*0\s*!important/s);
  assert.match(toolboxCss, /@media \(max-width:\s*1280px\)[\s\S]*\.ki-shell-toolbox \.toolbox-detail-reader\s*\{[^}]*left:\s*6px\s*!important/s);
  assert.match(systemCss, /\.ki-shell-system \.system-function-list\s*\{[^}]*padding-top:\s*0/s);
  assert.match(systemCss, /\.ki-shell-system \.cinematic-ingest\.cinematic-system \.system-function-list\s*\{[^}]*padding:\s*0 18px 18px 4px\s*!important/s);
});

test('industry chains keep the shared compact workspace origin', () => {
  assert.doesNotMatch(chainsCss, /\.ki-shell-chains \.ki-shell-content\s*\{[^}]*transform:/s);
});
