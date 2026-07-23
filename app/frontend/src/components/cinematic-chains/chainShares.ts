import type {
  EditableGlobalShare,
  GlobalShare,
  GlobalShareGroups,
  GlobalShares,
  ShareGroupKey,
} from './chainTypes';

const SHARE_GROUP_KEYS: ShareGroupKey[] = ['production', 'supply', 'demand'];

function parseShares(raw: unknown): unknown {
  if (typeof raw !== 'string') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function isGroupedGlobalShares(raw: unknown): raw is GlobalShareGroups {
  const data = parseShares(raw);
  if (!data || typeof data !== 'object' || Array.isArray(data) || !('groups' in data)) return false;
  const groups = data.groups;
  if (!groups || typeof groups !== 'object' || Array.isArray(groups)) return false;
  const keys = Object.keys(groups);
  return keys.length === SHARE_GROUP_KEYS.length
    && keys.every((key) => SHARE_GROUP_KEYS.includes(key as ShareGroupKey))
    && SHARE_GROUP_KEYS.every((key) => Array.isArray((groups as Record<string, unknown>)[key]));
}

export function normalizeShareGroups(raw: unknown): GlobalShareGroups['groups'] {
  const data = parseShares(raw);
  if (isGroupedGlobalShares(data)) {
    return {
      production: Array.isArray(data.groups.production) ? data.groups.production : [],
      supply: Array.isArray(data.groups.supply) ? data.groups.supply : [],
      demand: Array.isArray(data.groups.demand) ? data.groups.demand : [],
    };
  }
  return {
    production: Array.isArray(data) ? data : [],
    supply: [],
    demand: [],
  };
}

export function flattenGlobalShares(raw: unknown): EditableGlobalShare[] {
  const data = parseShares(raw);
  if (!isGroupedGlobalShares(data)) {
    return Array.isArray(data) ? data.map((share) => ({ ...share })) : [];
  }
  const groups = normalizeShareGroups(data);
  return SHARE_GROUP_KEYS.flatMap((group) => (
    groups[group].map((share) => ({ ...share, __shareGroup: group }))
  ));
}

export function serializeGlobalShares(
  shares: EditableGlobalShare[],
  grouped: boolean,
): GlobalShares {
  const clean = (share: EditableGlobalShare): GlobalShare => {
    const { __shareGroup: _group, ...value } = share;
    return value;
  };
  if (!grouped) return shares.map(clean);

  const groups: GlobalShareGroups['groups'] = { production: [], supply: [], demand: [] };
  for (const share of shares) {
    groups[share.__shareGroup || 'production'].push(clean(share));
  }
  return { groups };
}
