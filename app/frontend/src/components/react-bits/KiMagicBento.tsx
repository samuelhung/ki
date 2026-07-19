import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react';
import { gsap } from 'gsap';
import './KiMagicBento.css';

const DEFAULT_PARTICLE_COUNT = 12;
const DEFAULT_SPOTLIGHT_RADIUS = 300;
const DEFAULT_GLOW_COLOR = '132, 0, 255';
const DEFAULT_TILT_MAX = 10;
const DEFAULT_MAGNETISM_STRENGTH = 0.05;
const MOBILE_BREAKPOINT = 768;

interface MagicBentoConfig {
  disableAnimations: boolean;
  particleCount: number;
  spotlightRadius: number;
  glowColor: string;
  enableTilt: boolean;
  clickEffect: boolean;
  enableMagnetism: boolean;
  tiltMax: number;
  magnetismStrength: number;
  suspendSelector?: string;
}

interface MagicBentoGridProps {
  children: ReactNode;
  className?: string;
  disableAnimations?: boolean;
  particleCount?: number;
  spotlightRadius?: number;
  glowColor?: string;
  enableTilt?: boolean;
  clickEffect?: boolean;
  enableMagnetism?: boolean;
  tiltMax?: number;
  magnetismStrength?: number;
  suspendSelector?: string;
}

interface MagicBentoCardProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

const MagicBentoContext = createContext<MagicBentoConfig>({
  disableAnimations: false,
  particleCount: DEFAULT_PARTICLE_COUNT,
  spotlightRadius: DEFAULT_SPOTLIGHT_RADIUS,
  glowColor: DEFAULT_GLOW_COLOR,
  enableTilt: true,
  clickEffect: true,
  enableMagnetism: true,
  tiltMax: DEFAULT_TILT_MAX,
  magnetismStrength: DEFAULT_MAGNETISM_STRENGTH,
  suspendSelector: undefined,
});

function createParticleElement(x: number, y: number, color: string): HTMLDivElement {
  const element = document.createElement('div');
  element.className = 'ki-magic-particle';
  element.style.cssText = `
    position: absolute;
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: rgba(${color}, 1);
    box-shadow: 0 0 6px rgba(${color}, 0.6);
    pointer-events: none;
    z-index: 100;
    left: ${x}px;
    top: ${y}px;
  `;
  return element;
}

function calculateSpotlightValues(radius: number) {
  return { proximity: radius * 0.5, fadeDistance: radius * 0.75 };
}

function updateCardGlowProperties(
  card: HTMLElement,
  rect: DOMRect,
  pointerX: number,
  pointerY: number,
  glow: number,
  radius: number,
) {
  const relativeX = ((pointerX - rect.left) / rect.width) * 100;
  const relativeY = ((pointerY - rect.top) / rect.height) * 100;
  card.style.setProperty('--glow-x', `${relativeX}%`);
  card.style.setProperty('--glow-y', `${relativeY}%`);
  card.style.setProperty('--glow-intensity', glow.toString());
  card.style.setProperty('--glow-radius', `${radius}px`);
}

function useAnimationDisabled() {
  const [disabled, setDisabled] = useState(false);

  useEffect(() => {
    const query = window.matchMedia(
      `(max-width: ${MOBILE_BREAKPOINT}px), (pointer: coarse), (prefers-reduced-motion: reduce)`,
    );
    const update = () => setDisabled(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return disabled;
}

function GlobalSpotlight({ gridRef, config }: { gridRef: React.RefObject<HTMLDivElement | null>; config: MagicBentoConfig }) {
  useEffect(() => {
    const grid = gridRef.current;
    if (config.disableAnimations || !grid) return;

    const spotlight = document.createElement('div');
    spotlight.className = 'ki-global-spotlight';
    spotlight.style.cssText = `
      position: fixed;
      width: 800px;
      height: 800px;
      border-radius: 50%;
      pointer-events: none;
      background: radial-gradient(circle,
        rgba(${config.glowColor}, 0.15) 0%,
        rgba(${config.glowColor}, 0.08) 15%,
        rgba(${config.glowColor}, 0.04) 25%,
        rgba(${config.glowColor}, 0.02) 40%,
        rgba(${config.glowColor}, 0.01) 65%,
        transparent 70%
      );
      z-index: 200;
      opacity: 0;
      transform: translate(-50%, -50%);
      mix-blend-mode: screen;
    `;
    document.body.appendChild(spotlight);

    const cards = grid.querySelectorAll<HTMLElement>('.ki-magic-bento-card');
    const leftTo = gsap.quickTo(spotlight, 'left', { duration: 0.1, ease: 'power2.out' });
    const topTo = gsap.quickTo(spotlight, 'top', { duration: 0.1, ease: 'power2.out' });
    const opacityTo = gsap.quickTo(spotlight, 'opacity', { duration: 0.2, ease: 'power2.out' });
    let frameId: number | null = null;
    let pointerX = 0;
    let pointerY = 0;
    let visible = false;

    const hideSpotlight = () => {
      if (frameId !== null) cancelAnimationFrame(frameId);
      frameId = null;
      cards.forEach((card) => card.style.setProperty('--glow-intensity', '0'));
      if (visible) opacityTo(0);
      visible = false;
    };

    const renderSpotlight = () => {
      frameId = null;
      const gridRect = grid.getBoundingClientRect();
      const pointerInside = pointerX >= gridRect.left
        && pointerX <= gridRect.right
        && pointerY >= gridRect.top
        && pointerY <= gridRect.bottom;

      if (!pointerInside) {
        hideSpotlight();
        return;
      }

      const { proximity, fadeDistance } = calculateSpotlightValues(config.spotlightRadius);
      let minDistance = Infinity;

      cards.forEach((card) => {
        const rect = card.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const distance = Math.hypot(pointerX - centerX, pointerY - centerY) - Math.max(rect.width, rect.height) / 2;
        const effectiveDistance = Math.max(0, distance);
        minDistance = Math.min(minDistance, effectiveDistance);
        const glowIntensity = effectiveDistance <= proximity
          ? 1
          : effectiveDistance <= fadeDistance
            ? (fadeDistance - effectiveDistance) / (fadeDistance - proximity)
            : 0;
        updateCardGlowProperties(card, rect, pointerX, pointerY, glowIntensity, config.spotlightRadius);
      });

      leftTo(pointerX);
      topTo(pointerY);
      const targetOpacity = minDistance <= proximity
        ? 0.8
        : minDistance <= fadeDistance
          ? ((fadeDistance - minDistance) / (fadeDistance - proximity)) * 0.8
          : 0;
      opacityTo(targetOpacity);
      visible = targetOpacity > 0;
    };

    const handlePointerMove = (event: PointerEvent) => {
      pointerX = event.clientX;
      pointerY = event.clientY;
      if (frameId === null) frameId = requestAnimationFrame(renderSpotlight);
    };

    const handleVisibilityChange = () => {
      if (document.hidden) hideSpotlight();
    };

    document.addEventListener('pointermove', handlePointerMove, { passive: true });
    document.addEventListener('mouseleave', hideSpotlight);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('pointermove', handlePointerMove);
      document.removeEventListener('mouseleave', hideSpotlight);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (frameId !== null) cancelAnimationFrame(frameId);
      gsap.killTweensOf(spotlight);
      spotlight.remove();
    };
  }, [config, gridRef]);

  return null;
}

export function MagicBentoCard({ children, className = '', style }: MagicBentoCardProps) {
  const config = useContext(MagicBentoContext);
  const cardRef = useRef<HTMLDivElement>(null);
  const particlesRef = useRef<HTMLDivElement[]>([]);
  const timeoutsRef = useRef<number[]>([]);
  const isHoveredRef = useRef(false);
  const memoizedParticles = useRef<HTMLDivElement[]>([]);
  const particlesInitialized = useRef(false);

  useEffect(() => {
    memoizedParticles.current = [];
    particlesInitialized.current = false;
  }, [config.glowColor, config.particleCount]);

  const initializeParticles = useCallback(() => {
    if (particlesInitialized.current || !cardRef.current) return;
    const { width, height } = cardRef.current.getBoundingClientRect();
    memoizedParticles.current = Array.from({ length: config.particleCount }, () =>
      createParticleElement(Math.random() * width, Math.random() * height, config.glowColor));
    particlesInitialized.current = true;
  }, [config.glowColor, config.particleCount]);

  const clearAllParticles = useCallback((immediate = false) => {
    timeoutsRef.current.forEach(clearTimeout);
    timeoutsRef.current = [];
    const particles = particlesRef.current;
    particlesRef.current = [];

    particles.forEach((particle) => {
      gsap.killTweensOf(particle);
      if (immediate) {
        particle.remove();
        return;
      }
      gsap.to(particle, {
        scale: 0,
        opacity: 0,
        duration: 0.3,
        ease: 'back.in(1.7)',
        onComplete: () => particle.remove(),
      });
    });
  }, []);

  const animateParticles = useCallback(() => {
    if (!cardRef.current || !isHoveredRef.current) return;
    if (!particlesInitialized.current) initializeParticles();

    memoizedParticles.current.forEach((particle, index) => {
      const timeoutId = window.setTimeout(() => {
        if (!isHoveredRef.current || !cardRef.current) return;
        const clone = particle.cloneNode(true) as HTMLDivElement;
        cardRef.current.appendChild(clone);
        particlesRef.current.push(clone);
        gsap.fromTo(clone, { scale: 0, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' });
        gsap.to(clone, {
          x: (Math.random() - 0.5) * 100,
          y: (Math.random() - 0.5) * 100,
          rotation: Math.random() * 360,
          duration: 2 + Math.random() * 2,
          ease: 'none',
          repeat: -1,
          yoyo: true,
        });
        gsap.to(clone, { opacity: 0.3, duration: 1.5, ease: 'power2.inOut', repeat: -1, yoyo: true });
      }, index * 100);
      timeoutsRef.current.push(timeoutId);
    });
  }, [initializeParticles]);

  useEffect(() => {
    const element = cardRef.current;
    if (!element) return;

    if (config.disableAnimations) {
      clearAllParticles(true);
      gsap.set(element, { clearProps: 'transform' });
      return;
    }

    gsap.set(element, { transformPerspective: 1000 });
    const rotateXTo = gsap.quickTo(element, 'rotationX', { duration: 0.1, ease: 'power2.out' });
    const rotateYTo = gsap.quickTo(element, 'rotationY', { duration: 0.1, ease: 'power2.out' });
    const xTo = gsap.quickTo(element, 'x', { duration: 0.3, ease: 'power2.out' });
    const yTo = gsap.quickTo(element, 'y', { duration: 0.3, ease: 'power2.out' });
    let frameId: number | null = null;
    let pendingPointer: { clientX: number; clientY: number; target: EventTarget | null } | null = null;

    const resetSpatialMotion = (immediate = false) => {
      pendingPointer = null;
      if (frameId !== null) cancelAnimationFrame(frameId);
      frameId = null;
      if (immediate) {
        gsap.set(element, { rotationX: 0, rotationY: 0, x: 0, y: 0 });
        return;
      }
      rotateXTo(0);
      rotateYTo(0);
      xTo(0);
      yTo(0);
    };

    const shouldSuspendSpatialMotion = (target: EventTarget | null) => {
      if (!config.suspendSelector) return false;
      const targetElement = target instanceof Element ? target : null;
      const activeElement = document.activeElement instanceof Element ? document.activeElement : null;
      return Boolean(
        targetElement?.closest(config.suspendSelector)
        || (activeElement && element.contains(activeElement) && activeElement.closest(config.suspendSelector)),
      );
    };

    const handlePointerEnter = () => {
      isHoveredRef.current = true;
      animateParticles();
      if (config.enableTilt) {
        rotateXTo(config.tiltMax * 0.5);
        rotateYTo(config.tiltMax * 0.5);
      }
    };

    const handlePointerLeave = (immediate = false) => {
      isHoveredRef.current = false;
      clearAllParticles(immediate);
      resetSpatialMotion(immediate);
    };

    const applyPointerMotion = () => {
      frameId = null;
      const pointer = pendingPointer;
      pendingPointer = null;
      if (!pointer) return;
      if (shouldSuspendSpatialMotion(pointer.target)) {
        resetSpatialMotion();
        return;
      }
      if (!config.enableTilt && !config.enableMagnetism) return;

      const rect = element.getBoundingClientRect();
      const x = pointer.clientX - rect.left;
      const y = pointer.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      if (config.enableTilt) {
        rotateXTo(((y - centerY) / centerY) * -config.tiltMax);
        rotateYTo(((x - centerX) / centerX) * config.tiltMax);
      }
      if (config.enableMagnetism) {
        xTo((x - centerX) * config.magnetismStrength);
        yTo((y - centerY) * config.magnetismStrength);
      }
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!isHoveredRef.current) {
        isHoveredRef.current = true;
        animateParticles();
      }
      pendingPointer = { clientX: event.clientX, clientY: event.clientY, target: event.target };
      if (frameId === null) frameId = requestAnimationFrame(applyPointerMotion);
    };

    const handleDocumentPointerMove = (event: PointerEvent) => {
      if (!isHoveredRef.current) return;
      if (event.target instanceof Node && element.contains(event.target)) return;
      const rect = element.getBoundingClientRect();
      const outside = event.clientX < rect.left
        || event.clientX > rect.right
        || event.clientY < rect.top
        || event.clientY > rect.bottom;
      if (outside) handlePointerLeave();
    };

    const handleFocusIn = (event: FocusEvent) => {
      if (shouldSuspendSpatialMotion(event.target)) resetSpatialMotion();
    };

    const handleVisibilityChange = () => {
      if (document.hidden) handlePointerLeave(true);
    };

    const handleElementPointerLeave = () => handlePointerLeave();

    const handleClick = (event: MouseEvent) => {
      if (!config.clickEffect) return;
      const rect = element.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const maxDistance = Math.max(
        Math.hypot(x, y),
        Math.hypot(x - rect.width, y),
        Math.hypot(x, y - rect.height),
        Math.hypot(x - rect.width, y - rect.height),
      );
      const ripple = document.createElement('div');
      ripple.className = 'ki-magic-bento-ripple';
      ripple.style.cssText = `
        position: absolute;
        width: ${maxDistance * 2}px;
        height: ${maxDistance * 2}px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(${config.glowColor}, 0.4) 0%, rgba(${config.glowColor}, 0.2) 30%, transparent 70%);
        left: ${x - maxDistance}px;
        top: ${y - maxDistance}px;
        pointer-events: none;
        z-index: 1000;
      `;
      element.appendChild(ripple);
      gsap.fromTo(ripple, { scale: 0, opacity: 1 }, { scale: 1, opacity: 0, duration: 0.8, ease: 'power2.out', onComplete: () => ripple.remove() });
    };

    element.addEventListener('pointerenter', handlePointerEnter);
    element.addEventListener('pointerleave', handleElementPointerLeave);
    element.addEventListener('pointermove', handlePointerMove, { passive: true });
    element.addEventListener('click', handleClick);
    element.addEventListener('focusin', handleFocusIn);
    document.addEventListener('pointermove', handleDocumentPointerMove, { passive: true });
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      isHoveredRef.current = false;
      element.removeEventListener('pointerenter', handlePointerEnter);
      element.removeEventListener('pointerleave', handleElementPointerLeave);
      element.removeEventListener('pointermove', handlePointerMove);
      element.removeEventListener('click', handleClick);
      element.removeEventListener('focusin', handleFocusIn);
      document.removeEventListener('pointermove', handleDocumentPointerMove);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (frameId !== null) cancelAnimationFrame(frameId);
      clearAllParticles(true);
      element.querySelectorAll<HTMLElement>('.ki-magic-bento-ripple').forEach((ripple) => {
        gsap.killTweensOf(ripple);
        ripple.remove();
      });
      gsap.killTweensOf(element);
    };
  }, [animateParticles, clearAllParticles, config]);

  return (
    <div
      ref={cardRef}
      className={`ki-magic-bento-card ki-magic-bento-card--border-glow ${className}`}
      style={{ ...style, '--glow-color': config.glowColor } as CSSProperties}
    >
      {children}
    </div>
  );
}

export function MagicBentoGrid({
  children,
  className = '',
  disableAnimations = false,
  particleCount = DEFAULT_PARTICLE_COUNT,
  spotlightRadius = DEFAULT_SPOTLIGHT_RADIUS,
  glowColor = DEFAULT_GLOW_COLOR,
  enableTilt = false,
  clickEffect = true,
  enableMagnetism = true,
  tiltMax = DEFAULT_TILT_MAX,
  magnetismStrength = DEFAULT_MAGNETISM_STRENGTH,
  suspendSelector,
}: MagicBentoGridProps) {
  const gridRef = useRef<HTMLDivElement>(null);
  const animationDisabled = useAnimationDisabled();
  const config = useMemo<MagicBentoConfig>(() => ({
    disableAnimations: disableAnimations || animationDisabled,
    particleCount,
    spotlightRadius,
    glowColor,
    enableTilt,
    clickEffect,
    enableMagnetism,
    tiltMax,
    magnetismStrength,
    suspendSelector,
  }), [animationDisabled, clickEffect, disableAnimations, enableMagnetism, enableTilt, glowColor, magnetismStrength, particleCount, spotlightRadius, suspendSelector, tiltMax]);

  return (
    <MagicBentoContext.Provider value={config}>
      <GlobalSpotlight gridRef={gridRef} config={config} />
      <div ref={gridRef} className={`ki-magic-bento-grid bento-section ${className}`}>{children}</div>
    </MagicBentoContext.Provider>
  );
}
