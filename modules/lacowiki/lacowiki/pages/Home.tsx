import { useState } from 'react';

import '@simple-module-py/ui/lacowiki/styles.css';
import { DesignSystem } from '@simple-module-py/ui/lacowiki/design-system';
import { Overview } from '@simple-module-py/ui/lacowiki/overview';
import { Wireframes } from '@simple-module-py/ui/lacowiki/wireframes';

const TABS: [string, string][] = [
  ['overview', 'Overview'],
  ['system', 'Design system'],
  ['wireframes', 'Wireframes'],
];

function LacoWikiHome() {
  const [tab, setTab] = useState<string>('overview');

  return (
    <div className="lw-app" data-density="normal">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="brand-mark">
            <svg viewBox="0 0 22 22" width="22" height="22">
              <rect x="1" y="1" width="20" height="20" rx="4" fill="#0e1116" />
              <circle cx="11" cy="11" r="4" fill="none" stroke="white" strokeWidth="1.5" />
              <circle cx="11" cy="11" r="1.5" fill="white" />
            </svg>
          </div>
          LacoWiki{' '}
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 11,
              color: 'var(--lw-ink-4)',
              fontWeight: 400,
              marginLeft: 4,
            }}
          >
            / migration wireframes
          </span>
        </div>
        <div className="tabs">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className="tab"
              data-active={tab === id}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="topbar-meta">v0.1 · 8 modules · 23 frames</div>
      </header>

      <main>
        {tab === 'overview' && <Overview setTab={setTab} />}
        {tab === 'system' && <DesignSystem />}
        {tab === 'wireframes' && <Wireframes />}
      </main>
    </div>
  );
}

LacoWikiHome.layout = (page: React.ReactNode) => page;

export default LacoWikiHome;
