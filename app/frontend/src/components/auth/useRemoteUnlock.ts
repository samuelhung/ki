import { useCallback, useEffect, useState } from 'react';
import { getApiToken, setApiToken } from '../../api';
import {
  shouldRequireRemoteUnlock,
  subscribeRemoteAuthRequired,
} from './remoteUnlockRuntime';
import { validateRemoteUnlockToken } from './remoteUnlockRequest';

function requiresUnlock(token: string): boolean {
  return shouldRequireRemoteUnlock({
    isDev: import.meta.env.DEV,
    protocol: window.location.protocol,
    hostname: window.location.hostname,
    token,
  });
}

export function useRemoteUnlock() {
  const [locked, setLocked] = useState(() => requiresUnlock(getApiToken()));

  useEffect(() => subscribeRemoteAuthRequired(() => {
    setApiToken('');
    setLocked(requiresUnlock(''));
  }), []);

  const unlock = useCallback(async (token: string) => {
    await validateRemoteUnlockToken(token);
    setApiToken(token);
    window.location.reload();
  }, []);

  return { locked, unlock };
}
