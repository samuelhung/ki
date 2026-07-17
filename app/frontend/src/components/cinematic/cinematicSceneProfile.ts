export type CinematicSceneVariant = 'today' | 'ingest' | 'system';

export interface CinematicSceneProfile {
  className: string;
  pixelRatioScale: number;
  particleCount: number;
  bgIntensity: number;
  globeIntensity: number;
  terrainIntensity: number;
  signalIntensity: number;
  particleIntensity: number;
  motion: number;
  pointer: number;
  earthPosition: [number, number, number];
  earthScale: number;
  maxFps: number;
}

export const CINEMATIC_SCENE_BASE_VARIANTS: Record<CinematicSceneVariant, CinematicSceneProfile> = {
  today: {
    className: '',
    pixelRatioScale: 1,
    particleCount: 1250,
    bgIntensity: 1,
    globeIntensity: 1,
    terrainIntensity: 1,
    signalIntensity: 1,
    particleIntensity: 1,
    motion: 1,
    pointer: 1,
    earthPosition: [3.08, 0.03, -3.18],
    earthScale: 1,
    maxFps: 60,
  },
  ingest: {
    className: 'is-ingest-backdrop',
    pixelRatioScale: 0.78,
    particleCount: 1080,
    bgIntensity: 0.9,
    globeIntensity: 0.78,
    terrainIntensity: 0.62,
    signalIntensity: 0.58,
    particleIntensity: 0.84,
    motion: 0.74,
    pointer: 0.58,
    earthPosition: [3.7, -0.04, -3.62],
    earthScale: 0.9,
    maxFps: 48,
  },
  system: {
    className: 'is-system-backdrop',
    pixelRatioScale: 0.74,
    particleCount: 980,
    bgIntensity: 0.82,
    globeIntensity: 0.68,
    terrainIntensity: 0.52,
    signalIntensity: 0.48,
    particleIntensity: 0.74,
    motion: 0.58,
    pointer: 0.46,
    earthPosition: [3.82, 0.06, -3.72],
    earthScale: 0.84,
    maxFps: 44,
  },
};

const LASER_PRIMARY_OVERRIDES: Partial<Record<CinematicSceneVariant, Partial<CinematicSceneProfile>>> = {
  ingest: {
    pixelRatioScale: 0.58,
    particleCount: 620,
    globeIntensity: 0.7,
    terrainIntensity: 2.2,
    signalIntensity: 0.34,
    particleIntensity: 0.58,
    motion: 0.34,
    pointer: 0.28,
    maxFps: 36,
  },
  system: {
    pixelRatioScale: 0.54,
    particleCount: 520,
    globeIntensity: 0.5,
    terrainIntensity: 0.36,
    signalIntensity: 0.3,
    particleIntensity: 0.5,
    motion: 0.28,
    pointer: 0.22,
    maxFps: 32,
  },
};

export function resolveCinematicSceneProfile(
  variant: CinematicSceneVariant,
  options: { laserPrimary?: boolean; reducedMotion?: boolean; constrainedRuntime?: boolean } = {},
): CinematicSceneProfile {
  const base = CINEMATIC_SCENE_BASE_VARIANTS[variant];
  const laserOverride = options.laserPrimary ? LASER_PRIMARY_OVERRIDES[variant] || {} : {};
  let profile = { ...base, ...laserOverride };

  if (options.constrainedRuntime && !options.reducedMotion) {
    profile = {
      ...profile,
      pixelRatioScale: Math.min(profile.pixelRatioScale, 0.62),
      particleCount: Math.min(profile.particleCount, options.laserPrimary ? 440 : 720),
      signalIntensity: profile.signalIntensity * 0.86,
      particleIntensity: profile.particleIntensity * 0.86,
      motion: profile.motion * 0.72,
      pointer: profile.pointer * 0.7,
      maxFps: Math.min(profile.maxFps, 28),
    };
  }

  if (!options.reducedMotion) return profile;

  return {
    ...profile,
    pixelRatioScale: Math.min(profile.pixelRatioScale, 0.48),
    particleCount: Math.min(profile.particleCount, 340),
    globeIntensity: profile.globeIntensity * 0.82,
    terrainIntensity: profile.terrainIntensity * 0.78,
    signalIntensity: profile.signalIntensity * 0.76,
    particleIntensity: profile.particleIntensity * 0.74,
    motion: 0,
    pointer: 0,
    maxFps: 24,
  };
}
