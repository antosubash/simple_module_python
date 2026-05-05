import { MapPh, Pill, Row, Stack } from '../primitives';

const IMAGERY: [string, boolean][] = [
  ['Sentinel-2', true],
  ['Bing aerial', true],
  ['PlanetScope', false],
  ['Sentinel-1', false],
  ['Google Earth', true],
];

const MODES: [string, string, boolean?][] = [
  ['single', 'Single rater', true],
  ['consensus', 'Consensus (k≥2)'],
  ['expert', 'Expert review'],
];

const CONFIDENCES: [string, string, boolean?][] = [
  ['off', 'Off'],
  ['3', '3-step', true],
  ['5', '5-step'],
];

const REVIEWERS: [string, string, number][] = [
  ['m.lesiv@iiasa', 'owner', 125],
  ['d.fritz@iiasa', 'reviewer', 125],
  ['a.subash@iiasa', 'reviewer', 125],
  ['+ invite reviewer', '', 125],
];

const SUMMARY: [string, string][] = [
  ['samples', '500'],
  ['reviewers', '3'],
  ['per reviewer', '≈ 167'],
  ['mode', 'single rater'],
  ['buffer', '30 m'],
  ['est. time', '≈ 6 h'],
];

const cardCss = {
  border: '1px solid var(--lw-line)',
  borderRadius: 6,
  background: 'var(--lw-surface)',
  padding: 14,
} as const;

const fieldCss = {
  height: 32,
  border: '1px solid var(--lw-line)',
  borderRadius: 4,
  padding: '0 10px',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
} as const;

const compactFieldCss = {
  height: 28,
  border: '1px solid var(--lw-line)',
  borderRadius: 4,
  padding: '0 10px',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
} as const;

export const SourceCard = () => (
  <div style={cardCss}>
    <b style={{ fontSize: 13 }}>1 · Source</b>
    <Stack gap={10} style={{ marginTop: 10 }}>
      <Stack gap={4}>
        <span style={{ fontSize: 11, fontWeight: 500 }}>Sampling design</span>
        <div style={fieldCss}>
          Africa LC stratified 500
          <span style={{ color: 'var(--lw-ink-4)' }}>▾</span>
        </div>
      </Stack>
      <Stack gap={4}>
        <span style={{ fontSize: 11, fontWeight: 500 }}>Legend (classification options)</span>
        <div style={fieldCss}>
          IPCC LULUCF (6)
          <span style={{ color: 'var(--lw-ink-4)' }}>▾</span>
        </div>
      </Stack>
      <Stack gap={4}>
        <span style={{ fontSize: 11, fontWeight: 500 }}>Reference imagery layers</span>
        <Row gap={6} style={{ flexWrap: 'wrap' }}>
          {IMAGERY.map(([n, on]) => (
            <span
              key={n}
              style={{
                padding: '5px 10px',
                border: on ? '1.5px solid var(--lw-accent)' : '1px solid var(--lw-line)',
                background: on ? 'var(--lw-accent-soft)' : 'var(--lw-surface)',
                borderRadius: 4,
                fontSize: 11,
                fontWeight: on ? 600 : 500,
                color: on ? 'var(--lw-accent-ink)' : 'var(--lw-ink-3)',
              }}
            >
              {on ? '✓ ' : ''}
              {n}
            </span>
          ))}
        </Row>
      </Stack>
    </Stack>
  </div>
);

export const WorkflowCard = () => (
  <div style={cardCss}>
    <b style={{ fontSize: 13 }}>2 · Workflow</b>
    <Stack gap={10} style={{ marginTop: 10 }}>
      <Stack gap={4}>
        <span style={{ fontSize: 11, fontWeight: 500 }}>Mode</span>
        <Row gap={6}>
          {MODES.map(([k, l, on]) => (
            <span
              key={k}
              style={{
                flex: 1,
                padding: '8px 10px',
                border: on ? '1.5px solid var(--lw-accent)' : '1px solid var(--lw-line)',
                background: on ? 'var(--lw-accent-soft)' : 'var(--lw-surface)',
                borderRadius: 4,
                fontSize: 12,
                fontWeight: on ? 600 : 500,
                textAlign: 'center',
                color: on ? 'var(--lw-accent-ink)' : 'var(--lw-ink-2)',
              }}
            >
              {l}
            </span>
          ))}
        </Row>
      </Stack>
      <Row gap={12}>
        <Stack gap={4} style={{ flex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 500 }}>Buffer radius</span>
          <div style={{ ...compactFieldCss, fontFamily: 'var(--lw-font-mono)' }}>30 m</div>
        </Stack>
        <Stack gap={4} style={{ flex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 500 }}>Sample order</span>
          <div style={{ ...compactFieldCss, justifyContent: 'space-between' }}>random ▾</div>
        </Stack>
        <Stack gap={4} style={{ flex: 1 }}>
          <span style={{ fontSize: 11, fontWeight: 500 }}>Allow skip</span>
          <div style={compactFieldCss}>✓ with reason</div>
        </Stack>
      </Row>
      <Stack gap={4}>
        <span style={{ fontSize: 11, fontWeight: 500 }}>Confidence capture</span>
        <Row gap={6}>
          {CONFIDENCES.map(([k, l, on]) => (
            <span
              key={k}
              style={{
                padding: '5px 12px',
                border: on ? '1.5px solid var(--lw-accent)' : '1px solid var(--lw-line)',
                background: on ? 'var(--lw-accent-soft)' : 'var(--lw-surface)',
                borderRadius: 4,
                fontSize: 11,
                fontWeight: on ? 600 : 500,
                color: on ? 'var(--lw-accent-ink)' : 'var(--lw-ink-3)',
              }}
            >
              {l}
            </span>
          ))}
        </Row>
      </Stack>
    </Stack>
  </div>
);

export const ReviewersCard = () => (
  <div style={cardCss}>
    <b style={{ fontSize: 13 }}>3 · Reviewers</b>
    <Stack gap={8} style={{ marginTop: 10 }}>
      {REVIEWERS.map(([who, role, n], i) => (
        <Row
          key={who}
          gap={8}
          style={{ padding: '6px 0', borderBottom: i < 3 ? '1px solid var(--lw-line-soft)' : 0 }}
        >
          <div
            style={{
              width: 22,
              height: 22,
              borderRadius: '50%',
              background: i < 3 ? 'var(--lw-bg-sunk)' : 'transparent',
              border: '1px solid var(--lw-line)',
            }}
          />
          <span
            style={{
              fontSize: 12,
              flex: 1,
              color: i === 3 ? 'var(--lw-accent-ink)' : 'var(--lw-ink-1)',
            }}
          >
            {who}
          </span>
          {role && <Pill>{role}</Pill>}
          {role && (
            <span
              style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}
            >
              {n} samples
            </span>
          )}
        </Row>
      ))}
    </Stack>
  </div>
);

export const SummarySidebar = () => (
  <Stack gap={12}>
    <div style={cardCss}>
      <span
        style={{
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 10,
          color: 'var(--lw-ink-4)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}
      >
        Summary
      </span>
      <Stack gap={6} style={{ marginTop: 8, fontFamily: 'var(--lw-font-mono)', fontSize: 11 }}>
        {SUMMARY.map(([k, v]) => (
          <Row key={k} justify="space-between">
            <span style={{ color: 'var(--lw-ink-4)' }}>{k}</span>
            <b>{v}</b>
          </Row>
        ))}
      </Stack>
    </div>
    <div
      style={{
        flex: 1,
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <MapPh h={200}>
        {Array.from({ length: 50 }).map((_, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${10 + ((i * 31) % 80)}%`,
              top: `${10 + ((i * 47) % 80)}%`,
              width: 5,
              height: 5,
              borderRadius: '50%',
              background: 'var(--lw-accent)',
              border: '1px solid white',
              transform: 'translate(-50%,-50%)',
            }}
          />
        ))}
      </MapPh>
      <div
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          background: 'var(--lw-surface)',
          border: '1px solid var(--lw-line)',
          borderRadius: 4,
          padding: '3px 8px',
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 10,
        }}
      >
        500 samples
      </div>
    </div>
  </Stack>
);
