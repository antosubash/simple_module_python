import { Chrome } from '../chrome';
import { Btn, Frame, MapPh, Pill, Placeholder, Row, Stack } from '../primitives';

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

const META: [string, string][] = [
  ['CRS', 'EPSG:4326'],
  ['Resolution', '10 m'],
  ['Extent', 'Africa'],
  ['Format', 'COG'],
];

const SHARES: [string, string][] = [
  ['m.lesiv@iiasa', 'owner'],
  ['d.fritz@iiasa', 'editor'],
  ['public link', 'viewer'],
];

const DETAIL_TABS = ['Overview', 'Sampling (3)', 'Validations (2)', 'Reports (1)', 'Activity'];

export const WfDatasetDetail = () => (
  <Frame name="06 · Dataset — detail + share" dim="1280×800">
    <div style={{ height: 560 }}>
      <Chrome
        active="Datasets"
        title="Africa LC 2020 v3"
        crumbs={['Datasets']}
        actions={
          <>
            <Btn>Share</Btn>
            <Btn>Download</Btn>
            <Btn kind="accent">Open on map</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, height: '100%' }}>
          <Stack gap={12}>
            <Row gap={8}>
              {DETAIL_TABS.map((t, i) => (
                <span
                  key={t}
                  style={{
                    fontSize: 12,
                    fontWeight: i === 0 ? 600 : 500,
                    color: i === 0 ? 'var(--lw-ink-1)' : 'var(--lw-ink-3)',
                    borderBottom: i === 0 ? '2px solid var(--lw-ink-1)' : '2px solid transparent',
                    padding: '0 0 6px',
                  }}
                >
                  {t}
                </span>
              ))}
            </Row>
            <MapPh h={280} style={{ borderRadius: 6, border: '1px solid var(--lw-line)' }} />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12 }}>
              {META.map(([l, v]) => (
                <div
                  key={l}
                  style={{
                    padding: 10,
                    border: '1px solid var(--lw-line)',
                    borderRadius: 6,
                    background: 'var(--lw-surface)',
                  }}
                >
                  <div
                    style={{
                      fontFamily: 'var(--lw-font-mono)',
                      fontSize: 10,
                      color: 'var(--lw-ink-4)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                    }}
                  >
                    {l}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{v}</div>
                </div>
              ))}
            </div>
          </Stack>
          <Stack gap={12}>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 12,
              }}
            >
              <b style={{ fontSize: 13 }}>Sharing</b>
              <Stack gap={8} style={{ marginTop: 10 }}>
                {SHARES.map(([who, role]) => (
                  <Row key={who} gap={8}>
                    <div
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: '50%',
                        background: 'var(--lw-bg-sunk)',
                        border: '1px solid var(--lw-line)',
                      }}
                    />
                    <span style={{ fontSize: 12, flex: 1 }}>{who}</span>
                    <Pill>{role}</Pill>
                  </Row>
                ))}
                <Btn>+ Invite people</Btn>
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
              <b style={{ fontSize: 13 }}>Conversion log</b>
              <Stack
                gap={6}
                style={{
                  marginTop: 8,
                  fontFamily: 'var(--lw-font-mono)',
                  fontSize: 10,
                  color: 'var(--lw-ink-3)',
                }}
              >
                <div>✓ uploaded · 4.2 GB</div>
                <div>✓ tippecanoe → PMTiles</div>
                <div>✓ rio-cogeo → COG</div>
                <div style={{ color: 'var(--lw-accent-ink)' }}>✓ ready · 2h ago</div>
              </Stack>
            </div>
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
