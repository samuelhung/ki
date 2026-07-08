import { useEffect, useState } from 'react';

export type ToastMessage = { text: string; type: 'success' | 'info' };

export function useToastMessage(timeoutMs = 3000) {
  const [toast, setToast] = useState<ToastMessage | null>(null);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), timeoutMs);
    return () => window.clearTimeout(timer);
  }, [timeoutMs, toast]);

  return { toast, setToast };
}
