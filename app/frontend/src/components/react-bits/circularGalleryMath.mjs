export function lerp(current, target, ease) {
  return current + (target - current) * ease;
}

export function snapTarget(target, itemWidth) {
  if (!itemWidth) return target;
  const item = itemWidth * Math.round(Math.abs(target) / itemWidth);
  return target < 0 ? -item : item;
}

export function wrapOffset(position, planeHalfWidth, viewportHalfWidth, loopWidth, direction) {
  if (direction === 'right' && position + planeHalfWidth < -viewportHalfWidth) return -loopWidth;
  if (direction === 'left' && position - planeHalfWidth > viewportHalfWidth) return loopWidth;
  return 0;
}

export function arcTransform(x, viewportWidth, bend) {
  if (!bend || x === 0) return { y: 0, rotation: 0 };
  const halfWidth = viewportWidth / 2;
  const absoluteBend = Math.abs(bend);
  const radius = (halfWidth * halfWidth + absoluteBend * absoluteBend) / (2 * absoluteBend);
  const effectiveX = Math.min(Math.abs(x), halfWidth);
  const arc = radius - Math.sqrt(Math.max(0, radius * radius - effectiveX * effectiveX));
  const angle = Math.asin(Math.min(1, effectiveX / radius));
  return bend > 0
    ? { y: -arc, rotation: -Math.sign(x) * angle }
    : { y: arc, rotation: Math.sign(x) * angle };
}
