import {
  ACCENTS,
  MODULES,
  NEUTRALS,
  SampleCard,
  SampleTable,
  SPACING,
  SpatialLegend,
  SpatialMap,
  Swatch,
  TYPE_SPECS,
} from './design-system-blocks';
import { Btn, Pill, Placeholder, Stack } from './primitives';

export const DesignSystem = () => (
  <div className="ds-grid">
    <div>
      <div className="eyebrow">01 — System</div>
      <h1 className="h-display">Design system</h1>
      <p className="lede">
        A neutral, technical palette built around precise typography and one accent. Tokens are
        intentional and few — the aim is restraint, so map data and validation imagery can carry the
        visual weight.
      </p>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Neutrals</div>
        Cool grays, near-zero saturation. Used for surfaces, ink, and lines.
      </div>
      <div className="swatch-row">
        {NEUTRALS.map(([n, t, v]) => (
          <Swatch key={n} name={n} token={t} value={v} css={v} />
        ))}
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Accent</div>A single teal-cyan family for selected state,
        links, and primary CTAs. Same chroma across the family.
      </div>
      <div className="swatch-row">
        {ACCENTS.map(([n, t, v]) => (
          <Swatch key={n} name={n} token={t} value={v} css={v} />
        ))}
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Module keys</div>
        Tiny color dots for sidebar items and badges, drawn from a neutral hue family at fixed
        chroma.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        {MODULES.map(([n, c]) => (
          <div
            key={n}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '10px 12px',
              border: '1px solid var(--lw-line)',
              borderRadius: 6,
              background: 'var(--lw-surface)',
            }}
          >
            <span
              className={`mod-dot mod-${c}`}
              style={{ width: 12, height: 12, borderRadius: 3 }}
            />
            <span style={{ fontSize: 13, fontWeight: 500 }}>{n}</span>
            <span
              style={{
                fontFamily: 'var(--lw-font-mono)',
                fontSize: 10,
                color: 'var(--lw-ink-4)',
                marginLeft: 'auto',
              }}
            >
              mod-{c}
            </span>
          </div>
        ))}
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Type</div>
        Inter for UI. JetBrains Mono for tabular data, IDs, code, technical labels. Caveat for
        hand-drawn margin annotations only.
      </div>
      <div className="type-stack">
        {TYPE_SPECS.map(([meta, sample], i) => (
          <div className="type-spec" key={i}>
            <div className="meta">{meta}</div>
            <div>{sample}</div>
          </div>
        ))}
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Spacing & radius</div>
        4px base. Components round to <code>--r-2</code> (4px) by default; cards to{' '}
        <code>--r-3</code> (6px). Avoid heavy radii.
      </div>
      <div className="token-grid">
        {SPACING.map(([n, v]) => (
          <div key={n} className="token">
            <div
              className="demo"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-start' }}
            >
              <div
                style={{ height: 24, width: v, background: 'var(--lw-accent)', borderRadius: 2 }}
              />
            </div>
            <div className="name">
              <b>--{n}</b> · {v}px
            </div>
          </div>
        ))}
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Buttons & badges</div>
        One primary (ink-1), accent for spatial actions, ghost for secondary. Mono badges for
        status.
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
        <Btn kind="primary">Run sampling</Btn>
        <Btn kind="accent">Open on map</Btn>
        <Btn>Cancel</Btn>
        <Btn icon="↓">Export CSV</Btn>
        <span style={{ width: 1, height: 24, background: 'var(--lw-line)' }} />
        <Pill>draft</Pill>
        <Pill tone="ok">ready</Pill>
        <Pill tone="warn">processing</Pill>
        <Pill tone="accent">shared · 3</Pill>
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Cards, tables, lists</div>
        Cards on <code>--surface</code>, 1px <code>--line</code>, no shadow. Tables zebra-free; row
        hover only.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <SampleCard />
        <SampleTable />
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Spatial UI</div>
        The map components are the heart of the product. Restrained chrome — controls float on the
        map; legend collapses; sample markers are 6–10px discs.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 12 }}>
        <SpatialMap />
        <SpatialLegend />
      </div>
    </div>

    <div className="ds-row">
      <div className="label">
        <div className="label-title">Forms & inputs</div>
        Native-feeling text inputs, dotted borders for drop zones. Labels live above; helper text
        below in <code>--ink-3</code>.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Stack gap={12}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>Dataset name</div>
            <div
              style={{
                height: 32,
                border: '1px solid var(--lw-line)',
                borderRadius: 4,
                padding: '0 10px',
                display: 'flex',
                alignItems: 'center',
                fontSize: 13,
                background: 'var(--lw-surface)',
              }}
            >
              Africa LC 2020 v3
            </div>
            <div style={{ fontSize: 11, color: 'var(--lw-ink-3)', marginTop: 4 }}>
              Used as the title across the workspace.
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>Coordinate system</div>
            <div
              style={{
                height: 32,
                border: '1px solid var(--lw-line)',
                borderRadius: 4,
                padding: '0 10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: 13,
                background: 'var(--lw-surface)',
              }}
            >
              <span style={{ fontFamily: 'var(--lw-font-mono)' }}>EPSG:4326</span>
              <span style={{ color: 'var(--lw-ink-4)' }}>▾</span>
            </div>
          </div>
        </Stack>
        <Placeholder label="Drop GeoTIFF or Shapefile here · or click to browse" h={140} />
      </div>
    </div>
  </div>
);
