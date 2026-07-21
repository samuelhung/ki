import { useEffect, useState } from 'react';
import { backendUrl, getApiToken, getBackendUrl } from '../../api';
import { attachMediaTransportRecovery, MEDIA_CONNECTION_CHANGE_EVENT, synchronizeMediaTransport } from '../../mediaTransport';

function useConnectionRevision(): number {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const update = () => setRevision((value) => value + 1);
    window.addEventListener(MEDIA_CONNECTION_CHANGE_EVENT, update);
    return () => window.removeEventListener(MEDIA_CONNECTION_CHANGE_EVENT, update);
  }, []);
  return revision;
}

export function useMediaTransportConnection(): void {
  useEffect(() => {
    let controller: AbortController | null = null;
    const getConnection = () => ({ backendUrl: getBackendUrl(), token: getApiToken() });
    const synchronize = () => {
      controller?.abort();
      controller = new AbortController();
      void synchronizeMediaTransport(
        getConnection(),
        controller.signal,
      ).catch(() => {});
    };
    const detachRecovery = attachMediaTransportRecovery(getConnection);
    synchronize();
    window.addEventListener(MEDIA_CONNECTION_CHANGE_EVENT, synchronize);
    return () => {
      window.removeEventListener(MEDIA_CONNECTION_CHANGE_EVENT, synchronize);
      detachRecovery();
      controller?.abort();
    };
  }, []);
}

export function useAuthenticatedMediaUrl(path: string | null): string {
  const [mediaUrl, setMediaUrl] = useState('');
  const connectionRevision = useConnectionRevision();

  useEffect(() => {
    const controller = new AbortController();

    if (!path) {
      setMediaUrl('');
      return () => controller.abort();
    }
    const token = getApiToken();
    if (!token) {
      setMediaUrl(backendUrl(path));
      return () => controller.abort();
    }

    setMediaUrl('');
    synchronizeMediaTransport(
      { backendUrl: getBackendUrl(), token, path },
      controller.signal,
    ).then(setMediaUrl).catch(() => {
      if (!controller.signal.aborted) setMediaUrl('');
    });

    return () => controller.abort();
  }, [connectionRevision, path]);

  return mediaUrl;
}
