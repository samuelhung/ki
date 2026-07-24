import { useState, type FormEvent } from 'react';
import { KeyRound, Loader2, LockKeyhole, Sparkles } from 'lucide-react';
import KiMagicBentoFrame from '../react-bits/KiMagicBentoFrame';
import { remoteUnlockErrorMessage } from './remoteUnlockRequest';
import './RemoteUnlockGate.css';

interface RemoteUnlockGateProps {
  onUnlock(token: string): Promise<void>;
}

export default function RemoteUnlockGate({ onUnlock }: RemoteUnlockGateProps) {
  const [token, setToken] = useState('');
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (checking) return;
    setChecking(true);
    setError('');
    try {
      await onUnlock(token);
    } catch (reason) {
      setError(remoteUnlockErrorMessage(reason));
      setChecking(false);
    }
  }

  return (
    <div className="remote-unlock-backdrop">
      <div className="remote-unlock-stage">
        <KiMagicBentoFrame className="remote-unlock-frame" cardClassName="remote-unlock-card">
          <section
            className="remote-unlock-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="remote-unlock-title"
          >
            <header className="remote-unlock-header">
              <span>SECURE ACCESS</span>
              <div>
                <Sparkles aria-hidden="true" />
                <h2 id="remote-unlock-title">解锁知几</h2>
              </div>
              <p>验证当前会话后载入知几数据。</p>
            </header>

            <form onSubmit={submit}>
              <label>
                <span><KeyRound aria-hidden="true" />访问令牌</span>
                <input
                  autoFocus
                  type="password"
                  autoComplete="current-password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="KI_API_TOKEN"
                  aria-describedby="remote-unlock-status"
                />
              </label>
              <button type="submit" disabled={checking || !token.trim()}>
                {checking
                  ? <Loader2 className="remote-unlock-spinner" aria-hidden="true" />
                  : <LockKeyhole aria-hidden="true" />}
                <span>{checking ? '正在验证' : '进入知几'}</span>
                <small>{checking ? 'VERIFYING' : 'ENTER'}</small>
              </button>
              <p id="remote-unlock-status" className="remote-unlock-status" aria-live="polite">
                {error}
              </p>
            </form>
          </section>
        </KiMagicBentoFrame>
      </div>
    </div>
  );
}
