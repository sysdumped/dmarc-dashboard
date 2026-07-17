import React, { useState, useEffect } from 'react';

export default function UserMenu() {
  const [auth, setAuth] = useState(null);

  useEffect(() => {
    fetch('/api/auth/me')
      .then((r) => r.json())
      .then(setAuth)
      .catch(() => setAuth(null));
  }, []);

  // OIDC disabled or still loading
  if (!auth || !auth.oidc_enabled) return null;

  const user = auth.user;

  return (
    <div className="user-menu">
      <span className="user-name">
        <span className="user-icon">◉</span>
        {user?.name || user?.email || 'Utente'}
      </span>
      <a href="/auth/logout" className="logout-btn" title="Esci">
        ⎋ Logout
      </a>
    </div>
  );
}
