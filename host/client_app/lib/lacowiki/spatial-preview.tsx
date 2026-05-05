import { MapPh, Row } from './primitives';

const LEGEND_CLASSES: [string, string][] = [
  ['Forest land', '#3a7d44'],
  ['Cropland', '#d6a456'],
  ['Grassland', '#bcc972'],
  ['Wetlands', '#5b8aa8'],
  ['Settlements', '#9a3b3b'],
  ['Other', '#7c7c7c'],
];

const SAMPLE_POINTS: [number, number][] = [
  [35, 45],
  [55, 60],
  [70, 35],
  [25, 65],
  [80, 70],
];

export const SpatialMap = () => (
  <div
    style={{
      position: 'relative',
      borderRadius: 6,
      overflow: 'hidden',
      border: '1px solid var(--lw-line)',
    }}
  >
    <MapPh h={260} />
    <div
      style={{
        position: 'absolute',
        top: 10,
        left: 10,
        background: 'var(--lw-surface)',
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        padding: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        fontSize: 11,
        minWidth: 140,
      }}
    >
      <Row>
        <span style={{ width: 10, height: 10, background: 'var(--lw-accent)', borderRadius: 2 }} />
        Land cover
      </Row>
      <Row>
        <span style={{ width: 10, height: 10, background: 'var(--lw-ink-5)', borderRadius: 2 }} />
        Sentinel-2 RGB
      </Row>
      <Row>
        <span
          style={{
            width: 10,
            height: 10,
            background: 'var(--lw-bg-sunk)',
            borderRadius: 2,
            border: '1px dashed var(--lw-ink-5)',
          }}
        />
        Bing aerial
      </Row>
    </div>
    <div
      style={{
        position: 'absolute',
        top: 10,
        right: 10,
        background: 'var(--lw-surface)',
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          width: 28,
          height: 28,
          display: 'grid',
          placeItems: 'center',
          borderBottom: '1px solid var(--lw-line-soft)',
          fontWeight: 600,
        }}
      >
        +
      </div>
      <div
        style={{ width: 28, height: 28, display: 'grid', placeItems: 'center', fontWeight: 600 }}
      >
        −
      </div>
    </div>
    {SAMPLE_POINTS.map(([x, y], i) => (
      <div
        key={i}
        style={{
          position: 'absolute',
          left: `${x}%`,
          top: `${y}%`,
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: i === 1 ? 'var(--lw-accent)' : i === 4 ? 'var(--lw-ok)' : 'var(--lw-surface)',
          border: i === 1 ? '2px solid var(--lw-surface)' : '1.5px solid var(--lw-ink-1)',
          boxShadow: i === 1 ? '0 0 0 4px oklch(.62 .12 200 / .25)' : 'none',
          transform: 'translate(-50%, -50%)',
        }}
      />
    ))}
    <div
      style={{
        position: 'absolute',
        bottom: 10,
        left: 10,
        background: 'rgba(255,255,255,0.85)',
        padding: '4px 8px',
        fontFamily: 'var(--lw-font-mono)',
        fontSize: 10,
        borderRadius: 3,
        border: '1px solid var(--lw-line)',
      }}
    >
      500 m ━━━━
    </div>
  </div>
);

export const SpatialLegend = () => (
  <div
    style={{
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      background: 'var(--lw-surface)',
      overflow: 'hidden',
    }}
  >
    <div
      style={{
        padding: '8px 12px',
        borderBottom: '1px solid var(--lw-line-soft)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600 }}>IPCC LULUCF (6)</span>
      <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}>
        v1.2
      </span>
    </div>
    {LEGEND_CLASSES.map(([n, c], i) => (
      <div
        key={n}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 12px',
          fontSize: 12,
          borderBottom: i < 5 ? '1px solid var(--lw-line-soft)' : 0,
        }}
      >
        <span style={{ width: 14, height: 14, background: c, borderRadius: 2 }} />
        <span style={{ flex: 1 }}>{n}</span>
        <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}>
          {i + 1}
        </span>
      </div>
    ))}
  </div>
);
