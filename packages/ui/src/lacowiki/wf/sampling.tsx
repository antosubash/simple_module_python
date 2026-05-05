import { Chrome } from '../chrome';
import { Btn, Frame, MapPh, Pill, Row, Stack } from '../primitives';

const LIST_GRID = '2fr 130px 90px 90px 100px 80px 60px';

type SampleStatus = 'ready' | 'generating' | 'draft';

const SAMPLING_ROWS: [string, string, string, SampleStatus, string, string][] = [
  ['Africa LC stratified 500', 'stratified random', '500', 'ready', 'Africa LC 2020', '2h'],
  ['Tropical systematic 1km', 'systematic grid', '1240', 'ready', 'Tropical Forest 2024', '1d'],
  ['EU urban cluster 200', 'cluster', '200', 'generating', 'Urban Extents EU', '12m'],
  ['Sahel simple random 100', 'simple random', '100', 'draft', 'Sahel Cropmask v2', '3d'],
];

export const WfSamplingList = () => (
  <Frame name="09 · Sampling — list" dim="1280×720">
    <div style={{ height: 500 }}>
      <Chrome
        active="Sampling"
        title="Sampling designs"
        crumbs={['Workspace']}
        actions={<Btn kind="primary">+ New design</Btn>}
      >
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
              display: 'grid',
              gridTemplateColumns: LIST_GRID,
              padding: '8px 14px',
              borderBottom: '1px solid var(--lw-line)',
              background: 'var(--lw-bg-alt)',
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 10,
              letterSpacing: '0.06em',
              color: 'var(--lw-ink-4)',
              textTransform: 'uppercase',
            }}
          >
            <span>Design</span>
            <span>Strategy</span>
            <span>n</span>
            <span>Status</span>
            <span>Dataset</span>
            <span>Updated</span>
            <span></span>
          </div>
          {SAMPLING_ROWS.map((r, i) => (
            <div
              key={r[0]}
              style={{
                display: 'grid',
                gridTemplateColumns: LIST_GRID,
                padding: '10px 14px',
                fontSize: 12,
                alignItems: 'center',
                borderBottom: i < SAMPLING_ROWS.length - 1 ? '1px solid var(--lw-line-soft)' : 0,
              }}
            >
              <Row gap={10}>
                <span className="mod-dot mod-sampling" />
                <b>{r[0]}</b>
              </Row>
              <span
                style={{
                  fontFamily: 'var(--lw-font-mono)',
                  fontSize: 10,
                  color: 'var(--lw-ink-3)',
                }}
              >
                {r[1]}
              </span>
              <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 11 }}>{r[2]}</span>
              <Pill tone={r[3] === 'ready' ? 'ok' : r[3] === 'generating' ? 'warn' : 'default'}>
                {r[3]}
              </Pill>
              <span style={{ fontSize: 11, color: 'var(--lw-ink-3)' }}>{r[4]}</span>
              <span
                style={{
                  fontFamily: 'var(--lw-font-mono)',
                  fontSize: 10,
                  color: 'var(--lw-ink-4)',
                }}
              >
                {r[5]}
              </span>
              <span style={{ color: 'var(--lw-ink-4)', textAlign: 'right' }}>⋯</span>
            </div>
          ))}
        </div>
      </Chrome>
    </div>
  </Frame>
);

const DOT_COLORS = ['#3a7d44', '#d6a456', '#bcc972', '#5b8aa8', '#9a3b3b', '#7c7c7c'];

const SUMMARY: [string, string][] = [
  ['strategy', 'stratified random'],
  ['n', '500'],
  ['seed', '4831'],
  ['legend', 'IPCC LULUCF'],
  ['dataset', 'Africa LC 2020 v3'],
  ['created', 'by m.lesiv · 2h'],
];
const PER_CLASS: [string, string, string][] = [
  ['Forest', '180', '42%'],
  ['Cropland', '120', '18%'],
  ['Grassland', '90', '60%'],
  ['Wetlands', '50', '0%'],
  ['Settlements', '40', '12%'],
  ['Other', '20', '0%'],
];

export const WfSamplingDetail = () => (
  <Frame name="11 · Sampling — detail" dim="1280×720">
    <div style={{ height: 500 }}>
      <Chrome
        active="Sampling"
        title="Africa LC stratified 500"
        crumbs={['Sampling']}
        actions={
          <>
            <Btn>Export CSV</Btn>
            <Btn kind="accent">Start validation</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, height: '100%' }}>
          <MapPh h={400} style={{ borderRadius: 6, border: '1px solid var(--lw-line)' }}>
            {Array.from({ length: 80 }).map((_, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: `${(i * 41) % 100}%`,
                  top: `${(i * 67) % 100}%`,
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: DOT_COLORS[i % 6],
                  border: '1px solid white',
                  transform: 'translate(-50%,-50%)',
                }}
              />
            ))}
          </MapPh>
          <Stack gap={12}>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 12,
              }}
            >
              <b style={{ fontSize: 13 }}>Summary</b>
              <Stack
                gap={6}
                style={{ marginTop: 10, fontFamily: 'var(--lw-font-mono)', fontSize: 11 }}
              >
                {SUMMARY.map(([k, v]) => (
                  <Row key={k} justify="space-between">
                    <span style={{ color: 'var(--lw-ink-4)' }}>{k}</span>
                    <span>{v}</span>
                  </Row>
                ))}
              </Stack>
            </div>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 12,
              }}
            >
              <b style={{ fontSize: 13 }}>Per-class progress</b>
              <Stack gap={6} style={{ marginTop: 10, fontSize: 11 }}>
                {PER_CLASS.map((r) => (
                  <Row key={r[0]} gap={8}>
                    <span style={{ flex: 1 }}>{r[0]}</span>
                    <span style={{ fontFamily: 'var(--lw-font-mono)', color: 'var(--lw-ink-4)' }}>
                      {r[2]}
                    </span>
                    <span style={{ fontFamily: 'var(--lw-font-mono)' }}>{r[1]}</span>
                  </Row>
                ))}
              </Stack>
            </div>
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
