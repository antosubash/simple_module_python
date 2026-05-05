import { Row, Stack } from './primitives';

const MODS: [string, string, string][] = [
  ['datasets', 'Datasets', '8 tables · COG/PMTiles · sharing'],
  ['legends', 'Legends', '4 tables · 10 templates · CRUD'],
  ['sampling', 'Sampling', '4 tables · 7 strategies · jobs'],
  ['validation', 'Validation', '6 tables · classify page'],
  ['reports', 'Reports', '4 tables · matrix · sharing'],
  ['notif', 'Notifications', '3 tables · 6 events · in-app feed'],
];

export const Overview = ({ setTab }: { setTab: (t: string) => void }) => (
  <div>
    <div className="eyebrow">LacoWiki · Python rewrite</div>
    <h1 className="h-display">
      Wireframes & design system
      <br />
      for the v2 migration.
    </h1>
    <p className="lede">
      A starting point for the new LacoWiki: an opinionated design system in the modern
      scientific/technical mold, plus mid-fidelity wireframes covering all eight modules from the
      rewrite spec — datasets, legends, sampling, validation, reports, and account.
    </p>

    <div className="overview-grid">
      <a className="idx-card" onClick={() => setTab('system')}>
        <span className="num">→ 01 · system</span>
        <h3>Design system</h3>
        <p>
          Color, type, spacing, components, and the spatial UI primitives that carry most of the
          product weight.
        </p>
      </a>
      <a className="idx-card" onClick={() => setTab('wireframes')}>
        <span className="num">→ 02 · screens</span>
        <h3>Wireframes</h3>
        <p>
          15 frames across landing, dashboard, datasets, legends, sampling, validation, reports,
          settings.
        </p>
      </a>
      <a className="idx-card" onClick={() => setTab('wireframes')}>
        <span className="num">→ 03 · core</span>
        <h3>Validation, focused</h3>
        <p>
          One sample at a time — buffer, crosshair guides, single classify panel beside the map.
        </p>
      </a>
    </div>

    <div style={{ marginTop: 64, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32 }}>
      <div>
        <div className="eyebrow">Design direction</div>
        <h3 className="h-section">Restrained chrome, data-forward</h3>
        <p style={{ fontSize: 14, color: 'var(--lw-ink-2)' }}>
          Cool neutrals, one teal-cyan accent, Inter for UI and JetBrains Mono for data. Map and
          validation imagery carry the visual weight; the chrome stays out of the way. Inspired by
          the working language of Linear, Mapbox, Earth Engine — not a re-skin of any one of them.
        </p>
        <ul style={{ fontSize: 13, color: 'var(--lw-ink-3)', paddingLeft: 18, lineHeight: 1.7 }}>
          <li>1px lines, no shadows on chrome</li>
          <li>Status uses small mono pills, never icon-only</li>
          <li>Map controls float on the map; never wrap it</li>
          <li>Tabular numerals everywhere they appear in tables</li>
        </ul>
      </div>
      <div>
        <div className="eyebrow">Migration scope</div>
        <h3 className="h-section">Eight modules, one shell</h3>
        <Stack gap={8}>
          {MODS.map((r) => (
            <Row
              key={r[0]}
              gap={12}
              style={{ padding: '8px 0', borderBottom: '1px solid var(--lw-line-soft)' }}
            >
              <span className={`mod-dot mod-${r[0]}`} style={{ width: 10, height: 10 }} />
              <b style={{ fontSize: 13, width: 110 }}>{r[1]}</b>
              <span
                style={{
                  fontFamily: 'var(--lw-font-mono)',
                  fontSize: 11,
                  color: 'var(--lw-ink-4)',
                  flex: 1,
                }}
              >
                {r[2]}
              </span>
            </Row>
          ))}
        </Stack>
      </div>
    </div>
  </div>
);
