import type { ReactNode } from 'react';

import { Btn, Frame, Placeholder, Row, Stack } from '../primitives';

export const ValidationCommon = ({ children, label }: { children: ReactNode; label: string }) => (
  <Frame name={label} dim="1280×800">
    <div style={{ height: 540, display: 'flex', flexDirection: 'column' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '8px 14px',
          borderBottom: '1px solid var(--lw-line-soft)',
          background: 'var(--lw-surface)',
        }}
      >
        <Row gap={8} style={{ fontSize: 12 }}>
          <span style={{ color: 'var(--lw-ink-4)' }}>Validation /</span>
          <span style={{ color: 'var(--lw-ink-4)' }}>Africa LC stratified 500 /</span>
          <b>Sample 47 / 500</b>
        </Row>
        <Row gap={6} style={{ marginLeft: 'auto' }}>
          <span
            style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 11, color: 'var(--lw-ink-4)' }}
          >
            ← prev · next →
          </span>
          <span style={{ width: 1, height: 18, background: 'var(--lw-line)' }} />
          <Btn>Save & next</Btn>
          <Btn kind="primary">Submit</Btn>
        </Row>
      </div>
      {children}
    </div>
  </Frame>
);

const CLASSIFY_OPTIONS: [string, string, string, boolean?][] = [
  ['1', 'Forest land', '#3a7d44', true],
  ['2', 'Cropland', '#d6a456'],
  ['3', 'Grassland', '#bcc972'],
  ['4', 'Wetlands', '#5b8aa8'],
  ['5', 'Settlements', '#9a3b3b'],
  ['6', 'Other', '#7c7c7c'],
];

export const ClassifyPanel = ({ compact = false }: { compact?: boolean }) => (
  <Stack gap={compact ? 6 : 8} style={{ padding: compact ? 10 : 12 }}>
    <div
      style={{
        fontFamily: 'var(--lw-font-mono)',
        fontSize: 10,
        color: 'var(--lw-ink-4)',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
      }}
    >
      Classify · sample #47
    </div>
    <div style={{ fontSize: compact ? 11 : 12, color: 'var(--lw-ink-3)' }}>
      Pick the dominant land cover within the buffer.
    </div>
    {CLASSIFY_OPTIONS.map(([num, label, color, selected]) => (
      <Row
        key={num}
        gap={8}
        style={{
          padding: '8px 10px',
          border: selected ? '1.5px solid var(--lw-accent)' : '1px solid var(--lw-line)',
          borderRadius: 4,
          background: selected ? 'var(--lw-accent-soft)' : 'var(--lw-surface)',
          cursor: 'default',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--lw-font-mono)',
            fontSize: 10,
            color: 'var(--lw-ink-4)',
            width: 12,
          }}
        >
          {num}
        </span>
        <span style={{ width: 14, height: 14, background: color, borderRadius: 2 }} />
        <span style={{ fontSize: 12, fontWeight: selected ? 600 : 500, flex: 1 }}>{label}</span>
        {selected && (
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 10,
              color: 'var(--lw-accent-ink)',
            }}
          >
            ✓
          </span>
        )}
      </Row>
    ))}
    <Stack gap={4} style={{ marginTop: 4 }}>
      <span style={{ fontSize: 11, fontWeight: 500 }}>Confidence</span>
      <Row gap={4}>
        {(['low', 'med', 'high'] as const).map((c, i) => (
          <span
            key={c}
            style={{
              flex: 1,
              padding: '4px 0',
              textAlign: 'center',
              fontSize: 11,
              border: '1px solid var(--lw-line)',
              borderRadius: 3,
              background: i === 2 ? 'var(--lw-ink-1)' : 'var(--lw-surface)',
              color: i === 2 ? 'white' : 'var(--lw-ink-3)',
            }}
          >
            {c}
          </span>
        ))}
      </Row>
    </Stack>
    {!compact && <Placeholder label="Notes (optional)" h={50} />}
  </Stack>
);

export const ActiveSample = ({ kind = 'point' }: { kind?: 'point' | 'polygon' }) => (
  <>
    <div
      style={{
        position: 'absolute',
        left: '50%',
        top: 0,
        bottom: 0,
        width: 1,
        background: 'rgba(14,17,22,0.18)',
        borderLeft: '1px dashed rgba(14,17,22,0.25)',
      }}
    />
    <div
      style={{
        position: 'absolute',
        top: '50%',
        left: 0,
        right: 0,
        height: 1,
        background: 'rgba(14,17,22,0.18)',
        borderTop: '1px dashed rgba(14,17,22,0.25)',
      }}
    />
    {kind === 'point' ? (
      <>
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: 140,
            height: 140,
            transform: 'translate(-50%,-50%)',
            border: '1.5px dashed var(--lw-accent)',
            borderRadius: '50%',
            background: 'oklch(0.62 0.12 200 / 0.06)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: 60,
            height: 60,
            transform: 'translate(-50%,-50%)',
            border: '1.5px solid var(--lw-accent)',
            borderRadius: '50%',
            background: 'oklch(0.62 0.12 200 / 0.10)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            width: 14,
            height: 14,
            borderRadius: '50%',
            background: 'var(--lw-accent)',
            border: '3px solid var(--lw-surface)',
            boxShadow: '0 0 0 1.5px var(--lw-accent), 0 2px 6px rgba(0,0,0,0.3)',
            transform: 'translate(-50%,-50%)',
          }}
        />
      </>
    ) : (
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <polygon
          points="42,38 60,36 64,52 56,62 44,60 38,48"
          fill="oklch(0.62 0.12 200 / 0.18)"
          stroke="var(--lw-accent)"
          strokeWidth="0.6"
          strokeDasharray="1.2 0.8"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    )}
    <div
      style={{
        position: 'absolute',
        left: '50%',
        top: '50%',
        transform: 'translate(14px, 14px)',
        fontFamily: 'var(--lw-font-mono)',
        fontSize: 10,
        color: 'var(--lw-accent-ink)',
        background: 'rgba(255,255,255,0.92)',
        padding: '2px 6px',
        borderRadius: 3,
        border: '1px solid var(--lw-accent)',
        whiteSpace: 'nowrap',
      }}
    >
      14.32°N, 38.21°E · 30m
    </div>
  </>
);
