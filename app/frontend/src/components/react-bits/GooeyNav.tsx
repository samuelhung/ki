import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import './GooeyNav.css';

export interface GooeyNavItem { label: string; href: string }

const DEFAULT_PARTICLE_DISTANCES: [number, number] = [90, 10];
const DEFAULT_PARTICLE_COLORS = [1, 2, 3, 1, 2, 3, 1, 4];

interface GooeyNavProps {
  items: GooeyNavItem[];
  animationTime?: number;
  particleCount?: number;
  particleDistances?: [number, number];
  particleR?: number;
  timeVariance?: number;
  colors?: number[];
  initialActiveIndex?: number;
  activeIndex?: number;
  navigationDelay?: number;
  onNavigate?: (item: GooeyNavItem, index: number) => void;
}

const noise = (amount = 1) => amount / 2 - Math.random() * amount;

export default function GooeyNav({
  items,
  animationTime = 600,
  particleCount = 15,
  particleDistances = DEFAULT_PARTICLE_DISTANCES,
  particleR = 100,
  timeVariance = 300,
  colors = DEFAULT_PARTICLE_COLORS,
  initialActiveIndex = 0,
  activeIndex: controlledActiveIndex,
  navigationDelay = 0,
  onNavigate,
}: GooeyNavProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLUListElement>(null);
  const filterRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const timerIdsRef = useRef<number[]>([]);
  const navigationTimerRef = useRef<number | null>(null);
  const [effectHost, setEffectHost] = useState<HTMLElement | null>(null);
  const [internalActiveIndex, setInternalActiveIndex] = useState(initialActiveIndex);
  const [pendingActiveIndex, setPendingActiveIndex] = useState<number | null>(null);
  const activeIndex = controlledActiveIndex ?? internalActiveIndex;
  const renderedActiveIndex = pendingActiveIndex ?? activeIndex;

  const updateEffectPosition = useCallback((element: HTMLElement) => {
    if (!effectHost || !filterRef.current || !textRef.current) return;
    const hostRect = effectHost.getBoundingClientRect();
    const itemRect = element.getBoundingClientRect();
    const styles = {
      left: `${itemRect.left - hostRect.left}px`,
      top: `${itemRect.top - hostRect.top}px`,
      width: `${itemRect.width}px`,
      height: `${itemRect.height}px`,
    };
    Object.assign(filterRef.current.style, styles);
    Object.assign(textRef.current.style, styles);
    textRef.current.textContent = element.textContent;
  }, [effectHost]);

  const clearParticles = useCallback(() => {
    timerIdsRef.current.forEach(id => window.clearTimeout(id));
    timerIdsRef.current = [];
    filterRef.current?.querySelectorAll('.gooey-nav__particle').forEach(particle => particle.remove());
  }, []);

  const makeParticles = useCallback((element: HTMLElement) => {
    clearParticles();
    element.classList.remove('is-active');

    for (let index = 0; index < particleCount; index += 1) {
      const angle = ((360 + noise(8)) / particleCount) * (particleCount - index) * (Math.PI / 180);
      const start = [particleDistances[0] * Math.cos(angle), particleDistances[0] * Math.sin(angle)];
      const endDistance = particleDistances[1] + noise(7);
      const end = [endDistance * Math.cos(angle), endDistance * Math.sin(angle)];
      const duration = animationTime * 2 + noise(timeVariance * 2);
      const rotateNoise = noise(particleR / 10);
      const rotate = rotateNoise > 0 ? (rotateNoise + particleR / 20) * 10 : (rotateNoise - particleR / 20) * 10;
      const scale = 1 + noise(0.2);
      const color = colors[Math.floor(Math.random() * colors.length)];

      const createTimer = window.setTimeout(() => {
        const particle = document.createElement('span');
        const point = document.createElement('span');
        particle.className = 'gooey-nav__particle';
        point.className = 'gooey-nav__point';
        particle.style.setProperty('--start-x', `${start[0]}px`);
        particle.style.setProperty('--start-y', `${start[1]}px`);
        particle.style.setProperty('--end-x', `${end[0]}px`);
        particle.style.setProperty('--end-y', `${end[1]}px`);
        particle.style.setProperty('--time', `${duration}ms`);
        particle.style.setProperty('--scale', `${scale}`);
        particle.style.setProperty('--color', `var(--gooey-color-${color}, white)`);
        particle.style.setProperty('--rotate', `${rotate}deg`);
        particle.appendChild(point);
        element.appendChild(particle);
        requestAnimationFrame(() => element.classList.add('is-active'));

        const removeTimer = window.setTimeout(() => particle.remove(), duration);
        timerIdsRef.current.push(removeTimer);
      }, 30);
      timerIdsRef.current.push(createTimer);
    }
  }, [animationTime, clearParticles, colors, particleCount, particleDistances, particleR, timeVariance]);
  const makeParticlesRef = useRef(makeParticles);
  makeParticlesRef.current = makeParticles;

  const activate = useCallback((index: number) => {
    if (renderedActiveIndex === index) return false;
    if (controlledActiveIndex === undefined) setInternalActiveIndex(index);
    else setPendingActiveIndex(index);
    return true;
  }, [controlledActiveIndex, renderedActiveIndex]);

  const navigateAfterEffectStarts = useCallback((index: number, changed: boolean) => {
    if (navigationTimerRef.current !== null) window.clearTimeout(navigationTimerRef.current);
    if (!changed || navigationDelay <= 0) {
      onNavigate?.(items[index], index);
      return;
    }
    navigationTimerRef.current = window.setTimeout(() => onNavigate?.(items[index], index), navigationDelay);
  }, [items, navigationDelay, onNavigate]);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>, index: number) => {
    event.preventDefault();
    navigateAfterEffectStarts(index, activate(index));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>, index: number) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    navigateAfterEffectStarts(index, activate(index));
  };

  useEffect(() => { setPendingActiveIndex(null); }, [controlledActiveIndex]);

  useEffect(() => {
    const host = containerRef.current?.closest('main');
    setEffectHost(host instanceof HTMLElement ? host : document.body);
  }, []);

  useEffect(() => {
    const activeItem = navRef.current?.querySelectorAll('li')[renderedActiveIndex] as HTMLElement | undefined;
    if (activeItem) {
      updateEffectPosition(activeItem);
      textRef.current?.classList.add('is-active');
      if (filterRef.current) makeParticlesRef.current(filterRef.current);
    }

    const observer = new ResizeObserver(() => {
      const item = navRef.current?.querySelectorAll('li')[renderedActiveIndex] as HTMLElement | undefined;
      if (item) updateEffectPosition(item);
    });
    const syncPosition = () => {
      const item = navRef.current?.querySelectorAll('li')[renderedActiveIndex] as HTMLElement | undefined;
      if (item) updateEffectPosition(item);
    };
    if (containerRef.current) observer.observe(containerRef.current);
    window.addEventListener('resize', syncPosition);
    window.addEventListener('scroll', syncPosition, true);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', syncPosition);
      window.removeEventListener('scroll', syncPosition, true);
    };
  }, [renderedActiveIndex, updateEffectPosition]);

  useEffect(() => () => {
    clearParticles();
    if (navigationTimerRef.current !== null) window.clearTimeout(navigationTimerRef.current);
  }, [clearParticles]);

  return (
    <div className="gooey-nav" ref={containerRef}>
      <nav aria-label="Primary demo navigation">
        <ul ref={navRef}>
          {items.map((item, index) => (
            <li key={item.label} className={renderedActiveIndex === index ? 'is-active' : ''}>
              <a href={item.href} onClick={event => handleClick(event, index)} onKeyDown={event => handleKeyDown(event, index)}>
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      {effectHost && createPortal(
        <>
          <span className="gooey-nav__effect gooey-nav__filter gooey-nav__portal-effect" ref={filterRef} />
          <span className="gooey-nav__effect gooey-nav__text gooey-nav__portal-effect" ref={textRef} />
        </>,
        effectHost,
      )}
    </div>
  );
}
