import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

async function importTypescriptModule(sourcePath) {
  const dir = mkdtempSync(join(tmpdir(), 'ki-cinematic-profile-'));
  const source = readFileSync(sourcePath, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  }).outputText;
  const modulePath = join(dir, 'cinematicSceneProfile.mjs');
  writeFileSync(modulePath, compiled);
  return import(modulePath);
}

const {
  CINEMATIC_SCENE_BASE_VARIANTS,
  resolveCinematicSceneProfile,
} = await importTypescriptModule(new URL('./cinematicSceneProfile.ts', import.meta.url));

test('today keeps the full cinematic scene profile', () => {
  const profile = resolveCinematicSceneProfile('today', { laserPrimary: false });

  assert.equal(profile.particleCount, CINEMATIC_SCENE_BASE_VARIANTS.today.particleCount);
  assert.equal(profile.motion, CINEMATIC_SCENE_BASE_VARIANTS.today.motion);
  assert.equal(profile.maxFps, 60);
});

test('laser-primary pages reduce backdrop load without darkening too far', () => {
  const ingest = resolveCinematicSceneProfile('ingest', { laserPrimary: true });
  const system = resolveCinematicSceneProfile('system', { laserPrimary: true });

  assert.equal(ingest.particleCount, 620);
  assert.equal(system.particleCount, 520);
  assert.equal(ingest.maxFps, 36);
  assert.equal(system.maxFps, 32);
  assert.equal(ingest.globeIntensity, 0.7);
  assert.equal(ingest.terrainIntensity, 2.2);
  assert.ok(ingest.bgIntensity >= 0.8);
  assert.ok(system.bgIntensity >= 0.74);
  assert.ok(ingest.motion < CINEMATIC_SCENE_BASE_VARIANTS.ingest.motion);
  assert.ok(system.motion < CINEMATIC_SCENE_BASE_VARIANTS.system.motion);
});

test('reduced motion keeps a readable static backdrop', () => {
  const profile = resolveCinematicSceneProfile('ingest', {
    laserPrimary: true,
    reducedMotion: true,
  });

  assert.equal(profile.motion, 0);
  assert.equal(profile.pointer, 0);
  assert.equal(profile.maxFps, 24);
  assert.ok(profile.particleCount <= 360);
  assert.ok(profile.bgIntensity >= 0.76);
});

test('constrained runtime lowers cinematic load without disabling motion', () => {
  const profile = resolveCinematicSceneProfile('system', {
    laserPrimary: true,
    constrainedRuntime: true,
  });

  assert.equal(profile.maxFps, 28);
  assert.ok(profile.particleCount <= 440);
  assert.ok(profile.motion > 0);
  assert.ok(profile.pointer > 0);
  assert.ok(profile.bgIntensity >= 0.74);
});
