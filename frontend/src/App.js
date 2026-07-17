import React, { useState, useEffect, useRef } from 'react';
import { useApi, triggerFetch } from './hooks/useApi';
import OverviewCards from './components/OverviewCards';
import TimelineChart from './components/TimelineChart';
import DomainChart from './components/DomainChart';
import GeoMap from './components/GeoMap';
import SourcesTable from './components/SourcesTable';
import AlertsPanel from './components/AlertsPanel';
import './App.css';

const DAYS_OPTIONS = [1, 7, 14, 30, 90];
const TABS = [
  { id: 'overview', label: '⊞ Overview' },
  { id: 'rejects',  label: '✕ Reject / Quarantena' },
];

function Spinner() { return <div className="spinner" />; }

function DomainSearch({ days, value, onChange }) {
  const [input, setInput] = useState(value);
  const [open, setOpen]   = useState(false);
  const boxRef            = useRef(null);
  const { data: allDomains } = useApi(`/api/stats/domains?days=${days}`, [days]);

  const suggestions = (allDomains || []).filter(
    (d) => d.toLowerCase().includes(input.toLowerCase()) && d !== input
  );

  useEffect(() => { setInput(value); }, [value]);
  useEffect(() => {
    const handler = (e) => { if (!boxRef.current?.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const select = (d) => { setInput(d); onChange(d); setOpen(false); };
  const clear   = () => { setInput(''); onChange(''); setOpen(false); };

  return (
    <div className="domain-search" ref={boxRef}>
      <div className={`domain-input-wrap ${value ? 'active' : ''}`}>
        <span className="domain-icon">⊕</span>
        <input
          className="domain-input" placeholder="Filtra per dominio…" value={input}
          onChange={e => { setInput(e.target.value); setOpen(true); if (!e.target.value) onChange(''); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { onChange(input); setOpen(false); }
            if (e.key === 'Escape') clear();
          }}
        />
        {input && <button className="domain-clear" onClick={clear} title="Rimuovi filtro">✕</button>}
      </div>
      {open && suggestions.length > 0 && (
        <ul className="domain-suggestions">
          {suggestions.map((d) => (
            <li key={d} onMouseDown={() => select(d)}>
              <span className="sug-icon">◈</span> {d}
            </li>
          ))}
        </ul>
      )}
      {value && <span className="domain-badge">Filtro attivo: <strong>{value}</strong></span>}
    </div>
  );
}

export default function App() {
  const [days, setDays]       = useState(30);
  const [domain, setDomain]   = useState('');
  const [fetching, setFetching] = useState(false);
  const [lastFetch, setLastFetch] = useState(null);

  const q = `?days=${days}${domain ? `&domain=${encodeURIComponent(domain)}` : ''}`;

  const { data: overview, loading: l1, reload: r1 } = useApi(`/api/stats/overview${q}`, [days, domain], 60000);
  const { data: timeline, loading: l2, reload: r2 } = useApi(`/api/stats/timeline${q}`, [days, domain]);
  const { data: byDomain, loading: l3, reload: r3 } = useApi(`/api/stats/by_domain${q}`, [days, domain]);
  const { data: sources,  loading: l4, reload: r4 } = useApi(`/api/stats/sources${q}`,  [days, domain]);
  const { data: geo,      loading: l5, reload: r5 } = useApi(`/api/stats/geo${q}`,      [days, domain]);
  const { data: alerts,   loading: l6, reload: r6 } = useApi(`/api/alerts${q}`,         [days, domain]);
  const { data: rejects,  loading: l7, reload: r7 } = useApi(`/api/rejects${q}`,        [days, domain]);
  const { data: fetchLog }                           = useApi('/api/fetch_log', [], 30000);

  const reloadAll = () => { r1(); r2(); r3(); r4(); r5(); r6(); r7(); };

  const handleFetchNow = async () => {
    setFetching(true);
    try {
      await triggerFetch();
      setLastFetch(new Date().toLocaleTimeString('it-IT'));
      setTimeout(reloadAll, 4000);
    } finally { setFetching(false); }
  };

  const lastLog = fetchLog?.[0];

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon">⛁</span>
            <span className="logo-text">DMARC<span className="logo-accent">Dashboard</span></span>
          </div>
          {lastLog && (
            <span className="last-fetch">
              Ultimo sync: {new Date(lastLog.fetched_at).toLocaleString('it-IT')}
              {lastLog.new_reports > 0 && <span className="badge-new">+{lastLog.new_reports}</span>}
            </span>
          )}
        </div>
        <div className="header-right">
          <div className="days-selector">
            {DAYS_OPTIONS.map((d) => (
              <button
                key={d}
                className={`day-btn ${days === d ? 'active' : ''}`}
                onClick={() => setDays(d)}
              >
                {d}g
              </button>
            ))}
          </div>
          <button className={`fetch-btn ${fetching ? 'loading' : ''}`} onClick={handleFetchNow} disabled={fetching}>
            {fetching ? 'Sync…' : '⟳ Sync IMAP'}
          </button>
          <UserMenu />
        </div>
      </header>

      <main className="main">
        {/* Overview cards */}
        <section className="section">
          {l1 ? <Spinner /> : <OverviewCards data={overview} />}
        </section>

        {/* Domain search bar */}
        <section className="section">
          <DomainSearch days={days} value={domain} onChange={setDomain} />
        </section>

        {/* Alerts */}
        <section className="section">
          {l6 ? <Spinner /> : <AlertsPanel data={alerts} />}
        </section>

        {/* Timeline */}
        <section className="section">
          {l2 ? <Spinner /> : <TimelineChart data={timeline} />}
        </section>

        {/* Domain chart + geo */}
        <section className="section two-col">
          <div>{l3 ? <Spinner /> : <DomainChart data={byDomain} />}</div>
          <div className="geo-wrap">{l5 ? <Spinner /> : <GeoMap data={geo} />}</div>
        </section>

        {/* Sources table */}
        <section className="section">
          {l4 ? <Spinner /> : <SourcesTable data={sources} />}
        </section>

        {lastFetch && <div className="toast">Sync avviato alle {lastFetch} — i dati si aggiorneranno tra pochi secondi.</div>}
      </main>
    </div>
  );
}
