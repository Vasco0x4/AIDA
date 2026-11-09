import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { GitBranch, ArrowLeft, KeyRound, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import service from '../services/gitIntegrationService';
const field = 'w-full rounded-lg border border-neutral-300 dark:border-neutral-600 bg-white dark:bg-neutral-900 p-2.5 text-sm';
const muted = 'text-sm text-neutral-600 dark:text-neutral-300';
export default function GitIntegrations() {
  const { user } = useAuth();
  const admin = user?.role === 'admin';
  const [connections, setConnections] = useState([]), [id, setId] = useState('');
  const [items, setItems] = useState([]), [grants, setGrants] = useState([]);
  const [page, setPage] = useState(1), [more, setMore] = useState(false), [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [adding, setAdding] = useState(false), [name, setName] = useState(''), [provider, setProvider] = useState('github');
  const [origin, setOrigin] = useState('https://github.com'), [token, setToken] = useState(''), [replacement, setReplacement] = useState('');
  const [privateNetwork, setPrivateNetwork] = useState(false), [tick, setTick] = useState(0);
  const selected = connections.find(c => String(c.id) === id);
  function fail(e) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Request failed. Check the connection and retry.'); }
  useEffect(() => {
    if (!admin) return;
    let alive = true;
    service.list().then(rows => { if (alive) { setConnections(rows); setId(old => old || String(rows[0]?.id || '')); } }).catch(e => { if (alive) fail(e); });
    return () => { alive = false; };
  }, [admin, tick]);
  useEffect(() => {
    setItems([]); setGrants([]); setMore(false);
    if (!admin || !id || !selected) return;
    let alive = true;
    service.grants(id).then(rows => { if (alive) setGrants(rows); }).catch(e => { if (alive) fail(e); });
    if (selected.enabled) service.repositories(id, page).then(data => { if (alive) { setItems(data.items); setMore(data.has_more); } }).catch(e => { if (alive) fail(e); });
    return () => { alive = false; };
  }, [admin, id, page, selected?.enabled, tick]);
  async function perform(fn) {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); setTick(t => t + 1); } catch (e) { fail(e); } finally { setBusy(false); }
  }
  async function connect(e) {
    e.preventDefault();
    await perform(async () => {
      const row = await service.create({ name: name.trim(), provider, origin: origin.trim(), token, allow_private_network: privateNetwork });
      setToken(''); setName(''); setAdding(false); setId(String(row.id)); setPage(1);
      setNotice('Connected. Choose which repositories AIDA may import. Nothing is selected automatically.');
    });
  }
  const allowed = grants.filter(g => g.allowed);
  const visible = items.filter(r => r.path.toLowerCase().includes(search.toLowerCase()));
  return <div className="mx-auto max-w-6xl space-y-5">
    <header className="aida-page-header flex flex-wrap justify-between gap-4">
      <div><p className="aida-eyebrow">Application Security / Connections</p><h1 className="text-2xl font-bold flex items-center gap-3"><GitBranch className="text-primary-500" />Git integrations</h1><p className={`${muted} mt-2`}>Connect your account. Allow repositories. Review a commit.</p></div>
      <Link className="btn btn-secondary" to="/appsec"><ArrowLeft size={16} />Back to AppSec</Link>
    </header>
    {!admin ? <div className="card">Ask an administrator to connect GitHub or GitLab and allow repositories for this workspace.</div> : <>
      <div className="grid gap-3 sm:grid-cols-3">{[['1 · Connect', 'Use a token with read access only.'], ['2 · Choose repositories', 'AIDA imports only the repositories you allow.'], ['3 · Review source', 'Open a project and scan a branch or commit.']].map(([title, text]) => <div className="card" key={title}><h2 className="font-semibold">{title}</h2><p className={`${muted} mt-1`}>{text}</p></div>)}</div>
      {error && <p role="alert" className="rounded-xl bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200 p-4">{error}</p>}
      {notice && <p role="status" className="rounded-xl bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200 p-4">{notice}</p>}
      {(adding || !connections.length) && <form className="card space-y-4" onSubmit={connect}>
        <h2 className="font-semibold text-lg flex gap-2 items-center"><KeyRound size={19} />Connect GitHub or GitLab</h2>
        <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm">Connection name<input className={`${field} mt-1`} value={name} onChange={e => setName(e.target.value)} required maxLength={100} placeholder="Engineering repositories" /></label>
        <label className="text-sm">Provider<select className={`${field} mt-1`} value={provider} onChange={e => { setProvider(e.target.value); setOrigin(e.target.value === 'github' ? 'https://github.com' : 'https://gitlab.com'); }}><option value="github">GitHub</option><option value="gitlab">GitLab</option></select></label></div>
        <label className="block text-sm">Server URL<input className={`${field} mt-1`} type="url" value={origin} onChange={e => setOrigin(e.target.value)} required placeholder="https://gitlab.company.com" /></label>
        <label className="block text-sm font-medium">Access token<input className={`${field} mt-1`} type="password" autoComplete="new-password" value={token} onChange={e => setToken(e.target.value)} required minLength={8} maxLength={4096} placeholder="Paste your access token here" /></label>
        <p className={muted}>{provider === 'github' ? 'Fine-grained GitHub token: select repositories, then Contents: Read-only and Metadata: Read-only.' : 'GitLab access token: read_api scope. The repository list includes projects where the token identity is a member.'} AIDA cannot expand permissions granted by your provider.</p>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={privateNetwork} onChange={e => setPrivateNetwork(e.target.checked)} />Allow this server on a private network (self-hosted HTTPS only; certificate verification remains enabled).</label>
        <p className={muted}>Tokens are encrypted on the backend and never shown again. Allowed projects and results are shared with AIDA workspace users; only administrators manage connections.</p>
        <div className="flex gap-2"><button className="btn btn-primary" disabled={busy}>{busy ? 'Checking…' : 'Check & connect'}</button>{connections.length > 0 && <button type="button" className="btn btn-secondary" onClick={() => { setAdding(false); setToken(''); }}>Cancel</button>}</div>
      </form>}
      {connections.length > 0 && <section className="card space-y-4">
        <div className="flex flex-wrap items-end gap-3"><label className="text-sm flex-1 min-w-0">Connection<select className={`${field} mt-1`} value={id} onChange={e => { setId(e.target.value); setPage(1); setReplacement(''); setError(''); }} disabled={busy}>{connections.map(c => <option key={c.id} value={c.id}>{c.name} · {c.provider}{c.enabled ? '' : ' · disconnected'}</option>)}</select></label><button className="btn btn-secondary" onClick={() => setAdding(true)}>Add connection</button></div>
        {selected && <><p className={muted}>{selected.origin} · {selected.account} · {selected.enabled ? 'Connected' : 'Disconnected'}</p>
          <div className="flex flex-wrap gap-2"><button className="btn btn-secondary" disabled={busy || !selected.enabled} onClick={() => perform(async () => { await service.check(id); setNotice('Connection verified.'); })}>Check connection</button><button className="btn btn-secondary" disabled={busy || !selected.enabled} onClick={() => { if (window.confirm('Disconnect and remove the stored token? Repository access will be revoked and active repository scans cancelled. Existing results remain available.')) perform(async () => { await service.disconnect(id); setNotice('Disconnected. Token removed and repository permissions revoked.'); }); }}>Disconnect</button></div>
          <details><summary className="cursor-pointer text-sm font-medium">Replace token / reconnect</summary><form className="mt-3 flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); perform(async () => { await service.rotate(id, replacement); setReplacement(''); setNotice('Token replaced. Review repository permissions below.'); }); }}><label className="flex-1 text-sm">New access token<input className={`${field} mt-1`} type="password" autoComplete="new-password" value={replacement} onChange={e => setReplacement(e.target.value)} required minLength={8} /></label><button className="btn btn-secondary self-end" disabled={busy}>Verify & replace</button></form></details>
        </>}
      </section>}
      {selected && <div className="grid gap-5 lg:grid-cols-2"><section className="card space-y-4 min-w-0"><h2 className="font-semibold text-lg">Available repositories</h2><p className={muted}>Select a repository to create its AppSec project. This grants access within AIDA, not additional permissions at your Git provider.</p><label className="block text-sm">Filter this page<input className={`${field} mt-1`} value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a repository…" /></label>
        {!selected.enabled ? <p className={muted}>Replace the token to reconnect.</p> : !visible.length ? <p className={muted}>No repositories on this page. Check token permissions or try refreshing.</p> : <ul className="divide-y divide-neutral-200 dark:divide-neutral-700">{visible.map(r => <li key={r.provider_id} className="py-3"><label className="flex items-start gap-3"><input type="checkbox" className="mt-1" aria-label={`Allow ${r.path}`} checked={r.allowed} disabled={busy} onChange={e => { const enabled = e.target.checked; perform(async () => { await service.allow(id, r.provider_id, enabled); setNotice(enabled ? 'Repository allowed. Open its project to start a review.' : 'Repository access revoked.'); }); }} /><span className="min-w-0"><span className="block font-medium break-all">{r.path}</span><span className={muted}>{r.private ? 'Private' : 'Public'} · {r.default_branch}</span></span></label></li>)}</ul>}
        <div className="flex flex-wrap gap-2 items-center"><button className="btn btn-secondary" disabled={page === 1 || busy} onClick={() => setPage(p => p - 1)}>Previous</button><span className={muted}>Page {page}</span><button className="btn btn-secondary" disabled={!more || busy} onClick={() => setPage(p => p + 1)}>Next</button><button className="btn btn-secondary" disabled={busy} onClick={() => { setError(''); setTick(t => t + 1); }}>Refresh</button></div>
      </section><section className="card space-y-4 min-w-0"><h2 className="font-semibold text-lg flex items-center gap-2"><CheckCircle2 size={19} className="text-emerald-500" />Allowed repositories · {allowed.length}</h2><p className={muted}>Opening a project does not start a scan. You choose its branch or commit and any optional AI review.</p>{!allowed.length && <p className={muted}>No repositories allowed yet.</p>}{allowed.map(g => <div key={g.provider_id} className="rounded-xl border border-neutral-200 dark:border-neutral-700 p-3 space-y-3"><p className="font-medium break-all">{g.path}</p><div className="flex flex-wrap gap-2"><Link className="btn btn-primary" to={`/appsec?project=${g.project_id}`}>Open project</Link><button className="btn btn-secondary" disabled={busy} onClick={() => perform(async () => { await service.allow(id, g.provider_id, false); setNotice('Repository access revoked. Existing results are retained.'); })}>Revoke access</button></div></div>)}</section></div>}
      <p className={muted}>Need setup details? <Link className="underline" to="/guide?doc=appsec">Read the AppSec guide</Link>. No repository code is executed during a review.</p>
    </>}
  </div>;
}
