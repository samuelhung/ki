import { useEffect, useMemo, useRef } from 'react';
import * as THREE from 'three';
import {
  CINEMATIC_SCENE_BASE_VARIANTS,
  resolveCinematicSceneProfile,
  type CinematicSceneVariant,
} from './cinematicSceneProfile';
import {
  CinematicSceneRuntimeCache,
  createCinematicSceneRuntime,
  type CinematicPointer,
  type CinematicSceneRuntime,
} from './cinematicSceneRuntime';
import {
  AdaptivePixelRatioController,
  resolveAdaptivePixelRatio,
  resolveFrameCadence,
  resolveShaderOctaves,
} from './cinematicAdaptiveQuality';

interface Props {
  focus: number;
  variant?: CinematicSceneVariant;
  laserPrimary?: boolean;
  active?: boolean;
}

function pixelRatioCap(scale = 1) {
  const cap = window.innerWidth < 1440 ? 1.5 : Math.min(window.devicePixelRatio, 2);
  return Math.max(0.75, cap * scale);
}

function isConstrainedRuntime() {
  const compactViewport = window.innerWidth < 1180 || window.innerHeight < 820;
  return compactViewport;
}

function getCanvasSize(canvas: HTMLCanvasElement) {
  const rect = canvas.getBoundingClientRect();
  return {
    width: Math.max(1, Math.floor(rect.width || canvas.parentElement?.clientWidth || window.innerWidth)),
    height: Math.max(1, Math.floor(rect.height || canvas.parentElement?.clientHeight || window.innerHeight)),
  };
}

export default function CinematicScene({ focus, variant = 'today', laserPrimary = false, active = true }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const runtimeCacheRef = useRef(new CinematicSceneRuntimeCache());
  const activeRuntimeRef = useRef<CinematicSceneRuntime | null>(null);
  const adaptiveQualityRef = useRef(new AdaptivePixelRatioController());
  const focusRef = useRef(focus);
  const activeRef = useRef(active);
  const animationControllerRef = useRef<{ start: () => void; stop: () => void } | null>(null);
  const pointerRef = useRef<CinematicPointer>({ x: 0, y: 0 });
  const variantConfig = CINEMATIC_SCENE_BASE_VARIANTS[variant];
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );
  const constrainedRuntime = useMemo(() => typeof window !== 'undefined' && isConstrainedRuntime(), []);
  const runtimeKey = `${variant}:${laserPrimary ? 1 : 0}:${reducedMotion ? 1 : 0}:${constrainedRuntime ? 1 : 0}`;

  useEffect(() => {
    focusRef.current = focus;
  }, [focus]);

  useEffect(() => {
    activeRef.current = active;
    activeRef.current ? animationControllerRef.current?.start() : animationControllerRef.current?.stop();
  }, [active]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const renderer = rendererRef.current;
    if (!canvas || !renderer) return;
    const config = resolveCinematicSceneProfile(variant, { laserPrimary, reducedMotion, constrainedRuntime });
    const size = getCanvasSize(canvas);
    const runtime = runtimeCacheRef.current.getOrCreate(
      runtimeKey,
      () => createCinematicSceneRuntime(runtimeKey, config, size),
    );
    activeRuntimeRef.current = runtime;
    adaptiveQualityRef.current.reset();
    runtime.setQualityScale(adaptiveQualityRef.current.scale);
    renderer.setPixelRatio(resolveAdaptivePixelRatio(pixelRatioCap(runtime.pixelRatioScale), adaptiveQualityRef.current.scale));
    renderer.setSize(size.width, size.height, false);
    runtime.resize(size.width, size.height);
    runtime.resetClock();
  }, [constrainedRuntime, laserPrimary, reducedMotion, runtimeKey, variant]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resizeTarget = canvas.parentElement || canvas;
    const adaptiveQuality = adaptiveQualityRef.current;

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: false,
      powerPreference: 'high-performance',
    });
    rendererRef.current = renderer;
    renderer.setClearColor(0x020203, 1);
    const gl = renderer.getContext();
    const debugRendererInfo = gl.getExtension('WEBGL_debug_renderer_info');
    canvas.dataset.gpuRenderer = String(gl.getParameter(
      debugRendererInfo?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER,
    ));
    canvas.dataset.gpuVendor = String(gl.getParameter(
      debugRendererInfo?.UNMASKED_VENDOR_WEBGL ?? gl.VENDOR,
    ));

    let frame = 0;
    let running = false;
    let contextLost = false;
    let nextRenderAt = 0;
    let lastSceneFrame = 0;
    let lastMetricsPublish = performance.now();
    let renderedFrames = 0;
    let sceneTime = 0;
    let resizeFrame = 0;

    const ensureActiveRuntime = () => {
      const config = resolveCinematicSceneProfile(variant, { laserPrimary, reducedMotion, constrainedRuntime });
      const size = getCanvasSize(canvas);
      const runtime = runtimeCacheRef.current.getOrCreate(
        runtimeKey,
        () => createCinematicSceneRuntime(runtimeKey, config, size),
      );
      activeRuntimeRef.current = runtime;
      return runtime;
    };

    const resize = () => {
      const runtime = activeRuntimeRef.current || ensureActiveRuntime();
      const size = getCanvasSize(canvas);
      renderer.setPixelRatio(resolveAdaptivePixelRatio(pixelRatioCap(runtime.pixelRatioScale), adaptiveQualityRef.current.scale));
      renderer.setSize(size.width, size.height, false);
      runtime.resize(size.width, size.height);
    };

    const scheduleResize = () => {
      if (resizeFrame) return;
      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = 0;
        resize();
      });
    };

    const resetTimeBase = () => {
      const now = performance.now();
      const runtime = activeRuntimeRef.current;
      nextRenderAt = now + (1000 / Math.max(1, runtime?.maxFps || 60));
      lastSceneFrame = now;
      lastMetricsPublish = now;
      renderedFrames = 0;
      adaptiveQuality.resetSamples();
      activeRuntimeRef.current?.resetClock();
    };

    const stopAnimation = () => {
      running = false;
      cancelAnimationFrame(frame);
      frame = 0;
      lastSceneFrame = 0;
    };

    const animate = (now = performance.now()) => {
      if (!running) return;
      frame = requestAnimationFrame(animate);
      const runtime = activeRuntimeRef.current;
      if (!runtime) return;
      const minFrameMs = 1000 / Math.max(1, runtime.maxFps);
      const cadence = resolveFrameCadence(nextRenderAt, now, minFrameMs);
      if (!cadence.shouldRender) return;
      nextRenderAt = cadence.nextRenderAtMs;
      const frameDurationMs = lastSceneFrame === 0 ? minFrameMs : now - lastSceneFrame;
      const deltaSeconds = Math.max(0, Math.min(0.05, frameDurationMs / 1000));
      lastSceneFrame = now;
      sceneTime += deltaSeconds;
      runtime.update(deltaSeconds, sceneTime, pointerRef.current, focusRef.current || 0);
      runtime.render(renderer);
      renderedFrames += 1;
      if (adaptiveQuality.observe(frameDurationMs, minFrameMs) !== null) {
        runtime.setQualityScale(adaptiveQuality.scale);
        canvas.dataset.qualityScale = String(adaptiveQuality.scale);
        const shaderOctaves = resolveShaderOctaves(adaptiveQuality.scale);
        canvas.dataset.shaderOctaves = `${shaderOctaves.background}/${shaderOctaves.signal}`;
        scheduleResize();
      }
      if (now - lastMetricsPublish >= 1000) {
        const metricsElapsed = now - lastMetricsPublish;
        const renderInfo = renderer.info.render;
        canvas.dataset.renderCalls = String(renderInfo.calls);
        canvas.dataset.renderTriangles = String(renderInfo.triangles);
        canvas.dataset.renderLines = String(renderInfo.lines);
        canvas.dataset.renderPoints = String(renderInfo.points);
        canvas.dataset.qualityScale = String(adaptiveQuality.scale);
        const shaderOctaves = resolveShaderOctaves(adaptiveQuality.scale);
        canvas.dataset.shaderOctaves = `${shaderOctaves.background}/${shaderOctaves.signal}`;
        canvas.dataset.pixelRatio = renderer.getPixelRatio().toFixed(2);
        canvas.dataset.renderFps = (renderedFrames * 1000 / metricsElapsed).toFixed(2);
        renderedFrames = 0;
        lastMetricsPublish = now;
      }
    };

    const startAnimation = () => {
      if (!activeRef.current || running || contextLost || document.hidden) return;
      running = true;
      resetTimeBase();
      resize();
      frame = requestAnimationFrame(animate);
    };

    const onPointerMove = (event: PointerEvent) => {
      if (!activeRef.current) return;
      const rect = canvas.getBoundingClientRect();
      pointerRef.current.x = (event.clientX - rect.left) / Math.max(1, rect.width) - 0.5;
      pointerRef.current.y = (event.clientY - rect.top) / Math.max(1, rect.height) - 0.5;
    };
    const onVisibilityChange = () => document.hidden ? stopAnimation() : startAnimation();
    const onPageResume = () => startAnimation();
    const onContextLost = (event: Event) => {
      event.preventDefault();
      contextLost = true;
      stopAnimation();
    };
    const onContextRestored = () => {
      contextLost = false;
      resize();
      startAnimation();
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    document.addEventListener('visibilitychange', onVisibilityChange, { passive: true });
    window.addEventListener('focus', onPageResume, { passive: true });
    window.addEventListener('pageshow', onPageResume, { passive: true });
    canvas.addEventListener('webglcontextlost', onContextLost);
    canvas.addEventListener('webglcontextrestored', onContextRestored);
    const resizeObserver = new ResizeObserver(scheduleResize);
    resizeObserver.observe(resizeTarget);
    animationControllerRef.current = { start: startAnimation, stop: stopAnimation };
    ensureActiveRuntime();
    startAnimation();

    return () => {
      stopAnimation();
      animationControllerRef.current = null;
      window.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('focus', onPageResume);
      window.removeEventListener('pageshow', onPageResume);
      canvas.removeEventListener('webglcontextlost', onContextLost);
      canvas.removeEventListener('webglcontextrestored', onContextRestored);
      resizeObserver.disconnect();
      if (resizeFrame) cancelAnimationFrame(resizeFrame);
      runtimeCacheRef.current.dispose();
      activeRuntimeRef.current = null;
      renderer.dispose();
      rendererRef.current = null;
    };
  // Renderer and event lifecycle intentionally span profile changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <canvas ref={canvasRef} className={`cinematic-scene-canvas ${variantConfig.className}`} aria-hidden="true" />;
}
