import { AlertTriangle, Loader2, Trash2 } from 'lucide-react';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';

import Modal from '../Modal';
import { createSystemDialogController } from './systemDialogRuntime';
import type { SystemDialogController } from './systemDialogRuntime';

const SystemDialogContext = createContext<Pick<SystemDialogController, 'alert' | 'confirmAction'> | null>(null);

export function useSystemDialog() {
  const value = useContext(SystemDialogContext);
  if (!value) throw new Error('useSystemDialog must be used inside SystemDialogProvider');
  return value;
}

export function SystemDialogProvider({ children }: { children: React.ReactNode }) {
  const [controller] = useState(() => createSystemDialogController());
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const acknowledgeRef = useRef<HTMLButtonElement>(null);
  const api = useMemo(() => ({
    alert: controller.alert,
    confirmAction: controller.confirmAction,
  }), [controller]);

  useEffect(() => () => controller.destroy(), [controller]);

  const close = useCallback(() => {
    if (snapshot?.pending) return;
    if (snapshot?.kind === 'alert') controller.acknowledge();
    else controller.cancel();
  }, [controller, snapshot]);

  return (
    <SystemDialogContext.Provider value={api}>
      {children}
      {snapshot && <Modal
        open
        title={snapshot.title}
        maxWidth="sm"
        dismissible={!snapshot.pending}
        initialFocusRef={snapshot.kind === 'alert' ? acknowledgeRef : cancelRef}
        onClose={close}
      >
        <div className="space-y-5">
          <div className="flex items-start gap-3">
            {snapshot.tone === 'danger' && <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-400" />}
            <p className="text-sm leading-6 text-gray-300 whitespace-pre-wrap break-words">{snapshot.message}</p>
          </div>
          <div className="flex justify-end gap-2">
            {snapshot.kind === 'confirm' ? <>
              <button ref={cancelRef} type="button" onClick={() => controller.cancel()} disabled={snapshot.pending} className="px-4 py-2 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 border border-gray-600 hover:border-gray-500 transition-colors disabled:opacity-50">{snapshot.cancelLabel}</button>
              <button type="button" onClick={() => void controller.confirm()} disabled={snapshot.pending} className="px-4 py-2 rounded-lg text-xs font-medium bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 flex items-center gap-1.5">
                {snapshot.pending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                {snapshot.pending ? snapshot.pendingLabel : snapshot.confirmLabel}
              </button>
            </> : <button ref={acknowledgeRef} type="button" onClick={() => controller.acknowledge()} className="px-4 py-2 rounded-lg text-xs font-medium bg-white/10 text-white hover:bg-white/15 border border-white/15 transition-colors">{snapshot.acknowledgeLabel}</button>}
          </div>
        </div>
      </Modal>}
    </SystemDialogContext.Provider>
  );
}
