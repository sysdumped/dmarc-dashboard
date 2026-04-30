import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { format, parseISO } from 'date-fns';
import { it } from 'date-fns/locale';

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tooltip-title">
        {label ? format(parseISO(label), 'd MMM yyyy', { locale: it }) : ''}
      </div>
      {payload.map((p) => (
        <div key={p.dataKey} className="tooltip-row">
          <span style={{ color: p.color }}>■</span> {p.name}: <b>{p.value}</b>
        </div>
      ))}
    </div>
  );
};

export default function TimelineChart({ data }) {
  const formatted = (data || []).map((d) => ({
    ...d,
    label: d.date,
  }));

  return (
    <div className="chart-card">
      <h3 className="chart-title">Timeline per disposizione</h3>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={formatted} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="gNone" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gQ" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="gR" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#f87171" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => {
              try { return format(parseISO(v), 'd/M'); } catch { return v; }
            }}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: '#94a3b8', paddingTop: 8 }}
            formatter={(v) => ({ none: 'Consegnati', quarantine: 'Quarantena', reject: 'Rifiutati' }[v] || v)}
          />
          <Area type="monotone" dataKey="none" name="none" stroke="#60a5fa" fill="url(#gNone)" strokeWidth={2} />
          <Area type="monotone" dataKey="quarantine" name="quarantine" stroke="#fbbf24" fill="url(#gQ)" strokeWidth={2} />
          <Area type="monotone" dataKey="reject" name="reject" stroke="#f87171" fill="url(#gR)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
