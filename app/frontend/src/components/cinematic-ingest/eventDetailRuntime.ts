type SelectedOwner = { selectedId?: string; sequence: number };
type ActiveActionName = 'summarize' | 'contemplate' | 'link' | 'chain' | 'sync';

export function createSelectedEventOwner(initialSelectedId?: string) {
  let selectedId = initialSelectedId;
  let sequence = 0;
  const capture = (): SelectedOwner => ({ selectedId, sequence });
  return {
    capture,
    select(nextSelectedId?: string) {
      if (nextSelectedId !== selectedId) {
        selectedId = nextSelectedId;
        sequence += 1;
      }
      return capture();
    },
    isCurrent(owner: SelectedOwner) {
      return owner.selectedId === selectedId && owner.sequence === sequence;
    },
    invalidate(owner: SelectedOwner) {
      if (owner.selectedId !== selectedId || owner.sequence !== sequence) return;
      selectedId = undefined;
      sequence += 1;
    },
  };
}

export function toMediaPath(absolutePath: string | undefined): string | null {
  if (!absolutePath) return null;
  const index = absolutePath.indexOf('/data/ingest/');
  if (index === -1) return null;
  return '/ingest' + absolutePath.substring(index + '/data/ingest'.length);
}

export function createActiveActionRegistry() {
  const active = new Set<string>(); const listeners = new Set<() => void>();
  let revision = 0;
  const keyFor = (name: ActiveActionName, eventId: string) => `${name}:${eventId}`;
  const emit = () => { revision += 1; listeners.forEach((listener) => listener()); };
  return {
    begin(name: ActiveActionName, eventId: string) {
      const key = keyFor(name, eventId); if (active.has(key)) return null;
      active.add(key); emit(); return key;
    },
    end(key: string | null) { if (key && active.delete(key)) emit(); },
    isActive(name: ActiveActionName, eventId?: string) { return Boolean(eventId && active.has(keyFor(name, eventId))); },
    subscribe(listener: () => void) { listeners.add(listener); return () => listeners.delete(listener); },
    getSnapshot() { return revision; },
  };
}

export function activeActionState(
  actions: ReturnType<typeof createActiveActionRegistry>,
  eventId?: string,
) {
  return {
    summarizingId: actions.isActive('summarize', eventId) ? eventId || null : null,
    contemplating: actions.isActive('contemplate', eventId),
    contemplateLinking: actions.isActive('link', eventId),
    chainLoading: actions.isActive('chain', eventId),
    syncingHints: actions.isActive('sync', eventId),
  };
}
