import React from 'react';

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return null;
  const cls = `b-${value.toLowerCase().replace(/[^a-z_]/g, '')}`;
  return <span className={`badge ${cls}`}>{value.replace(/_/g, ' ')}</span>;
}

export function Spinner() {
  return <span className="spinner" aria-label="loading" />;
}

export function EmptyState({ icon, title, hint }: { icon: string; title: string; hint?: string }) {
  return (
    <div className="empty">
      <div className="icon">{icon}</div>
      <h3 style={{ margin: '8px 0 4px' }}>{title}</h3>
      {hint && <p className="small muted" style={{ margin: 0 }}>{hint}</p>}
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-banner">
      ⚠ {message}{' '}
      {onRetry && <button className="btn" style={{ marginLeft: 8, padding: '4px 10px' }} onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Avatar({ name }: { name: string }) {
  const initial = (name || '?').trim().charAt(0).toUpperCase();
  return <span className="avatar">{initial}</span>;
}

export function ChannelIcon({ channel }: { channel: string }) {
  const icons: Record<string, string> = {
    instagram: '📸', whatsapp: '💬', facebook: '📘', email: '✉️', web: '🌐',
  };
  return <span title={channel}>{icons[channel] ?? '📨'}</span>;
}

export function StatCard({ num, label }: { num: number | string; label: string }) {
  return (
    <div className="stat-card">
      <div className="num">{num}</div>
      <div className="lbl">{label}</div>
    </div>
  );
}

export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 12 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 52 }} />
      ))}
    </div>
  );
}

export function useToast() {
  const [msg, setMsg] = React.useState<string | null>(null);
  const toast = React.useCallback((m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 3000);
  }, []);
  const node = msg ? (
    <div style={{ position: 'fixed', bottom: 24, right: 24, background: '#111827', color: '#fff', padding: '10px 16px', borderRadius: 8, zIndex: 99 }}>
      {msg}
    </div>
  ) : null;
  return { toast, node };
}
