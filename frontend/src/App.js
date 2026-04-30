import React, { useState } from 'react';
import { useApi, triggerFetch } from './hooks/useApi';
import OverviewCards from './components/OverviewCards';
import TimelineChart from './components/TimelineChart';
import DomainChart from './components/DomainChart';
import GeoMap from './components/GeoMap';
import SourcesTable from './components/SourcesTable';
import AlertsPanel from './components/AlertsPanel';
import './App.css';

const DAYS_OPTIONS = [7, 14, 30, 90];

function Spinner() {
  return <div className="spinner" />;
}

export default function App() {
  const [days, setDays] = useState(30);
  const [fetching, setFetching] = useState(false);
  const [lastFetch, setLastFetch] = useState(null);

  const q = `?days=${days}`;
  const { data: overview, loading: l1, reload: r1 } = useApi(`/api/stats/overview${q}`, [days], 60000);
  const { data: timeline, loading: l2, reload: r2 } = useApi(`/api/stats/timeline${q}`, [days]);
  const { data: byDomain, loading: l3, reload: r3 } = useApi(`/api/stats/by_domain${q}`, [days]);
  const { data: sources, loading: l4, reload: r4 } = useApi(`/api/stats/sources${q}`, [days]);
  const { data: geo, loading: l5, reload: r5 } = useApi(`/api/stats/geo${q}`, [days]);
  const { data: alerts, loading: l6, reload: r6 } = useApi(`/api/alerts${q}`, [days]);
  const { data: fetchLog } = useApi('/api/fetch_log', [], 30000);

  const reloadAll = () => { r1(); r2(); r3(); r4(); r5(); r6(); };

  const handleFetchNow = async () => {
    setFetching(true);
    try {
      await triggerFetch();
      setLastFetch(new Date().toLocaleTimeString('it-IT'));
      setTimeout(reloadAll, 4000);
    } finally {
      setFetching(false);
    }
  };

  const lastLog = fetchLog?.[0];

  return (
    <div className="app">
      {/* Header */}
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
          <button
            className={`fetch-btn ${fetching ? 'loading' : ''}`}
            onClick={handleFetchNow}
            disabled={fetching}
          >
            {fetching ? 'Sync…' : '⟳ Sync IMAP'}
          </button>
        </div>
      </header>

      <main className="main">
        {/* Overview */}
        <section className="section">
          {l1 ? <Spinner /> : <OverviewCards data={overview} />}
        </section>

        {/* Alerts */}
        <section className="section">
          {l6 ? <Spinner /> : <AlertsPanel data={alerts} />}
        </section>

        {/* Timeline */}
        <section className="section">
          {l2 ? <Spinner /> : <TimelineChart data={timeline} />}
        </section>

        {/* Domain chart + geo side by side on large screens */}
        <section className="section two-col">
          <div>{l3 ? <Spinner /> : <DomainChart data={byDomain} />}</div>
          <div className="geo-wrap">{l5 ? <Spinner /> : <GeoMap data={geo} />}</div>
        </section>

        {/* Sources table */}
        <section className="section">
          {l4 ? <Spinner /> : <SourcesTable data={sources} />}
        </section>

        {lastFetch && (
          <div className="toast">Sync avviato alle {lastFetch} — i dati si aggiorneranno tra pochi secondi.</div>
        )}
      </main>
    </div>
  );
}
