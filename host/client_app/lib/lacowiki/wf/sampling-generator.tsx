import { Chrome } from '../chrome';
import { Btn, Frame, MapPh, Row, Stack } from '../primitives';

const STRATEGIES = [
  'Simple random',
  'Stratified random',
  'Systematic grid',
  'Cluster',
  'Two-stage',
  'Equal allocation',
  'Proportional allocation',
];

const ALLOCATIONS: [string, string, number, number][] = [
  ['Forest land', '#3a7d44', 180, 36],
  ['Cropland', '#d6a456', 120, 24],
  ['Grassland', '#bcc972', 90, 18],
  ['Wetlands', '#5b8aa8', 50, 10],
  ['Settlements', '#9a3b3b', 40, 8],
  ['Other', '#7c7c7c', 20, 4],
];

const DOT_COLORS = ['#3a7d44', '#d6a456', '#bcc972', '#5b8aa8', '#9a3b3b', '#7c7c7c'];

const FieldRow = ({
  label,
  value,
  mono,
  caret,
}: {
  label: string;
  value: string;
  mono?: boolean;
  caret?: boolean;
}) => (
  <Stack gap={4}>
    <span style={{ fontSize: 11, fontWeight: 500 }}>{label}</span>
    <div
      style={{
        height: 30,
        border: '1px solid var(--lw-line)',
        borderRadius: 4,
        padding: '0 10px',
        fontFamily: mono ? 'var(--lw-font-mono)' : undefined,
        fontSize: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}
    >
      {value}
      {caret ? <span style={{ color: 'var(--lw-ink-4)' }}>▾</span> : null}
    </div>
  </Stack>
);

const StrategyList = () => (
  <div
    style={{
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      background: 'var(--lw-surface)',
      padding: 14,
    }}
  >
    <b style={{ fontSize: 13 }}>1 · Strategy</b>
    <Stack gap={6} style={{ marginTop: 10 }}>
      {STRATEGIES.map((s, i) => (
        <Row
          key={s}
          gap={8}
          style={{
            padding: '6px 8px',
            borderRadius: 4,
            background: i === 1 ? 'var(--lw-accent-soft)' : 'transparent',
            fontSize: 12,
            fontWeight: i === 1 ? 600 : 500,
          }}
        >
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              border: `1.5px solid ${i === 1 ? 'var(--lw-accent)' : 'var(--lw-ink-5)'}`,
              background: i === 1 ? 'var(--lw-accent)' : 'transparent',
            }}
          />
          {s}
        </Row>
      ))}
    </Stack>
  </div>
);

const ParametersBox = () => (
  <div
    style={{
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      background: 'var(--lw-surface)',
      padding: 14,
    }}
  >
    <b style={{ fontSize: 13 }}>2 · Parameters</b>
    <Stack gap={10} style={{ marginTop: 10 }}>
      <FieldRow label="Total points (n)" value="500" mono />
      <FieldRow label="Dataset" value="Africa LC 2020 v3" caret />
      <FieldRow label="Legend" value="IPCC LULUCF (6)" caret />
      <FieldRow label="Random seed" value="4831" mono />
    </Stack>
  </div>
);

const AllocationBox = () => (
  <div
    style={{
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      background: 'var(--lw-surface)',
      padding: 14,
    }}
  >
    <Row justify="space-between">
      <b style={{ fontSize: 13 }}>3 · Allocation per class</b>
      <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}>
        Σ = 500
      </span>
    </Row>
    <Stack gap={6} style={{ marginTop: 10 }}>
      {ALLOCATIONS.map(([n, c, count, pct]) => (
        <Row key={n} gap={10} style={{ fontSize: 12 }}>
          <span style={{ width: 12, height: 12, background: c, borderRadius: 2 }} />
          <span style={{ width: 100 }}>{n}</span>
          <div
            style={{
              flex: 1,
              height: 8,
              background: 'var(--lw-bg-sunk)',
              borderRadius: 4,
              overflow: 'hidden',
            }}
          >
            <div style={{ width: `${pct}%`, height: '100%', background: c, opacity: 0.7 }} />
          </div>
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 11,
              width: 40,
              textAlign: 'right',
            }}
          >
            {count}
          </span>
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 10,
              color: 'var(--lw-ink-4)',
              width: 30,
            }}
          >
            {pct}%
          </span>
        </Row>
      ))}
    </Stack>
  </div>
);

const PreviewMap = () => (
  <div
    style={{
      flex: 1,
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      overflow: 'hidden',
      position: 'relative',
    }}
  >
    <MapPh h={220}>
      {Array.from({ length: 60 }).map((_, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: `${(i * 37) % 100}%`,
            top: `${(i * 53) % 100}%`,
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: DOT_COLORS[i % 6],
            border: '1px solid white',
            transform: 'translate(-50%,-50%)',
          }}
        />
      ))}
    </MapPh>
    <div
      style={{
        position: 'absolute',
        top: 10,
        left: 10,
        background: 'var(--lw-surface)',
        border: '1px solid var(--lw-line)',
        borderRadius: 4,
        padding: '4px 8px',
        fontFamily: 'var(--lw-font-mono)',
        fontSize: 10,
      }}
    >
      preview · 60 / 500
    </div>
  </div>
);

export const WfSamplingGenerator = () => (
  <Frame name="10 · Sampling generator" dim="1280×800">
    <div style={{ height: 560 }}>
      <Chrome
        active="Sampling"
        title="New sampling design"
        crumbs={['Sampling']}
        actions={
          <>
            <Btn>Save draft</Btn>
            <Btn kind="primary">Generate</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 16, height: '100%' }}>
          <Stack gap={12}>
            <StrategyList />
            <ParametersBox />
          </Stack>
          <Stack gap={12}>
            <AllocationBox />
            <PreviewMap />
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
