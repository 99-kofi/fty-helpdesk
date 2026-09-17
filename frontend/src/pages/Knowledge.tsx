import { useEffect, useState } from 'react';
import { api, KBArticle } from '../api/client';
import { EmptyState, ErrorBanner, SkeletonList, useToast } from '../components/ui';

export default function Knowledge() {
  const [rows, setRows] = useState<KBArticle[]>([]);
  const [cats, setCats] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [fCat, setFCat] = useState('');
  const [editing, setEditing] = useState<KBArticle | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ category: '', title: '', body: '' });
  const { toast, node } = useToast();

  async function load() {
    try {
      setErr(null);
      const params = new URLSearchParams();
      if (q.trim()) params.set('q', q.trim());
      if (fCat) params.set('category', fCat);
      const [arts, categories] = await Promise.all([
        api<KBArticle[]>(`/knowledge?${params.toString()}`),
        api<string[]>('/knowledge/categories').catch(() => [] as string[]),
      ]);
      setRows(arts);
      setCats(categories);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to load knowledge base');
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, fCat]);

  function startEdit(a?: KBArticle) {
    if (a) {
      setEditing(a);
      setForm({ category: a.category, title: a.title, body: a.body });
    } else {
      setEditing(null);
      setForm({ category: cats[0] ?? 'General', title: '', body: '' });
    }
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditing(null);
    setForm({ category: '', title: '', body: '' });
  }

  async function save() {
    if (!form.title.trim() || !form.body.trim()) { toast('Title and body are required'); return; }
    try {
      if (editing) {
        await api(`/knowledge/${editing.id}`, { method: 'PATCH', body: JSON.stringify(form) });
        toast('Article updated');
      } else {
        await api('/knowledge', { method: 'POST', body: JSON.stringify({ ...form, category: form.category || 'General' }) });
        toast('Article added');
      }
      closeForm();
      load();
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Save failed (manager only?)');
    }
  }

  async function remove(id: number) {
    if (!confirm('Delete this article?')) return;
    await api(`/knowledge/${id}`, { method: 'DELETE' });
    load();
  }

  return (
    <div>
      {node}
      <div className="row" style={{ marginBottom: 12 }}>
        <h1 style={{ margin: 0 }}>📚 Knowledge Base</h1>
        <span className="grow" />
        <input className="input" style={{ maxWidth: 240 }} placeholder="🔍 Search answers…" value={q} onChange={e => setQ(e.target.value)} />
        <select className="select" value={fCat} onChange={e => setFCat(e.target.value)}>
          <option value="">All categories</option>
          {cats.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <button className="btn btn-primary" onClick={() => startEdit(undefined)}>＋ New article</button>
      </div>
      {err && <ErrorBanner message={err} onRetry={load} />}
      {showForm && (
        <div className="card" style={{ marginBottom: 12 }}>
          <b>{editing ? `Edit #${editing.id}` : 'New article'}</b>
          <div className="row" style={{ marginTop: 8 }}>
            <input className="input" style={{ maxWidth: 200 }} placeholder="Category" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} />
            <input className="input" placeholder="Title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
          </div>
          <textarea className="textarea" style={{ marginTop: 8, minHeight: 90 }} placeholder="Approved answer…" value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn btn-primary" onClick={save}>Save</button>
            <button className="btn" onClick={closeForm}>Cancel</button>
          </div>
        </div>
      )}
      {loading ? <SkeletonList /> : rows.length === 0 ? (
        <EmptyState icon="📚" title="No articles" hint="Add approved answers — agents and AI suggestions draw from here." />
      ) : rows.map(a => (
        <div key={a.id} className="card" style={{ marginBottom: 10 }}>
          <div className="row">
            <span className="badge b-normal">{a.category}</span>
            <b>{a.title}</b>
            <span className="grow" />
            <button className="btn" style={{ padding: '4px 10px' }} onClick={() => startEdit(a)}>Edit</button>
            <button className="btn" style={{ padding: '4px 10px' }} onClick={() => remove(a.id)}>Delete</button>
          </div>
          <p className="small" style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap' }}>{a.body}</p>
        </div>
      ))}
    </div>
  );
}
