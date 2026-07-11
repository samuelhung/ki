import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import './DomeGallery.css';

const DEFAULT_IMAGES = [
  {
    src: 'https://images.unsplash.com/photo-1755331039789-7e5680e26e8f?q=80&w=774&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Abstract art'
  },
  {
    src: 'https://images.unsplash.com/photo-1755569309049-98410b94f66d?q=80&w=772&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Modern sculpture'
  },
  {
    src: 'https://images.unsplash.com/photo-1755497595318-7e5e3523854f?q=80&w=774&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Digital artwork'
  },
  {
    src: 'https://images.unsplash.com/photo-1755353985163-c2a0fe5ac3d8?q=80&w=774&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Contemporary art'
  },
  {
    src: 'https://images.unsplash.com/photo-1745965976680-d00be7dc0377?q=80&w=774&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Geometric pattern'
  },
  {
    src: 'https://images.unsplash.com/photo-1752588975228-21f44630bb3c?q=80&w=774&auto=format&fit=crop&ixlib=rb-4.1.0',
    alt: 'Textured surface'
  },
  {
    src: 'https://pbs.twimg.com/media/Gyla7NnXMAAXSo_?format=jpg&name=large',
    alt: 'Social media image'
  }
];

const DEFAULTS = {
  maxVerticalRotationDeg: 5,
  dragSensitivity: 20,
  enlargeTransitionMs: 300,
  segments: 35,
  clickMoveTolerance: 12
};

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
const normalizeAngle = (degrees) => ((degrees % 360) + 360) % 360;
const wrapAngleSigned = (degrees) => {
  const angle = (((degrees + 180) % 360) + 360) % 360;
  return angle - 180;
};

function getDataNumber(element, name, fallback) {
  const attr = element.dataset[name] ?? element.getAttribute(`data-${name}`);
  const parsed = attr == null ? NaN : parseFloat(attr);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeImage(image) {
  if (typeof image === 'string') return { src: image, alt: '' };
  return { src: image.src || '', alt: image.alt || '' };
}

function buildItems(pool, segments, tileScale = 1, tileGapScale = 1) {
  const itemSize = clamp(tileScale, 0.2, 2) * 2;
  const gapScale = clamp(tileGapScale, 0, 2);
  const itemStep = itemSize + Math.max(0, 2 - itemSize) * gapScale;
  const startX = -((segments - 1) * itemStep) / 2;
  const xCols = Array.from({ length: segments }, (_, index) => startX + index * itemStep);
  const evenYs = [-2, -1, 0, 1, 2].map((y) => y * itemStep);
  const oddYs = [-1.5, -0.5, 0.5, 1.5, 2.5].map((y) => y * itemStep);

  const coords = xCols.flatMap((x, columnIndex) => {
    const ys = columnIndex % 2 === 0 ? evenYs : oddYs;
    return ys.map((y) => ({ x, y, sizeX: itemSize, sizeY: itemSize }));
  });

  const normalizedImages = pool.length > 0 ? pool.map(normalizeImage) : [{ src: '', alt: '' }];
  const usedImages = Array.from({ length: coords.length }, (_, index) => normalizedImages[index % normalizedImages.length]);

  for (let index = 1; index < usedImages.length; index += 1) {
    if (usedImages[index].src === usedImages[index - 1].src) {
      for (let swapIndex = index + 1; swapIndex < usedImages.length; swapIndex += 1) {
        if (usedImages[swapIndex].src !== usedImages[index].src) {
          const next = usedImages[index];
          usedImages[index] = usedImages[swapIndex];
          usedImages[swapIndex] = next;
          break;
        }
      }
    }
  }

  return coords.map((coord, index) => ({
    ...coord,
    src: usedImages[index].src,
    alt: usedImages[index].alt
  }));
}

function computeItemBaseRotation(offsetX, offsetY, sizeX, sizeY, segments) {
  const unit = 360 / segments / 2;
  const rotateY = unit * (offsetX + (sizeX - 1) / 2);
  const rotateX = unit * (offsetY - (sizeY - 1) / 2);
  return { rotateX, rotateY };
}

export default function DomeGallery({
  images = DEFAULT_IMAGES,
  fit = 0.5,
  fitBasis = 'auto',
  minRadius = 600,
  maxRadius = Infinity,
  padFactor = 0.25,
  overlayBlurColor = '#060010',
  maxVerticalRotationDeg = DEFAULTS.maxVerticalRotationDeg,
  dragSensitivity = DEFAULTS.dragSensitivity,
  enlargeTransitionMs = DEFAULTS.enlargeTransitionMs,
  segments = DEFAULTS.segments,
  dragDampening = 2,
  openedImageWidth = '400px',
  openedImageHeight = '400px',
  imageBorderRadius = '30px',
  openedImageBorderRadius = '30px',
  grayscale = true,
  clickMoveTolerance = DEFAULTS.clickMoveTolerance,
  tileScale = 1,
  tileGapScale = 1
}) {
  const rootRef = useRef(null);
  const mainRef = useRef(null);
  const sphereRef = useRef(null);
  const frameRef = useRef(null);
  const viewerRef = useRef(null);
  const scrimRef = useRef(null);
  const focusedElRef = useRef(null);
  const originalTilePositionRef = useRef(null);
  const rotationRef = useRef({ x: 0, y: 0 });
  const startRotRef = useRef({ x: 0, y: 0 });
  const startPosRef = useRef(null);
  const lastPointRef = useRef(null);
  const draggingRef = useRef(false);
  const movedRef = useRef(false);
  const pressedTileRef = useRef(null);
  const inertiaRafRef = useRef(null);
  const openingRef = useRef(false);
  const openStartedAtRef = useRef(0);
  const lastDragEndAtRef = useRef(0);
  const scrollLockedRef = useRef(false);

  const items = useMemo(() => buildItems(images, segments, tileScale, tileGapScale), [images, segments, tileScale, tileGapScale]);

  const applyTransform = useCallback((xDeg, yDeg) => {
    const sphere = sphereRef.current;
    if (sphere) {
      sphere.style.transform = `translateZ(calc(var(--radius) * -1)) rotateX(${xDeg}deg) rotateY(${yDeg}deg)`;
    }
  }, []);

  const lockScroll = useCallback(() => {
    if (scrollLockedRef.current) return;
    scrollLockedRef.current = true;
    document.body.classList.add('dg-scroll-lock');
  }, []);

  const unlockScroll = useCallback(() => {
    if (!scrollLockedRef.current) return;
    if (rootRef.current?.getAttribute('data-enlarging') === 'true') return;
    scrollLockedRef.current = false;
    document.body.classList.remove('dg-scroll-lock');
  }, []);

  const stopInertia = useCallback(() => {
    if (inertiaRafRef.current) {
      cancelAnimationFrame(inertiaRafRef.current);
      inertiaRafRef.current = null;
    }
  }, []);

  const resetInteractionState = useCallback(() => {
    stopInertia();
    draggingRef.current = false;
    movedRef.current = false;
    pressedTileRef.current = null;
    startPosRef.current = null;
    lastPointRef.current = null;
    applyTransform(rotationRef.current.x, rotationRef.current.y);
  }, [applyTransform, stopInertia]);

  const startInertia = useCallback(
    (vx, vy) => {
      const maxVelocity = 1.4;
      let velocityX = clamp(vx, -maxVelocity, maxVelocity) * 80;
      let velocityY = clamp(vy, -maxVelocity, maxVelocity) * 80;
      let frames = 0;
      const dampening = clamp(dragDampening ?? 0.6, 0, 1);
      const frictionMul = 0.94 + 0.055 * dampening;
      const stopThreshold = 0.015 - 0.01 * dampening;
      const maxFrames = Math.round(90 + 270 * dampening);

      const step = () => {
        velocityX *= frictionMul;
        velocityY *= frictionMul;
        if (Math.abs(velocityX) < stopThreshold && Math.abs(velocityY) < stopThreshold) {
          inertiaRafRef.current = null;
          return;
        }
        if (frames > maxFrames) {
          inertiaRafRef.current = null;
          return;
        }
        frames += 1;

        const nextX = clamp(rotationRef.current.x - velocityY / 200, -maxVerticalRotationDeg, maxVerticalRotationDeg);
        const nextY = wrapAngleSigned(rotationRef.current.y + velocityX / 200);
        rotationRef.current = { x: nextX, y: nextY };
        applyTransform(nextX, nextY);
        inertiaRafRef.current = requestAnimationFrame(step);
      };

      stopInertia();
      inertiaRafRef.current = requestAnimationFrame(step);
    },
    [applyTransform, dragDampening, maxVerticalRotationDeg, stopInertia]
  );

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;

    const resizeObserver = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect;
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      const minDim = Math.min(width, height);
      const maxDim = Math.max(width, height);
      const aspect = width / height;
      let basis;

      switch (fitBasis) {
        case 'min':
          basis = minDim;
          break;
        case 'max':
          basis = maxDim;
          break;
        case 'width':
          basis = width;
          break;
        case 'height':
          basis = height;
          break;
        default:
          basis = aspect >= 1.3 ? width : minDim;
      }

      let radius = basis * fit;
      radius = Math.min(radius, height * 1.35);
      radius = clamp(radius, minRadius, maxRadius);
      const viewerPad = Math.max(8, Math.round(minDim * padFactor));

      root.style.setProperty('--radius', `${Math.round(radius)}px`);
      root.style.setProperty('--viewer-pad', `${viewerPad}px`);
      root.style.setProperty('--overlay-blur-color', overlayBlurColor);
      root.style.setProperty('--tile-radius', imageBorderRadius);
      root.style.setProperty('--enlarge-radius', openedImageBorderRadius);
      root.style.setProperty('--image-filter', grayscale ? 'grayscale(1)' : 'none');
      applyTransform(rotationRef.current.x, rotationRef.current.y);

      const overlay = viewerRef.current?.querySelector('.enlarge');
      if (overlay && frameRef.current && mainRef.current) {
        const frameRect = frameRef.current.getBoundingClientRect();
        const mainRect = mainRef.current.getBoundingClientRect();
        const hasCustomSize = openedImageWidth || openedImageHeight;

        if (hasCustomSize) {
          const temp = document.createElement('div');
          temp.style.cssText = `position: absolute; width: ${openedImageWidth || `${frameRect.width}px`}; height: ${openedImageHeight || `${frameRect.height}px`}; visibility: hidden;`;
          document.body.appendChild(temp);
          const tempRect = temp.getBoundingClientRect();
          temp.remove();

          overlay.style.left = `${frameRect.left - mainRect.left + (frameRect.width - tempRect.width) / 2}px`;
          overlay.style.top = `${frameRect.top - mainRect.top + (frameRect.height - tempRect.height) / 2}px`;
          overlay.style.width = `${tempRect.width}px`;
          overlay.style.height = `${tempRect.height}px`;
        } else {
          overlay.style.left = `${frameRect.left - mainRect.left}px`;
          overlay.style.top = `${frameRect.top - mainRect.top}px`;
          overlay.style.width = `${frameRect.width}px`;
          overlay.style.height = `${frameRect.height}px`;
        }
      }
    });

    resizeObserver.observe(root);
    return () => resizeObserver.disconnect();
  }, [
    applyTransform,
    fit,
    fitBasis,
    grayscale,
    imageBorderRadius,
    maxRadius,
    minRadius,
    openedImageBorderRadius,
    openedImageHeight,
    openedImageWidth,
    overlayBlurColor,
    padFactor
  ]);

  const openItemFromElement = useCallback(
    (element) => {
      if (openingRef.current) return;
      openingRef.current = true;
      openStartedAtRef.current = performance.now();
      lockScroll();

      const parent = element.parentElement;
      focusedElRef.current = element;
      element.setAttribute('data-focused', 'true');

      const offsetX = getDataNumber(parent, 'offsetX', 0);
      const offsetY = getDataNumber(parent, 'offsetY', 0);
      const sizeX = getDataNumber(parent, 'sizeX', 2);
      const sizeY = getDataNumber(parent, 'sizeY', 2);
      const parentRot = computeItemBaseRotation(offsetX, offsetY, sizeX, sizeY, segments);
      const parentY = normalizeAngle(parentRot.rotateY);
      const globalY = normalizeAngle(rotationRef.current.y);
      let rotY = -(parentY + globalY) % 360;
      if (rotY < -180) rotY += 360;
      const rotX = -parentRot.rotateX - rotationRef.current.x;

      parent.style.setProperty('--rot-y-delta', `${rotY}deg`);
      parent.style.setProperty('--rot-x-delta', `${rotX}deg`);

      const refDiv = document.createElement('div');
      refDiv.className = 'item__image item__image--reference';
      refDiv.style.opacity = '0';
      refDiv.style.transform = `rotateX(${-parentRot.rotateX}deg) rotateY(${-parentRot.rotateY}deg)`;
      parent.appendChild(refDiv);
      void refDiv.offsetHeight;

      const tileRect = refDiv.getBoundingClientRect();
      const mainRect = mainRef.current?.getBoundingClientRect();
      const frameRect = frameRef.current?.getBoundingClientRect();

      if (!mainRect || !frameRect || tileRect.width <= 0 || tileRect.height <= 0) {
        openingRef.current = false;
        focusedElRef.current = null;
        parent.removeChild(refDiv);
        unlockScroll();
        return;
      }

      originalTilePositionRef.current = {
        left: tileRect.left,
        top: tileRect.top,
        width: tileRect.width,
        height: tileRect.height
      };

      element.style.visibility = 'hidden';
      element.style.zIndex = '0';

      const overlay = document.createElement('div');
      overlay.className = 'enlarge';
      const finalWidth = openedImageWidth || `${frameRect.width}px`;
      const finalHeight = openedImageHeight || `${frameRect.height}px`;
      const temp = document.createElement('div');
      temp.style.cssText = `position: absolute; width: ${finalWidth}; height: ${finalHeight}; visibility: hidden;`;
      document.body.appendChild(temp);
      const finalRect = temp.getBoundingClientRect();
      temp.remove();
      const finalLeft = frameRect.left - mainRect.left + (frameRect.width - finalRect.width) / 2;
      const finalTop = frameRect.top - mainRect.top + (frameRect.height - finalRect.height) / 2;

      overlay.style.left = `${finalLeft}px`;
      overlay.style.top = `${finalTop}px`;
      overlay.style.width = `${finalRect.width}px`;
      overlay.style.height = `${finalRect.height}px`;
      overlay.style.opacity = '0';
      overlay.style.willChange = 'transform, opacity';
      overlay.style.transform = 'translate(0px, 0px) scale(1, 1)';
      overlay.style.transformOrigin = 'top left';
      overlay.style.transition = `transform ${enlargeTransitionMs}ms ease, opacity ${enlargeTransitionMs}ms ease`;

      const rawSrc = parent.dataset.src || element.querySelector('img')?.src || '';
      const img = document.createElement('img');
      img.src = rawSrc;
      overlay.appendChild(img);
      viewerRef.current.appendChild(overlay);

      const tx0 = tileRect.left - mainRect.left - finalLeft;
      const ty0 = tileRect.top - mainRect.top - finalTop;
      const sx0 = tileRect.width / finalRect.width;
      const sy0 = tileRect.height / finalRect.height;
      const startTransform = `translate(${tx0}px, ${ty0}px) scale(${Number.isFinite(sx0) ? sx0 : 1}, ${Number.isFinite(sy0) ? sy0 : 1})`;

      overlay.style.transform = startTransform;
      rootRef.current?.setAttribute('data-enlarging', 'true');

      setTimeout(() => {
        if (!overlay.parentElement) return;
        overlay.style.opacity = '1';
        overlay.style.transform = 'translate(0px, 0px) scale(1, 1)';
      }, 16);
    },
    [enlargeTransitionMs, lockScroll, openedImageHeight, openedImageWidth, segments, unlockScroll]
  );

  useEffect(() => {
    const main = mainRef.current;
    if (!main) return undefined;

    const getEventTile = (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return null;
      const directTile = target.closest('.item__image:not(.item__image--reference)');
      if (directTile) return directTile;
      return target.closest('.item')?.querySelector('.item__image:not(.item__image--reference)') || null;
    };

    const onPointerDown = (event) => {
      if (focusedElRef.current || event.button > 0) return;
      stopInertia();
      draggingRef.current = true;
      movedRef.current = false;
      pressedTileRef.current = getEventTile(event);
      startRotRef.current = { ...rotationRef.current };
      startPosRef.current = { x: event.clientX, y: event.clientY };
      lastPointRef.current = { x: event.clientX, y: event.clientY, t: performance.now() };
      main.setPointerCapture?.(event.pointerId);
    };

    const onPointerMove = (event) => {
      if (focusedElRef.current || !draggingRef.current || !startPosRef.current) return;
      const dx = event.clientX - startPosRef.current.x;
      const dy = event.clientY - startPosRef.current.y;
      const dist2 = dx * dx + dy * dy;
      if (!movedRef.current && dist2 > clickMoveTolerance * clickMoveTolerance) movedRef.current = true;

      const nextX = clamp(startRotRef.current.x - dy / dragSensitivity, -maxVerticalRotationDeg, maxVerticalRotationDeg);
      const nextY = wrapAngleSigned(startRotRef.current.y + dx / dragSensitivity);

      if (rotationRef.current.x !== nextX || rotationRef.current.y !== nextY) {
        rotationRef.current = { x: nextX, y: nextY };
        applyTransform(nextX, nextY);
      }
      lastPointRef.current = { x: event.clientX, y: event.clientY, t: performance.now() };
    };

    const onPointerUp = (event) => {
      if (!draggingRef.current) return;
      const tileToOpen = !movedRef.current && performance.now() - lastDragEndAtRef.current >= 80 ? pressedTileRef.current : null;
      draggingRef.current = false;
      main.releasePointerCapture?.(event.pointerId);

      const last = lastPointRef.current;
      const now = performance.now();
      let vx = 0;
      let vy = 0;
      if (last && now > last.t) {
        const dt = Math.max(16, now - last.t);
        vx = ((event.clientX - last.x) / dt) * 16;
        vy = ((event.clientY - last.y) / dt) * 16;
      }

      if (movedRef.current && (Math.abs(vx) > 0.005 || Math.abs(vy) > 0.005)) startInertia(vx, vy);
      if (movedRef.current) lastDragEndAtRef.current = performance.now();
      movedRef.current = false;
      pressedTileRef.current = null;
      startPosRef.current = null;
      lastPointRef.current = null;

      if (tileToOpen && !openingRef.current) openItemFromElement(tileToOpen);
    };

    main.addEventListener('pointerdown', onPointerDown);
    main.addEventListener('pointermove', onPointerMove);
    main.addEventListener('pointerup', onPointerUp);
    main.addEventListener('pointercancel', onPointerUp);

    return () => {
      main.removeEventListener('pointerdown', onPointerDown);
      main.removeEventListener('pointermove', onPointerMove);
      main.removeEventListener('pointerup', onPointerUp);
      main.removeEventListener('pointercancel', onPointerUp);
    };
  }, [applyTransform, clickMoveTolerance, dragSensitivity, maxVerticalRotationDeg, openItemFromElement, startInertia, stopInertia]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) {
        resetInteractionState();
        return;
      }
      applyTransform(rotationRef.current.x, rotationRef.current.y);
    };
    const onPageSuspend = () => resetInteractionState();
    const onPageResume = () => applyTransform(rotationRef.current.x, rotationRef.current.y);

    document.addEventListener('visibilitychange', onVisibilityChange, { passive: true });
    window.addEventListener('blur', onPageSuspend, { passive: true });
    window.addEventListener('pagehide', onPageSuspend, { passive: true });
    window.addEventListener('focus', onPageResume, { passive: true });
    window.addEventListener('pageshow', onPageResume, { passive: true });

    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('blur', onPageSuspend);
      window.removeEventListener('pagehide', onPageSuspend);
      window.removeEventListener('focus', onPageResume);
      window.removeEventListener('pageshow', onPageResume);
    };
  }, [applyTransform, resetInteractionState]);

  const onTileClick = useCallback(
    (event) => {
      if (draggingRef.current) return;
      if (movedRef.current) return;
      if (performance.now() - lastDragEndAtRef.current < 80) return;
      if (openingRef.current) return;
      openItemFromElement(event.currentTarget);
    },
    [openItemFromElement]
  );

  useEffect(() => {
    const scrim = scrimRef.current;
    if (!scrim) return undefined;

    const close = () => {
      if (performance.now() - openStartedAtRef.current < 250) return;
      const element = focusedElRef.current;
      if (!element) return;

      const parent = element.parentElement;
      const overlay = viewerRef.current?.querySelector('.enlarge');
      if (!overlay) return;
      const refDiv = parent.querySelector('.item__image--reference');
      const originalPos = originalTilePositionRef.current;

      if (!originalPos) {
        overlay.remove();
        refDiv?.remove();
        parent.style.setProperty('--rot-y-delta', '0deg');
        parent.style.setProperty('--rot-x-delta', '0deg');
        element.style.visibility = '';
        element.style.zIndex = '0';
        focusedElRef.current = null;
        rootRef.current?.removeAttribute('data-enlarging');
        openingRef.current = false;
        unlockScroll();
        return;
      }

      const currentRect = overlay.getBoundingClientRect();
      const rootRect = rootRef.current.getBoundingClientRect();
      const animatingOverlay = document.createElement('div');
      animatingOverlay.className = 'enlarge-closing';
      animatingOverlay.style.cssText = `
        position: absolute;
        left: ${currentRect.left - rootRect.left}px;
        top: ${currentRect.top - rootRect.top}px;
        width: ${currentRect.width}px;
        height: ${currentRect.height}px;
        z-index: 9999;
        border-radius: var(--enlarge-radius, 32px);
        overflow: hidden;
        box-shadow: 0 10px 30px rgba(0,0,0,.35);
        transition: all ${enlargeTransitionMs}ms ease-out;
        pointer-events: none;
        margin: 0;
        transform: none;
      `;

      const originalImg = overlay.querySelector('img');
      if (originalImg) {
        const img = originalImg.cloneNode();
        img.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
        animatingOverlay.appendChild(img);
      }

      overlay.remove();
      rootRef.current.appendChild(animatingOverlay);
      void animatingOverlay.getBoundingClientRect();

      requestAnimationFrame(() => {
        animatingOverlay.style.left = `${originalPos.left - rootRect.left}px`;
        animatingOverlay.style.top = `${originalPos.top - rootRect.top}px`;
        animatingOverlay.style.width = `${originalPos.width}px`;
        animatingOverlay.style.height = `${originalPos.height}px`;
        animatingOverlay.style.opacity = '0';
      });

      const cleanup = () => {
        animatingOverlay.remove();
        originalTilePositionRef.current = null;
        refDiv?.remove();
        parent.style.transition = 'none';
        element.style.transition = 'none';
        parent.style.setProperty('--rot-y-delta', '0deg');
        parent.style.setProperty('--rot-x-delta', '0deg');

        requestAnimationFrame(() => {
          element.style.visibility = '';
          element.style.opacity = '0';
          element.style.zIndex = '0';
          focusedElRef.current = null;
          rootRef.current?.removeAttribute('data-enlarging');

          requestAnimationFrame(() => {
            parent.style.transition = '';
            element.style.transition = 'opacity 300ms ease-out';

            requestAnimationFrame(() => {
              element.style.opacity = '1';
              setTimeout(() => {
                element.style.transition = '';
                element.style.opacity = '';
                openingRef.current = false;
                unlockScroll();
              }, 300);
            });
          });
        });
      };

      animatingOverlay.addEventListener('transitionend', cleanup, { once: true });
    };

    scrim.addEventListener('click', close);
    const onKeyDown = (event) => {
      if (event.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKeyDown);

    return () => {
      scrim.removeEventListener('click', close);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [enlargeTransitionMs, unlockScroll]);

  useEffect(() => {
    return () => {
      document.body.classList.remove('dg-scroll-lock');
      stopInertia();
    };
  }, [stopInertia]);

  return (
    <div
      ref={rootRef}
      className="sphere-root"
      style={{
        '--segments-x': segments,
        '--segments-y': segments,
        '--overlay-blur-color': overlayBlurColor,
        '--tile-radius': imageBorderRadius,
        '--enlarge-radius': openedImageBorderRadius,
        '--image-filter': grayscale ? 'grayscale(1)' : 'none'
      }}
    >
      <main ref={mainRef} className="sphere-main">
        <div className="sphere-stage">
          <div ref={sphereRef} className="sphere">
            {items.map((item, index) => (
              <div
                key={`${item.x},${item.y},${index}`}
                className="item"
                data-src={item.src}
                data-offset-x={item.x}
                data-offset-y={item.y}
                data-size-x={item.sizeX}
                data-size-y={item.sizeY}
                style={{
                  '--offset-x': item.x,
                  '--offset-y': item.y,
                  '--item-size-x': item.sizeX,
                  '--item-size-y': item.sizeY
                }}
              >
                <div className="item__image" role="button" tabIndex={0} aria-label={item.alt || 'Open image'} onClick={onTileClick}>
                  <img src={item.src} draggable={false} alt={item.alt} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="overlay" />
        <div className="overlay overlay--blur" />
        <div className="edge-fade edge-fade--top" />
        <div className="edge-fade edge-fade--bottom" />

        <div className="viewer" ref={viewerRef}>
          <div ref={scrimRef} className="scrim" />
          <div ref={frameRef} className="frame" />
        </div>
      </main>
    </div>
  );
}
