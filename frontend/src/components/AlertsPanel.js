import React from 'react';
export default function AlertsPanel({data}){
  if(!data)return null;
  const{failing_deliveries,unenforced_policies}=data;
  const hasAlerts=failing_deliveries?.length>0||unenforced_policies?.length>0;
  return(<div className="chart-card">
    <h3 className="chart-title">Alert policy DMARC</h3>
    {!hasAlerts&&<div className="alert-ok"><span style={{fontSize:24}}>✓</span><span>Nessun alert — tutte le policy risultano configurate e rispettate.</span></div>}
    {unenforced_policies?.length>0&&<div className="alert-section"><div className="alert-header warn">⚠ Policy non enforced (p=none)</div><div className="alert-list">{unenforced_policies.map((d,i)=><div key={i} className="alert-item"><code>{d.domain}</code><span className="alert-badge warn">p=none</span><span style={{color:'#94a3b8',fontSize:12}}>— considera di alzare a quarantine o reject</span></div>)}</div></div>}
    {failing_deliveries?.length>0&&<div className="alert-section"><div className="alert-header danger">✕ Messaggi rifiutati/quarantena</div><div className="alert-list">{failing_deliveries.map((d,i)=><div key={i} className="alert-item"><code>{d.domain}</code><span className={`alert-badge ${d.disposition==='reject'?'danger':'warn'}`}>{d.disposition}</span><span style={{color:'#94a3b8',fontSize:12}}>— {d.n?.toLocaleString()} messaggi</span></div>)}</div></div>}
  </div>);
}
