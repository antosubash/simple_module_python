import { Chrome } from '../chrome';
import { Btn, Frame, Pill, Placeholder, Row, Stack } from '../primitives';

const LEGEND_CARDS: [string, string, 'template' | 'custom' | 'draft', string][] = [
  ['IPCC LULUCF', '6 classes', 'template', '#3a7d44|#d6a456|#bcc972|#5b8aa8|#9a3b3b|#7c7c7c'],
  ['CORINE L1', '5 classes', 'template', '#9a3b3b|#d6a456|#3a7d44|#5b8aa8|#bcc972'],
  [
    'FAO LCCS',
    '8 classes',
    'template',
    '#3a7d44|#7ba368|#bcc972|#d6a456|#a8895a|#5b8aa8|#9a3b3b|#7c7c7c',
  ],
  ['Sahel cropmask', '3 classes', 'custom', '#d6a456|#bcc972|#7c7c7c'],
  ['EU urban extents', '4 classes', 'custom', '#9a3b3b|#c47171|#bcc972|#7c7c7c'],
  [
    'Forest types v2',
    '7 classes',
    'draft',
    '#2d6034|#3a7d44|#5e9c6a|#7ba368|#a3c08e|#7c7c7c|#bcc972',
  ],
];

export const WfLegendsList = () => (
  <Frame name="07 · Legends — list" dim="1280×720">
    <div style={{ height: 500 }}>
      <Chrome
        active="Legends"
        title="Legends"
        crumbs={['Workspace']}
        actions={
          <>
            <Btn>Import</Btn>
            <Btn kind="primary">+ New legend</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {LEGEND_CARDS.map(([name, count, kind, swatches]) => (
            <div
              key={name}
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 14,
              }}
            >
              <Row justify="space-between">
                <Row gap={6}>
                  <span className="mod-dot mod-legends" />
                  <b style={{ fontSize: 13 }}>{name}</b>
                </Row>
                <Pill tone={kind === 'template' ? 'accent' : 'default'}>{kind}</Pill>
              </Row>
              <div
                style={{
                  fontFamily: 'var(--lw-font-mono)',
                  fontSize: 10,
                  color: 'var(--lw-ink-4)',
                  margin: '6px 0 10px',
                }}
              >
                {count}
              </div>
              <Row gap={2}>
                {swatches.split('|').map((c, j) => (
                  <div key={j} style={{ flex: 1, height: 16, background: c, borderRadius: 2 }} />
                ))}
              </Row>
            </div>
          ))}
        </div>
      </Chrome>
    </div>
  </Frame>
);

const CLASSES: [string, string, string, string][] = [
  ['1', 'Forest land', '#3a7d44', 'FRST'],
  ['2', 'Cropland', '#d6a456', 'CROP'],
  ['3', 'Grassland', '#bcc972', 'GRSS'],
  ['4', 'Wetlands', '#5b8aa8', 'WTLD'],
  ['5', 'Settlements', '#9a3b3b', 'STTL'],
  ['6', 'Other', '#7c7c7c', 'OTHR'],
];

const COLOR_OPTIONS = ['#bcc972', '#9aaa55', '#d4dc9a', '#7d8b46', '#e8eed0', '#6b7a35'];

export const WfLegendBuilder = () => (
  <Frame name="08 · Legend builder" dim="1280×720">
    <div style={{ height: 500 }}>
      <Chrome
        active="Legends"
        title="IPCC LULUCF — edit"
        crumbs={['Legends']}
        actions={
          <>
            <Btn>Discard</Btn>
            <Btn kind="primary">Save legend</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, height: '100%' }}>
          <div
            style={{
              border: '1px solid var(--lw-line)',
              borderRadius: 6,
              background: 'var(--lw-surface)',
              overflow: 'hidden',
            }}
          >
            <Row
              justify="space-between"
              style={{ padding: '10px 14px', borderBottom: '1px solid var(--lw-line-soft)' }}
            >
              <b style={{ fontSize: 13 }}>Classes (6)</b>
              <Btn>+ Add class</Btn>
            </Row>
            {CLASSES.map((r, i) => (
              <Row
                key={r[0]}
                gap={12}
                style={{
                  padding: '10px 14px',
                  borderBottom: i < 5 ? '1px solid var(--lw-line-soft)' : 0,
                  fontSize: 12,
                  background: i === 2 ? 'var(--lw-accent-soft)' : 'transparent',
                }}
              >
                <span
                  style={{
                    width: 16,
                    color: 'var(--lw-ink-4)',
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 10,
                  }}
                >
                  {r[0]}
                </span>
                <span
                  style={{
                    width: 18,
                    height: 18,
                    background: r[2],
                    borderRadius: 3,
                    border: '1px solid rgba(0,0,0,0.1)',
                  }}
                />
                <span style={{ flex: 1, fontWeight: 500 }}>{r[1]}</span>
                <span
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 10,
                    color: 'var(--lw-ink-4)',
                  }}
                >
                  {r[3]}
                </span>
                <span style={{ color: 'var(--lw-ink-4)' }}>⋮</span>
              </Row>
            ))}
          </div>
          <Stack gap={12}>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 12,
              }}
            >
              <b style={{ fontSize: 13 }}>Class details</b>
              <Stack gap={8} style={{ marginTop: 10 }}>
                <Stack gap={4}>
                  <span style={{ fontSize: 11, fontWeight: 500 }}>Label</span>
                  <div
                    style={{
                      height: 28,
                      border: '1px solid var(--lw-line)',
                      borderRadius: 4,
                      padding: '0 8px',
                      fontSize: 12,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    Grassland
                  </div>
                </Stack>
                <Stack gap={4}>
                  <span style={{ fontSize: 11, fontWeight: 500 }}>Code</span>
                  <div
                    style={{
                      height: 28,
                      border: '1px solid var(--lw-line)',
                      borderRadius: 4,
                      padding: '0 8px',
                      fontFamily: 'var(--lw-font-mono)',
                      fontSize: 11,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    GRSS
                  </div>
                </Stack>
                <Stack gap={4}>
                  <span style={{ fontSize: 11, fontWeight: 500 }}>Color</span>
                  <Row gap={4}>
                    {COLOR_OPTIONS.map((c) => (
                      <div
                        key={c}
                        style={{
                          width: 24,
                          height: 24,
                          background: c,
                          borderRadius: 3,
                          border:
                            c === '#bcc972'
                              ? '2px solid var(--lw-ink-1)'
                              : '1px solid var(--lw-line)',
                        }}
                      />
                    ))}
                  </Row>
                </Stack>
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
              <b style={{ fontSize: 13 }}>Description</b>
              <Placeholder label="Definition · field guide notes" h={70} style={{ marginTop: 8 }} />
            </div>
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
