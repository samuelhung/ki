const QUALITY_SCALES = [1, 0.86, 0.72] as const;
const SAMPLE_WINDOW_MS = 1000;
const DOWNGRADE_FPS_RATIO = 0.8;
const RECOVERY_FPS_RATIO = 0.92;
const SLOW_WINDOW_LIMIT = 2;
const STABLE_WINDOW_LIMIT = 4;
const CHANGE_COOLDOWN_WINDOWS = 2;

export function resolveFrameCadence(nextRenderAtMs: number, nowMs: number, minFrameMs: number) {
  if (nowMs + 0.01 < nextRenderAtMs) {
    return { shouldRender: false, nextRenderAtMs };
  }

  const missedIntervals = Math.floor(Math.max(0, nowMs - nextRenderAtMs) / minFrameMs) + 1;
  return {
    shouldRender: true,
    nextRenderAtMs: nextRenderAtMs + missedIntervals * minFrameMs,
  };
}

export function resolveAdaptivePixelRatio(basePixelRatio: number, qualityScale: number) {
  if (qualityScale >= 1) return basePixelRatio;
  return Math.max(0.6, Number((basePixelRatio * qualityScale).toFixed(3)));
}

export function resolveShaderOctaves(qualityScale: number) {
  if (qualityScale >= 0.99) return { background: 6, signal: 5 };
  if (qualityScale >= 0.8) return { background: 5, signal: 4 };
  return { background: 4, signal: 3 };
}

export class AdaptivePixelRatioController {
  private level = 0;
  private sampleDurationMs = 0;
  private sampleCount = 0;
  private slowWindows = 0;
  private stableWindows = 0;
  private cooldownWindows = 0;

  get scale() {
    return QUALITY_SCALES[this.level];
  }

  observe(frameDurationMs: number, targetFrameMs: number): number | null {
    if (!Number.isFinite(frameDurationMs) || frameDurationMs <= 0) return null;
    this.sampleDurationMs += frameDurationMs;
    this.sampleCount += 1;
    if (this.sampleDurationMs < SAMPLE_WINDOW_MS) return null;

    const measuredFps = this.sampleCount * 1000 / this.sampleDurationMs;
    const targetFps = 1000 / Math.max(1, targetFrameMs);
    this.clearWindow();

    if (this.cooldownWindows > 0) {
      this.cooldownWindows -= 1;
      return null;
    }

    if (measuredFps < targetFps * DOWNGRADE_FPS_RATIO) {
      this.slowWindows += 1;
      this.stableWindows = 0;
      if (this.slowWindows >= SLOW_WINDOW_LIMIT && this.level < QUALITY_SCALES.length - 1) {
        this.level += 1;
        this.afterChange();
        return this.scale;
      }
      return null;
    }

    this.slowWindows = 0;
    if (measuredFps >= targetFps * RECOVERY_FPS_RATIO && this.level > 0) {
      this.stableWindows += 1;
      if (this.stableWindows >= STABLE_WINDOW_LIMIT) {
        this.level -= 1;
        this.afterChange();
        return this.scale;
      }
    } else {
      this.stableWindows = 0;
    }
    return null;
  }

  resetSamples() {
    this.clearWindow();
    this.slowWindows = 0;
    this.stableWindows = 0;
  }

  reset() {
    this.level = 0;
    this.cooldownWindows = CHANGE_COOLDOWN_WINDOWS;
    this.resetSamples();
  }

  private afterChange() {
    this.cooldownWindows = CHANGE_COOLDOWN_WINDOWS;
    this.resetSamples();
  }

  private clearWindow() {
    this.sampleDurationMs = 0;
    this.sampleCount = 0;
  }
}
