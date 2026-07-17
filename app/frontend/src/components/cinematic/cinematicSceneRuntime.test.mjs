import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const scene = readFileSync(new URL('./CinematicScene.tsx', import.meta.url), 'utf8');
const runtime = readFileSync(new URL('./cinematicSceneRuntime.ts', import.meta.url), 'utf8');
const provider = readFileSync(new URL('./CinematicBackdropContext.tsx', import.meta.url), 'utf8');

test('the persistent scene owns one renderer and caches profile runtimes', () => {
  assert.match(scene, /new THREE\.WebGLRenderer/);
  assert.equal((scene.match(/new THREE\.WebGLRenderer/g) || []).length, 1);
  assert.match(scene, /new CinematicSceneRuntimeCache/);
  assert.match(scene, /getOrCreate\(/);
  assert.match(scene, /Renderer and event lifecycle intentionally span profile changes/);
  assert.match(runtime, /class CinematicSceneRuntimeCache/);
  assert.match(runtime, /private readonly runtimes = new Map/);
});

test('visibility and context lifecycle reset the animation time base', () => {
  assert.match(scene, /document\.hidden \? stopAnimation\(\) : startAnimation\(\)/);
  assert.match(scene, /resetTimeBase\(\)/);
  assert.match(scene, /webglcontextlost/);
  assert.match(scene, /webglcontextrestored/);
  assert.match(scene, /Math\.min\(0\.05,/);
});

test('canvas resize observes its stable host and defers renderer writes', () => {
  assert.match(scene, /const resizeTarget = canvas\.parentElement \|\| canvas/);
  assert.match(scene, /const scheduleResize = \(\) =>/);
  assert.match(scene, /resizeFrame = requestAnimationFrame/);
  assert.match(scene, /resizeObserver\.observe\(resizeTarget\)/);
  assert.match(scene, /if \(resizeFrame\) cancelAnimationFrame\(resizeFrame\)/);
  assert.doesNotMatch(scene, /new ResizeObserver\(resize\)/);
});

test('active state owns the animation loop instead of skipping inside raf', () => {
  assert.match(scene, /activeRef\.current \? animationControllerRef\.current\?\.start\(\) : animationControllerRef\.current\?\.stop\(\)/);
  assert.doesNotMatch(scene, /if \(!runtime \|\| !activeRef\.current\) return/);
  assert.match(scene, /if \(!activeRef\.current \|\| running \|\| contextLost \|\| document\.hidden\) return/);
  assert.match(scene, /if \(!activeRef\.current\) return;\s*const rect = canvas\.getBoundingClientRect\(\)/);
});

test('scene publishes throttled renderer counters for performance qa', () => {
  assert.match(scene, /lastMetricsPublish/);
  assert.match(scene, /renderer\.info\.render/);
  assert.match(scene, /canvas\.dataset\.renderCalls/);
  assert.match(scene, /canvas\.dataset\.renderTriangles/);
  assert.match(scene, /canvas\.dataset\.renderLines/);
  assert.match(scene, /canvas\.dataset\.renderPoints/);
  assert.match(scene, /canvas\.dataset\.renderFps/);
  assert.match(scene, /renderedFrames/);
  assert.match(scene, /WEBGL_debug_renderer_info/);
  assert.match(scene, /canvas\.dataset\.gpuRenderer/);
  assert.match(scene, /canvas\.dataset\.gpuVendor/);
});

test('scene adapts pixel ratio from sustained frame timing without changing scene density', () => {
  assert.match(scene, /new AdaptivePixelRatioController/);
  assert.match(scene, /resolveAdaptivePixelRatio\(pixelRatioCap\(runtime\.pixelRatioScale\), adaptiveQualityRef\.current\.scale\)/);
  assert.match(scene, /adaptiveQuality\.observe\(frameDurationMs, minFrameMs\)/);
  assert.match(scene, /canvas\.dataset\.qualityScale/);
  assert.match(scene, /adaptiveQuality\.resetSamples\(\)/);
  assert.doesNotMatch(scene, /particleCount\s*=/);
});

test('runtime capability detection does not treat privacy-limited cpu counts as weak hardware', () => {
  assert.doesNotMatch(scene, /navigator\.hardwareConcurrency/);
  assert.doesNotMatch(scene, /connection\?\.saveData/);
  assert.match(scene, /compactViewport/);
});

test('adaptive quality also lowers shader work without changing scene composition', () => {
  assert.match(runtime, /setQualityScale\(scale: number\)/);
  assert.match(runtime, /resolveShaderOctaves\(scale\)/);
  assert.match(runtime, /bgMaterial\.defines\.CINEMATIC_OCTAVES/);
  assert.match(runtime, /signalMaterial\.defines\.CINEMATIC_OCTAVES/);
  assert.match(runtime, /bgMaterial\.needsUpdate = true/);
  assert.match(runtime, /signalMaterial\.needsUpdate = true/);
  assert.match(scene, /runtime\.setQualityScale\(adaptiveQuality\.scale\)/);
  assert.doesNotMatch(scene, /runtime\.particleCount/);
});

test('provider keeps the canvas mounted when route requests clear', () => {
  assert.match(provider, /const activeRequest = request \|\|/);
  assert.match(provider, /<CinematicScene/);
  assert.match(provider, /active=\{Boolean\(request\)\}/);
  assert.doesNotMatch(provider, /\{request && \(/);
});

test('provider memoizes its public context value', () => {
  assert.match(provider, /useMemo/);
  assert.match(provider, /const contextValue = useMemo\(\(\) => \(\{ setBackdrop \}\), \[setBackdrop\]\)/);
  assert.match(provider, /value=\{contextValue\}/);
});

test('runtime disposal is idempotent and deduplicates shared resources', () => {
  assert.match(runtime, /if \(disposed\) return/);
  assert.match(runtime, /const geometries = new Set/);
  assert.match(runtime, /const materials = new Set/);
  assert.match(runtime, /this\.runtimes\.forEach\(\(runtime\) => runtime\.dispose\(\)\)/);
});

test('terrain avoids the large transparent line-segment slow path', () => {
  assert.match(runtime, /terrain\.add\(makeLine/);
  assert.doesNotMatch(runtime, /terrainBatchPositions/);
  assert.doesNotMatch(runtime, /terrain\.add\(new THREE\.LineSegments/);
});
