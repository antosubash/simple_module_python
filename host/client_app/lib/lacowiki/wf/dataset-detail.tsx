import { Chrome } from '../chrome';
import { Btn, Frame, MapPh, Pill, Row, Stack } from '../primitives';

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

const cardCss = {
  border: '1px solid var(--lw-line)',
  borderRadius: 6,
  background: 'var(--lw-surface)',
  padding: 12,
} as const;

const TabBar = () => (
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
);

const MetaGrid = () => (
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
);

const SharingCard = () => (
  <div style={cardCss}>
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
);

const ConversionLog = () => (
  <div style={cardCss}>
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
);

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
            <TabBar />
            <MapPh h={280} style={{ borderRadius: 6, border: '1px solid var(--lw-line)' }} />
            <MetaGrid />
          </Stack>
          <Stack gap={12}>
            <SharingCard />
            <ConversionLog />
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
