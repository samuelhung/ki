import type { EventItem } from '../cinematic-ingest/ingestTypes';
import type { Source } from '../../types';

interface LibraryFilters {
  topic?: string;
  status?: string;
  source?: string;
  state?: string;
  query?: string;
}

export function filterLibraryEvents(events: EventItem[], filters?: LibraryFilters): EventItem[];
export function filterSources(sources: Source[], filters?: LibraryFilters): Source[];
export function getLibraryStats(events: EventItem[]): { total: number; ready: number; processing: number; errors: number };
export function getSourceStats(sources: Source[]): { total: number; enabled: number; paused: number; errors: number };
export function resolveVisibleItem<T extends { id: string }>(items: T[], selectedId: string | null): T | null;
