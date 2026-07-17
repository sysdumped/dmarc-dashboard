import React, { useEffect, useRef } from 'react';

// Dynamic import of Leaflet to avoid SSR issues
let L = null;

function getColor(disposition) {
  if (disposition === 'reject') return '#f87171';
  if (disposition === 'quarantine') return '#fbbf24';
  return '#60a5fa';
}

export default function GeoMap({ data }) {
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    import('leaflet').then((leaflet) => {
      L = leaflet.default;

      if (!mapInstanceRef.current && mapRef.current) {
        const map = L.map(mapRef.current, {
          center: [30, 10],
          zoom: 2,
          zoomControl: true,
        });

        L.tileLayer(
          'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
          {
            attribution: '© OpenStreetMap © CARTO',
            subdomains: 'abcd',
            maxZoom: 19,
          }
        ).addTo(map);

        mapInstanceRef.current = map;
      }

      // Clear old markers
      mapInstanceRef.current.eachLayer((layer) => {
        if (layer instanceof L.CircleMarker) {
          mapInstanceRef.current.removeLayer(layer);
        }
      });

      // Group by lat/lon
      const grouped = {};
      (data || []).forEach((point) => {
        if (!point.geo_lat || !point.geo_lon) return;
        const key = `${point.geo_lat},${point.geo_lon}`;
        if (!grouped[key]) {
          grouped[key] = { lat: point.geo_lat, lon: point.geo_lon, country: point.geo_country, items: [] };
        }
        grouped[key].items.push(point);
      });

      Object.values(grouped).forEach((g) => {
        const totalMessages = g.items.reduce((s, i) => s + (i.total || 0), 0);
        const hasReject = g.items.some((i) => i.disposition === 'reject');
        const hasQuarantine = g.items.some((i) => i.disposition === 'quarantine');
        const color = hasReject ? '#f87171' : hasQuarantine ? '#fbbf24' : '#60a5fa';
        const radius = Math.min(4 + Math.log1p(totalMessages) * 3, 30);

        const rows = g.items
          .map((i) => `<tr><td>${i.disposition}</td><td>${i.total}</td></tr>`)
          .join('');

        const popup = `
          <div style="font-family:monospace;font-size:12px;color:#e2e8f0">
            <b>${g.country || 'Unknown'}</b><br/>
            <b>${g.lat}, ${g.lon}</b><br/>
            <table style="margin-top:4px;border-collapse:collapse">
              <tr><th style="padding-right:8px">Disposizione</th><th>Messaggi</th></tr>
              ${rows}
            </table>
          </div>
        `;

        L.circleMarker([g.lat, g.lon], {
          radius,
          color,
          fillColor: color,
          fillOpacity: 0.6,
          weight: 1.5,
        })
          .bindPopup(popup, { className: 'dark-popup' })
          .addTo(mapInstanceRef.current);
      });
    });

    return () => {};
  }, [data]);

  return (
    <div className="chart-card" style={{ padding: 0 }}>
      <div style={{ position: 'relative' }}>
        <h3 className="chart-title" style={{ position: 'absolute', top: 16, left: 20, zIndex: 999, margin: 0 }}>
          Mappa geografica sorgenti
        </h3>
        <div ref={mapRef} style={{ height: 420, borderRadius: 12, overflow: 'hidden' }} />
        <div style={{ position: 'absolute', bottom: 12, right: 12, zIndex: 999, display: 'flex', gap: 12, background: 'rgba(15,23,42,0.8)', padding: '6px 12px', borderRadius: 8 }}>
          {[['#60a5fa', 'Consegnati'], ['#fbbf24', 'Quarantena'], ['#f87171', 'Rifiutati']].map(([c, l]) => (
            <span key={l} style={{ fontSize: 11, color: '#cbd5e1', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: c, display: 'inline-block' }} />
              {l}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
