import React, { useState } from 'react';

function Badge({ value, type }) {
  const colors = {
    pass: { bg: 'rgba(52,211,153,0.15)', color: '#34d399' },
    fail: { bg: 'rgba(248,113,113,0.15)', color: '#f87171' },
    neutral: { bg: 'rgba(148,163,184,0.12)', color: '#94a3b8' },
    reject: { bg: 'rgba(248,113,113,0.15)', color: '#f87171' },
    quarantine: { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24' },
    none: { bg: 'rgba(96,165,250,0.15)', color: '#60a5fa' },
  };
  const style = colors[value] || colors.neutral;
  return (
    <span style={{
      ...style,
      padding: '2px 8px',
      borderRadius: 99,
      fontSize: 11,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
    }}>{value}</span>
  );
}

export default function SourcesTable({ data }) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState({ key: 'total', dir: -1 });

  const filtered = (data || [])
    .filter((r) =>
      !search ||
      r.source_ip?.includes(search) ||
      r.domains?.includes(search) ||
      r.geo_country?.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      const av = a[sort.key] ?? '';
      const bv = b[sort.key] ?? '';
      return sort.dir * (av < bv ? -1 : av > bv ? 1 : 0);
    });

  const toggleSort = (key) => {
    setSort((s) => ({ key, dir: s.key === key ? -s.dir : -1 }));
  };

  const Th = ({ k, label }) => (
    <th
      style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}
      onClick={() => toggleSort(k)}
    >
      {label} {sort.key === k ? (sort.dir === -1 ? '↓' : '↑') : ''}
    </th>
  );

  return (
    <div className="chart-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 className="chart-title" style={{ margin: 0 }}>IP Sorgenti</h3>
        <input
          className="search-input"
          placeholder="Filtra per IP, dominio, paese…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              <Th k="source_ip" label="IP" />
              <Th k="total" label="Messaggi" />
              <Th k="disposition" label="Disposizione" />
              <Th k="dkim_result" label="DKIM" />
              <Th k="spf_result" label="SPF" />
              <Th k="geo_country" label="Paese" />
              <Th k="domains" label="Dominio" />
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((r, i) => (
              <tr key={i}>
                <td><code style={{ fontSize: 12 }}>{r.source_ip}</code></td>
                <td>{r.total?.toLocaleString()}</td>
                <td><Badge value={r.disposition} /></td>
                <td><Badge value={r.dkim_result} /></td>
                <td><Badge value={r.spf_result} /></td>
                <td>{r.geo_country || '—'}</td>
                <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.domains || '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ textAlign: 'center', padding: 40, color: '#475569' }}>Nessun risultato</div>
        )}
      </div>
    </div>
  );
}
