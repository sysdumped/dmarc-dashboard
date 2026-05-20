import React from 'react';

function pct(num, den) {
  if (!den) return 0;
  return Math.round((num / den) * 100);
}

export default function OverviewCards({ data }) {
  if (!data) return null;
  const { total_messages, report_count, dkim_pass, spf_pass, disposition } = data;
  const rejected    = disposition?.reject     || 0;
  const quarantined = disposition?.quarantine || 0;
  const delivered   = disposition?.none       || 0;

  const cards = [
    { label: 'Messaggi totali', value: total_messages?.toLocaleString() ?? '—', sub: `da ${report_count} report`, accent: '#60a5fa', icon: '✉' },
    { label: 'DKIM Pass',  value: `${pct(dkim_pass, total_messages)}%`,  sub: `${dkim_pass?.toLocaleString()} messaggi`, accent: '#34d399', icon: '🔑' },
    { label: 'SPF Pass',   value: `${pct(spf_pass,  total_messages)}%`,  sub: `${spf_pass?.toLocaleString()} messaggi`,  accent: '#a78bfa', icon: '🛡' },
    { label: 'Consegnati', value: delivered?.toLocaleString()   ?? '0',  sub: `${pct(delivered,   total_messages)}% del totale`, accent: '#34d399', icon: '✓' },
    { label: 'Quarantena', value: quarantined?.toLocaleString() ?? '0',  sub: `${pct(quarantined, total_messages)}% del totale`, accent: '#fbbf24', icon: '⚠' },
    { label: 'Rifiutati',  value: rejected?.toLocaleString()    ?? '0',  sub: `${pct(rejected,    total_messages)}% del totale`, accent: '#f87171', icon: '✕' },
  ];

  return (
    <div className="cards-grid">
      {cards.map((c) => (
        <div key={c.label} className="card" style={{ '--accent': c.accent }}>
          <div className="card-icon">{c.icon}</div>
          <div className="card-body">
            <div className="card-value">{c.value}</div>
            <div className="card-label">{c.label}</div>
            <div className="card-sub">{c.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
