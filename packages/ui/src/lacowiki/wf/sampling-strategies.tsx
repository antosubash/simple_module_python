import { Frame, Row, Stack } from '../primitives';

type Field = { l: string; v: string; mono?: boolean };
type Strategy = { label: string; note: string; fields: Field[] };

const StrategyParams: Record<string, Strategy> = {
  simple: {
    label: 'Simple random',
    note: 'Points uniformly at random across the study area.',
    fields: [
      { l: 'Total points (n)', v: '100', mono: true },
      { l: 'Study area', v: 'Africa LC 2020 v3 extent' },
      { l: 'Min spacing', v: '0 m (none)', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  stratified: {
    label: 'Stratified random',
    note: 'Points allocated per legend class. See allocation panel →',
    fields: [
      { l: 'Total points (n)', v: '500', mono: true },
      { l: 'Stratification', v: 'IPCC LULUCF (6)' },
      { l: 'Allocation method', v: 'proportional ▾' },
      { l: 'Min per stratum', v: '20', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  systematic: {
    label: 'Systematic grid',
    note: 'Regular lattice. Origin offset randomised by seed.',
    fields: [
      { l: 'Grid spacing', v: '1.0 km', mono: true },
      { l: 'Grid type', v: 'square ▾' },
      { l: 'Random origin', v: '✓ enabled' },
      { l: 'Approx. n', v: '≈ 1240', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  cluster: {
    label: 'Cluster',
    note: 'Primary clusters drawn first, then sites within each.',
    fields: [
      { l: 'Clusters (PSU)', v: '20', mono: true },
      { l: 'Cluster shape', v: '10 km square ▾' },
      { l: 'Sites per cluster', v: '10', mono: true },
      { l: 'Total points (n)', v: '200', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  twostage: {
    label: 'Two-stage',
    note: 'Strata → clusters → sites. Useful for fieldwork logistics.',
    fields: [
      { l: 'Stage 1 — strata', v: 'IPCC LULUCF (6)' },
      { l: 'Stage 1 — clusters/stratum', v: '5', mono: true },
      { l: 'Stage 2 — sites/cluster', v: '10', mono: true },
      { l: 'Total points (n)', v: '300', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  equal: {
    label: 'Equal allocation',
    note: 'Same n per legend class regardless of area.',
    fields: [
      { l: 'Stratification', v: 'IPCC LULUCF (6)' },
      { l: 'Points per class', v: '50', mono: true },
      { l: 'Total points (n)', v: '300', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
  proportional: {
    label: 'Proportional allocation',
    note: 'n per class scaled to mapped area share.',
    fields: [
      { l: 'Stratification', v: 'IPCC LULUCF (6)' },
      { l: 'Total points (n)', v: '500', mono: true },
      { l: 'Min per class', v: '20', mono: true },
      { l: 'Random seed', v: '4831', mono: true },
    ],
  },
};

const StrategyCard = ({ k }: { k: string }) => {
  const s = StrategyParams[k];
  return (
    <div
      style={{
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        background: 'var(--lw-surface)',
        padding: 14,
      }}
    >
      <Row justify="space-between">
        <b style={{ fontSize: 13 }}>{s.label}</b>
        <span className="wf-pill accent" style={{ fontSize: 10 }}>
          {k}
        </span>
      </Row>
      <div style={{ fontSize: 11, color: 'var(--lw-ink-3)', marginTop: 4 }}>{s.note}</div>
      <Stack gap={8} style={{ marginTop: 12 }}>
        {s.fields.map((f, i) => (
          <Stack key={i} gap={4}>
            <span style={{ fontSize: 11, fontWeight: 500 }}>{f.l}</span>
            <div
              style={{
                height: 28,
                border: '1px solid var(--lw-line)',
                borderRadius: 4,
                padding: '0 10px',
                fontSize: 12,
                fontFamily: f.mono ? 'var(--lw-font-mono)' : 'var(--lw-font-ui)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--lw-surface)',
              }}
            >
              {f.v}
            </div>
          </Stack>
        ))}
      </Stack>
    </div>
  );
};

export const WfSamplingStrategies = () => (
  <Frame name="10b · Strategy parameter cards (one per type)" dim="1280×800">
    <div style={{ padding: 16, background: 'var(--lw-bg-alt)' }}>
      <div
        style={{
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 11,
          color: 'var(--lw-ink-3)',
          marginBottom: 12,
        }}
      >
        Each strategy swaps the right-hand panel of the generator. Below: all 7 cards side-by-side.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {Object.keys(StrategyParams).map((k) => (
          <StrategyCard key={k} k={k} />
        ))}
      </div>
    </div>
  </Frame>
);
