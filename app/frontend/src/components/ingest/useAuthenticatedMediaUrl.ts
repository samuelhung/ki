import { useEffect, useState } from 'react';
import { apiFetch, backendUrl, getApiToken } from '../../api';
import { loadAuthenticatedObjectUrl, shouldLoadAuthenticatedObjectUrl } from '../../apiFetchRuntime';

export function useAuthenticatedMediaUrl(path: string | null): string {
  const [mediaUrl, setMediaUrl] = useState('');

  useEffect(() => {
    let active = true;
    let revoke = () => {};

    if (!path) {
      setMediaUrl('');
      return () => { active = false; };
    }
    if (!shouldLoadAuthenticatedObjectUrl(path, getApiToken())) {
      setMediaUrl(backendUrl(path));
      return () => { active = false; };
    }

    setMediaUrl('');
    loadAuthenticatedObjectUrl(path, apiFetch)
      .then((asset) => {
        if (!active) {
          asset.revoke();
          return;
        }
        revoke = asset.revoke;
        setMediaUrl(asset.url);
      })
      .catch(() => {
        if (active) setMediaUrl('');
      });

    return () => {
      active = false;
      revoke();
    };
  }, [path]);

  return mediaUrl;
}
