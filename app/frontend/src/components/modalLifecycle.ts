type Focusable = { focus: () => void };

type ModalLifecycleOptions = {
  documentObject: Pick<Document, 'activeElement' | 'body'>;
  windowObject: Pick<Window, 'setTimeout' | 'clearTimeout' | 'addEventListener' | 'removeEventListener'>;
  getFocusTarget: () => Focusable | null;
  isDismissible: () => boolean;
  onClose: () => void;
};

function isFocusable(value: unknown): value is Focusable {
  return Boolean(value && typeof value === 'object' && 'focus' in value && typeof value.focus === 'function');
}

export function installModalLifecycle(options: ModalLifecycleOptions) {
  const previousFocus = isFocusable(options.documentObject.activeElement)
    ? options.documentObject.activeElement
    : null;
  const previousOverflow = options.documentObject.body.style.overflow;
  options.documentObject.body.style.overflow = 'hidden';
  const focusTimer = options.windowObject.setTimeout(() => options.getFocusTarget()?.focus(), 0);
  const handleKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape' && options.isDismissible()) options.onClose();
  };
  options.windowObject.addEventListener('keydown', handleKeydown);

  return () => {
    options.windowObject.clearTimeout(focusTimer);
    options.windowObject.removeEventListener('keydown', handleKeydown);
    options.documentObject.body.style.overflow = previousOverflow;
    previousFocus?.focus();
  };
}

export function getModalBackdropHandler(dismissible: boolean, onClose: () => void) {
  return dismissible ? onClose : undefined;
}
