import assert from 'node:assert/strict';
import test from 'node:test';

import {
  AdaptivePixelRatioController,
  resolveAdaptivePixelRatio,
  resolveFrameCadence,
  resolveShaderOctaves,
} from './cinematicAdaptiveQuality.ts';

function observeMany(controller, count, frameDurationMs, targetFrameMs = 1000 / 60) {
  const changes = [];
  for (let index = 0; index < count; index += 1) {
    const change = controller.observe(frameDurationMs, targetFrameMs);
    if (change !== null) changes.push(change);
  }
  return changes;
}

function observeWindow(controller, fps, targetFps = 60) {
  return observeMany(controller, Math.ceil(fps) + 1, 1000 / fps, 1000 / targetFps);
}

test('two sustained low-fps windows lower pixel ratio one level', () => {
  const controller = new AdaptivePixelRatioController();

  assert.deepEqual(observeWindow(controller, 40), []);
  assert.deepEqual(observeWindow(controller, 40), [0.86]);
  assert.equal(controller.scale, 0.86);
});

test('an isolated long frame inside a healthy window does not lower quality', () => {
  const controller = new AdaptivePixelRatioController();

  observeMany(controller, 59, 1000 / 60);
  controller.observe(180, 1000 / 60);
  observeWindow(controller, 60);

  assert.equal(controller.scale, 1);
});

test('quality only recovers after four stable windows and cooldown', () => {
  const controller = new AdaptivePixelRatioController();
  observeWindow(controller, 40);
  observeWindow(controller, 40);

  const changes = [];
  for (let index = 0; index < 6; index += 1) {
    changes.push(...observeWindow(controller, 60));
  }

  assert.deepEqual(changes, [1]);
  assert.equal(controller.scale, 1);
});

test('a middling window interrupts the consecutive recovery streak', () => {
  const controller = new AdaptivePixelRatioController();
  observeWindow(controller, 40);
  observeWindow(controller, 40);

  observeWindow(controller, 60);
  observeWindow(controller, 60);
  observeWindow(controller, 60);
  observeWindow(controller, 60);
  observeWindow(controller, 60);
  observeWindow(controller, 50);

  assert.deepEqual(observeWindow(controller, 60), []);
  assert.equal(controller.scale, 0.86);
});

test('resetSamples clears timing history without forcing high quality', () => {
  const controller = new AdaptivePixelRatioController();
  observeWindow(controller, 40);
  observeWindow(controller, 40);

  controller.resetSamples();

  assert.equal(controller.scale, 0.86);
  assert.deepEqual(observeWindow(controller, 60), []);
});

test('a full reset ignores the first two startup windows', () => {
  const controller = new AdaptivePixelRatioController();
  controller.reset();

  assert.deepEqual(observeWindow(controller, 30), []);
  assert.deepEqual(observeWindow(controller, 30), []);
  assert.equal(controller.scale, 1);
});

test('adaptive scale can lower an already constrained base ratio without changing default quality', () => {
  assert.equal(resolveAdaptivePixelRatio(0.75, 1), 0.75);
  assert.equal(resolveAdaptivePixelRatio(0.75, 0.86), 0.645);
  assert.equal(resolveAdaptivePixelRatio(0.75, 0.72), 0.6);
});

test('shader octaves step down with the adaptive quality tier', () => {
  assert.deepEqual(resolveShaderOctaves(1), { background: 6, signal: 5 });
  assert.deepEqual(resolveShaderOctaves(0.86), { background: 5, signal: 4 });
  assert.deepEqual(resolveShaderOctaves(0.72), { background: 4, signal: 3 });
});

test('frame cadence preserves a 28 fps target on a 30 hz animation clock', () => {
  const minFrameMs = 1000 / 28;
  let nextRenderAtMs = minFrameMs;
  let renderedFrames = 0;

  for (let frame = 1; frame <= 30; frame += 1) {
    const result = resolveFrameCadence(nextRenderAtMs, frame * (1000 / 30), minFrameMs);
    nextRenderAtMs = result.nextRenderAtMs;
    if (result.shouldRender) renderedFrames += 1;
  }

  assert.equal(renderedFrames, 28);
});
