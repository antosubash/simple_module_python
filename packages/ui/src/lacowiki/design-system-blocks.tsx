import type { ReactNode } from 'react';

import { Pill } from './primitives';

export { SpatialLegend, SpatialMap } from './spatial-preview';

export const Swatch = ({
  name,
  token,
  value,
  css,
}: {
  name: string;
  token: string;
  value: string;
  css: string;
}) => (
  <div className="swatch">
    <div className="chip" style={{ background: css }} />
    <div className="meta">
      <b>{name}</b>
      {token}
      <br />
      {value}
    </div>
  </div>
);

export const NEUTRALS: [string, string, string][] = [
  ['bg', '--bg', '#fafbfc'],
  ['bg-alt', '--bg-alt', '#f3f5f7'],
  ['surface', '--surface', '#ffffff'],
  ['line', '--line', '#dfe3e8'],
  ['ink-3', '--ink-3', '#6b7480'],
  ['ink-1', '--ink-1', '#0e1116'],
];

export const ACCENTS: [string, string, string][] = [
  ['accent', '--accent', 'oklch(.62 .12 200)'],
  ['accent-soft', '--accent-soft', 'oklch(.94 .04 200)'],
  ['accent-ink', '--accent-ink', 'oklch(.34 .08 200)'],
  ['ok', '--ok', 'oklch(.62 .12 155)'],
  ['warn', '--warn', 'oklch(.72 .13 75)'],
  ['err', '--err', 'oklch(.58 .16 25)'],
];

export const MODULES: [string, string][] = [
  ['Datasets', 'datasets'],
  ['Legends', 'legends'],
  ['Sampling', 'sampling'],
  ['Validation', 'validation'],
  ['Reports', 'reports'],
  ['Notifications', 'notif'],
];

export const TYPE_SPECS: [string, ReactNode][] = [
  [
    'Display · 44/1.05 · -0.02em',
    <span style={{ fontSize: 44, lineHeight: 1.05, letterSpacing: '-0.02em', fontWeight: 600 }}>
      Map. Sample. Validate.
    </span>,
  ],
  [
    'H1 · 28/1.15 · -0.01em',
    <span style={{ fontSize: 28, lineHeight: 1.15, letterSpacing: '-0.01em', fontWeight: 600 }}>
      Land cover datasets
    </span>,
  ],
  ['H2 · 20/1.25', <span style={{ fontSize: 20, fontWeight: 600 }}>Sampling design</span>],
  [
    'Body · 14/1.5',
    <span style={{ fontSize: 14 }}>
      Stratified random sampling allocates points proportionally across legend classes.
    </span>,
  ],
  [
    'Small · 12/1.4 · ink-3',
    <span style={{ fontSize: 12, color: 'var(--lw-ink-3)' }}>
      Last updated 2 hours ago by m.lesiv@iiasa.ac.at
    </span>,
  ],
  [
    'Mono · 12 · uppercase',
    <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 12, letterSpacing: '0.06em' }}>
      EPSG:4326 · 14,328 PIXELS · COG
    </span>,
  ],
  [
    'Hand · annotation',
    <span
      style={{ fontFamily: 'var(--lw-font-hand)', fontSize: 22, color: 'var(--lw-accent-ink)' }}
    >
      ← classify here
    </span>,
  ],
];

export const SPACING: [string, number][] = [
  ['s-1', 4],
  ['s-2', 8],
  ['s-3', 12],
  ['s-4', 16],
  ['s-5', 24],
  ['s-6', 32],
  ['s-7', 48],
  ['s-8', 64],
];

export const SampleCard = () => (
  <div
    style={{
      background: 'var(--lw-surface)',
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      padding: 16,
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <span className="mod-dot mod-datasets" />
      <span style={{ fontSize: 11, fontFamily: 'var(--lw-font-mono)', color: 'var(--lw-ink-4)' }}>
        DATASET · COG
      </span>
      <Pill tone="ok">ready</Pill>
    </div>
    <div style={{ fontSize: 16, fontWeight: 600 }}>Africa LC 2020 v3</div>
    <div style={{ fontSize: 13, color: 'var(--lw-ink-3)', marginTop: 4 }}>
      Sentinel-2 derived classification, 10m resolution
    </div>
    <div
      style={{
        display: 'flex',
        gap: 16,
        marginTop: 12,
        fontSize: 11,
        fontFamily: 'var(--lw-font-mono)',
        color: 'var(--lw-ink-4)',
      }}
    >
      <span>4.2 GB</span>
      <span>EPSG:4326</span>
      <span>shared · 3</span>
    </div>
  </div>
);

export const SampleTable = () => (
  <div
    style={{
      background: 'var(--lw-surface)',
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      overflow: 'hidden',
    }}
  >
    {(
      [
        ['Africa LC 2020', 'ready', '4.2 GB'],
        ['Tropical Forest 2024', 'processing', '1.8 GB'],
        ['Urban Extents EU', 'ready', '850 MB'],
      ] as [string, 'ready' | 'processing', string][]
    ).map((r, i) => (
      <div
        key={r[0]}
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 80px 80px',
          padding: '10px 14px',
          fontSize: 12,
          borderBottom: i < 2 ? '1px solid var(--lw-line-soft)' : 0,
          alignItems: 'center',
        }}
      >
        <span style={{ fontWeight: 500 }}>{r[0]}</span>
        <Pill tone={r[1] === 'ready' ? 'ok' : 'warn'}>{r[1]}</Pill>
        <span
          style={{
            fontFamily: 'var(--lw-font-mono)',
            color: 'var(--lw-ink-4)',
            textAlign: 'right',
          }}
        >
          {r[2]}
        </span>
      </div>
    ))}
  </div>
);
