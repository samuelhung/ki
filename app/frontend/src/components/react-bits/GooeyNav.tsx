import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import './GooeyNav.css';

export interface GooeyNavItem { label: string; href: string }

interface GooeyNavProps {
  items: GooeyNavItem[];
  animationTime?: number;
  particleCount?: number;
  particleDistances?: [number, number];
  particleR?: number;
  timeVariance?: number;
  colors?: number[];
  initialActiveIndex?: number;
}

const noise = (amount = 1) => amount / 2 - Math.random() * amount;

export default function GooeyNav({
  items,
  animationTime = 600,
  particleCount = 15,
  particleDistances = [90, 10],
  particleR = 100,
  timeVariance = 300,
  colors = [1, 2, 3, 1, 2, 3, 1, 4],
  initialActiveIndex = 0,
}: GooeyNavProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLUListElement>(null);
  const filterRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const timerIdsRef = useRef<number[]>([]);
  const [activeIndex, setActiveIndex] = useState(initialActiveIndex);

  const updateEffectPosition = useCallback((element: HTMLElement) => {
    if (!containerRef.current || !filterRef.current || !textRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const itemRect = element.getBoundingClientRect();
    const styles = {
      left: `${itemRect.left - containerRect.left}px`,
      top: `${itemRect.top - containerRect.top}px`,
      width: `${itemRect.width}px`,
      height: `${itemRect.height}px`,
    };
    Object.assign(filterRef.current.style, styles);
    Object.assign(textRef.current.style, styles);
    textRef.current.textContent = element.textContent;
  }, []);

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

  const activate = useCallback((element: HTMLElement, index: number) => {
    if (activeIndex === index) return;
    setActiveIndex(index);
    updateEffectPosition(element);
    if (textRef.current) {
      textRef.current.classList.remove('is-active');
      void textRef.current.offsetWidth;
      textRef.current.classList.add('is-active');
    }
    if (filterRef.current) makeParticles(filterRef.current);
  }, [activeIndex, makeParticles, updateEffectPosition]);

  const handleClick = (event: MouseEvent<HTMLAnchorElement>, index: number) => {
    event.preventDefault();
    const item = event.currentTarget.parentElement;
    if (item) activate(item, index);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLAnchorElement>, index: number) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    const item = event.currentTarget.parentElement;
    if (item) activate(item, index);
  };

  useEffect(() => {
    const activeItem = navRef.current?.querySelectorAll('li')[activeIndex] as HTMLElement | undefined;
    if (activeItem) {
      updateEffectPosition(activeItem);
      textRef.current?.classList.add('is-active');
    }

    const observer = new ResizeObserver(() => {
      const item = navRef.current?.querySelectorAll('li')[activeIndex] as HTMLElement | undefined;
      if (item) updateEffectPosition(item);
    });
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [activeIndex, updateEffectPosition]);

  useEffect(() => clearParticles, [clearParticles]);

  return (
    <div className="gooey-nav" ref={containerRef}>
      <nav aria-label="Primary demo navigation">
        <ul ref={navRef}>
          {items.map((item, index) => (
            <li key={item.label} className={activeIndex === index ? 'is-active' : ''}>
              <a href={item.href} onClick={event => handleClick(event, index)} onKeyDown={event => handleKeyDown(event, index)}>
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <span className="gooey-nav__effect gooey-nav__filter" ref={filterRef} />
      <span className="gooey-nav__effect gooey-nav__text" ref={textRef} />
    </div>
  );
}
