import type { ChainNode } from './chainTypes';

export interface ChainGroup {
  name: string;
  nodes: ChainNode[];
}

export function buildChainGroups(nodes: ChainNode[]): ChainGroup[];
export function filterChainGroups(groups: ChainGroup[], query?: string): ChainGroup[];
export function getChainStats(groups: ChainGroup[], hints?: number, suggestions?: number): { chains: number; nodes: number; hints: number; suggestions: number };
export function getPendingReviewCount(payload: unknown): number;
export function resolveSelectedChain(groups: ChainGroup[], selectedName?: string): string;
export function summarizeChainNodeTypes(nodes: ChainNode[]): string;
