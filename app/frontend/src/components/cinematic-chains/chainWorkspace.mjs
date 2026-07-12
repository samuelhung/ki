export function buildChainGroups(nodes) {
  const groups = new Map();
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (!groups.has(node.chain)) groups.set(node.chain, []);
    groups.get(node.chain).push(node);
  }
  return [...groups.entries()].map(([name, chainNodes]) => ({
    name,
    nodes: [...chainNodes].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0)),
  }));
}

export function filterChainGroups(groups, query = '') {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return groups;
  return groups.filter((group) => `${group.name} ${group.nodes.map((node) => node.name).join(' ')}`.toLowerCase().includes(normalized));
}

export function getChainStats(groups, hints = 0, suggestions = 0) {
  return {
    chains: groups.length,
    nodes: groups.reduce((sum, group) => sum + group.nodes.length, 0),
    hints,
    suggestions,
  };
}
