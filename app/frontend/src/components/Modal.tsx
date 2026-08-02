import React, { ReactNode, useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { getModalBackdropHandler, installModalLifecycle } from './modalLifecycle';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  dismissible?: boolean;
  initialFocusRef?: React.RefObject<HTMLButtonElement | null>;
}

const _maxWidthClass: Record<string, string> = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl', '2xl': 'max-w-2xl' };

export default function Modal({
  open,
  onClose,
  title,
  children,
  maxWidth = 'lg',
  dismissible = true,
  initialFocusRef,
}: ModalProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const dismissibleRef = useRef(dismissible);

  onCloseRef.current = onClose;
  dismissibleRef.current = dismissible;

  useEffect(() => {
    if (!open) return;
    return installModalLifecycle({
      documentObject: document,
      windowObject: window,
      getFocusTarget: () => initialFocusRef?.current ?? panelRef.current,
      isDismissible: () => dismissibleRef.current,
      onClose: () => onCloseRef.current(),
    });
  }, [initialFocusRef, open]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={getModalBackdropHandler(dismissible, onClose)} />
      {/* Panel */}
      <div ref={panelRef} tabIndex={-1} className={`relative z-10 w-full ${_maxWidthClass[maxWidth]} mx-4 bg-[#141518] border border-[#2A2B30] rounded-xl shadow-2xl`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#2A2B30]">
          <h2 id={titleId} className="text-lg font-semibold text-white">{title}</h2>
          {dismissible && <button type="button" onClick={onClose} aria-label="关闭"
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2A2B30] transition-colors">
            <X size={18} />
          </button>}
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
