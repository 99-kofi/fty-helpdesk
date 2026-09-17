import { useEffect, useMemo, useState } from 'react';
import { api, Agent, Customer } from '../api/client';
import { Avatar, EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

export default function Customers() {
  const [rows, setRows] = useState<Customer[]>([]);
  const [me, setMe] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      const [data, myself] = await Promise.all([
        api<Customer[]>('/customers'),
        api<Agent>('/auth/me').catch(() => null as unknown as Agent),
      ]);
      setRows(data);
      setMe(myself);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load customers');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter(c =>
      (c.name ?? '').toLowerCase().includes(s)
      || (c.email ?? '').toLowerCase().includes(s)
      || (c.phone ?? '').includes(s)
    );
  }, [rows, q]);

  async function create() {
    if (!name.trim() && !email.trim() && !phone.trim()) { toast('Enter at least a name, email, or phone'); return; }
    try {
      await api('/customers', { method: 'POST', body: JSON.stringify({ name: name || null, email: email || null, phone: phone || null }) });
      setName(''); setEmail(''); setPhone('');
      toast('Customer added');
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Create failed');
    }
  }

  return (
    <div>
      {node}
      <div className="row" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>👥 Customers</h1>
        <span className="grow" />
        <input className="input" style={{ maxWidth: 240 }} placeholder="🔍 Search…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      {err && <ErrorBanner message={err} onRetry={load} />}
      {me?.role === 'admin' && (
      <div className="card" style={{ marginBottom: 12 }}>
        <b>＋ New customer</b>
        <div className="row" style={{ marginTop: 8 }}>
          <input className="input" placeholder="Name" value={name} onChange={e => setName(e.target.value)} />
          <input className="input" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
          <input className="input" placeholder="Phone" value={phone} onChange={e => setPhone(e.target.value)} />
          <button className="btn btn-primary" onClick={create}>Add</button>
        </div>
      </div>
      )}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? <SkeletonList /> : filtered.length === 0 ? (
          <EmptyState icon="👥" title="No customers" hint="Add one above — channel contacts resolve here automatically." />
        ) : (
          <table className="table">
            <thead><tr><th></th><th>Name</th><th>Email</th><th>Phone</th></tr></thead>
            <tbody>
              {filtered.map(c => (
                <tr key={c.id}>
                  <td><Avatar name={c.name ?? `#${c.id}`} /></td>
                  <td><b>{c.name ?? `Customer #${c.id}`}</b></td>
                  <td>{c.email ?? '—'}</td>
                  <td>{c.phone ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
