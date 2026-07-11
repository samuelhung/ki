export function computeCinematicNavigationGeometry(totalHubs: number, activeHubIndex: number, childCount: number) {
  const safeIndex = Math.max(0, activeHubIndex);
  const hubRowHeight = 40;
  const hubBottomPadding = 24;
  const hubHeight = 330;
  const childMenuHeight = Math.max(134, childCount * hubRowHeight + 18);
  const activeHubCenter = hubBottomPadding + ((Math.max(1, totalHubs) - 1 - safeIndex) * hubRowHeight) + 15;
  const childMenuBottom = Math.max(
    hubBottomPadding,
    Math.min(hubHeight - childMenuHeight - 20, activeHubCenter - childMenuHeight / 2),
  );

  return { childMenuHeight, childMenuBottom };
}
