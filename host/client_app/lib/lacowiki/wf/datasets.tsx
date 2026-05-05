import { Chrome } from '../chrome';
import { Btn, Frame, Pill, Placeholder, Row, Stack } from '../primitives';

export { WfDatasetDetail } from './dataset-detail';

const COLS_GRID = '2fr 90px 100px 90px 90px 80px 60px';

type Status = 'ready' | 'processing' | 'failed';

const ROWS: [string, string, Status, string, string, string][] = [
  ['Africa LC 2020 v3', 'COG', 'ready', '4.2 GB', '3', '2h'],
  ['Tropical Forest 2024', 'PMTiles', 'processing', '1.8 GB', '—', '12h'],
  ['Urban Extents EU', 'COG', 'ready', '850 MB', '8', '2d'],
  ['Sahel Cropmask v2', 'COG', 'failed', '—', '—', '3d'],
  ['WorldPop 2020 mask', 'PMTiles', 'ready', '2.1 GB', '12', '1w'],
];

export const WfDatasetsList = () => (
  <Frame name="04 · Datasets — list" dim="1280×800">
    <div style={{ height: 540 }}>
      <Chrome
        active="Datasets"
        title="Datasets"
        crumbs={['Workspace']}
        actions={
          <>
            <Btn>Filter</Btn>
            <Btn kind="primary">+ Upload</Btn>
          </>
        }
      >
        <Stack gap={12}>
          <Row gap={8}>
            <div
              style={{
                flex: 1,
                height: 32,
                border: '1px solid var(--lw-line)',
                borderRadius: 4,
                padding: '0 10px',
                fontSize: 12,
                background: 'var(--lw-surface)',
                display: 'flex',
                alignItems: 'center',
                color: 'var(--lw-ink-4)',
              }}
            >
              Search 12 datasets…
            </div>
            <Btn>Type ▾</Btn>
            <Btn>Owner ▾</Btn>
            <Btn>Status ▾</Btn>
          </Row>
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
                gridTemplateColumns: COLS_GRID,
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
              <span>Name</span>
              <span>Type</span>
              <span>Status</span>
              <span>Size</span>
              <span>Shared</span>
              <span>Updated</span>
              <span></span>
            </div>
            {ROWS.map((r, i) => (
              <div
                key={r[0]}
                style={{
                  display: 'grid',
                  gridTemplateColumns: COLS_GRID,
                  padding: '10px 14px',
                  fontSize: 12,
                  alignItems: 'center',
                  borderBottom: i < ROWS.length - 1 ? '1px solid var(--lw-line-soft)' : 0,
                }}
              >
                <Row gap={10}>
                  <span className="mod-dot mod-datasets" />
                  <b>{r[0]}</b>
                </Row>
                <span
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 10,
                    color: 'var(--lw-ink-4)',
                  }}
                >
                  {r[1]}
                </span>
                <Pill tone={r[2] === 'ready' ? 'ok' : 'warn'}>{r[2]}</Pill>
                <span
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 11,
                    color: 'var(--lw-ink-3)',
                  }}
                >
                  {r[3]}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 11,
                    color: 'var(--lw-ink-3)',
                  }}
                >
                  {r[4]}
                </span>
                <span
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 11,
                    color: 'var(--lw-ink-4)',
                  }}
                >
                  {r[5]}
                </span>
                <span style={{ color: 'var(--lw-ink-4)', textAlign: 'right' }}>⋯</span>
              </div>
            ))}
          </div>
        </Stack>
      </Chrome>
    </div>
  </Frame>
);

export const WfDatasetUpload = () => (
  <Frame name="05 · Datasets — upload" dim="800×600">
    <div style={{ height: 480, padding: 32, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row justify="space-between">
        <b style={{ fontSize: 18 }}>Upload dataset</b>
        <span style={{ color: 'var(--lw-ink-4)' }}>✕</span>
      </Row>
      <Row gap={4} style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 11 }}>
        <span style={{ color: 'var(--lw-accent-ink)' }}>1 · file</span>
        <span style={{ color: 'var(--lw-ink-4)' }}>→</span>
        <span style={{ color: 'var(--lw-ink-4)' }}>2 · metadata</span>
        <span style={{ color: 'var(--lw-ink-4)' }}>→</span>
        <span style={{ color: 'var(--lw-ink-4)' }}>3 · convert</span>
      </Row>
      <Placeholder label="Drop GeoTIFF / Shapefile / GeoPackage here · max 8 GB" h={180} />
      <Stack gap={6}>
        <Row gap={8}>
          <span className="wf-pill ok">africa_lc_2020.tif</span>
          <span
            style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 11, color: 'var(--lw-ink-4)' }}
          >
            4.2 GB · uploading 64%
          </span>
        </Row>
        <div
          style={{
            height: 6,
            background: 'var(--lw-bg-sunk)',
            borderRadius: 3,
            overflow: 'hidden',
          }}
        >
          <div style={{ width: '64%', height: '100%', background: 'var(--lw-accent)' }} />
        </div>
        <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}>
          auto-detected EPSG:4326 · COG · 14328×11200
        </span>
      </Stack>
      <Row gap={8} justify="flex-end" style={{ marginTop: 'auto' }}>
        <Btn>Cancel</Btn>
        <Btn kind="primary">Continue →</Btn>
      </Row>
    </div>
  </Frame>
);
