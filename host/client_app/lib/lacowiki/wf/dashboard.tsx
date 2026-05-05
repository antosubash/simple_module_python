import { Chrome } from '../chrome';
import { Btn, Frame, Pill, Row, Stack } from '../primitives';

const STATS: [string, string][] = [
  ['Active projects', '4'],
  ['Datasets', '12'],
  ['Pending validation', '218'],
  ['Reports this month', '3'],
];

const PROJECTS = [
  'Africa LC 2020 — accuracy assessment',
  'Tropical forest change 2024',
  'EU urban extents validation',
  'Sahel crop mask v2',
];
const PROJECT_MODS = ['validation', 'sampling', 'datasets', 'reports'];
const PROJECT_TONES: ('warn' | 'ok' | 'default')[] = ['warn', 'ok', 'default', 'default'];
const PROJECT_LABELS = ['218 to validate', 'sampling done', 'ready', 'draft'];
const PROJECT_AGES = ['2h', '1d', '3d', '1w'];

const ACTIVITY = [
  'm.lesiv shared Africa LC 2020 with you',
  'Sampling generated 500 points',
  'ConvertDatasetJob completed',
  'New comment on EU urban v2',
];
const ACTIVITY_AGES = ['12m', '1h', '3h', 'yesterday'];

export const WfDashboard = () => (
  <Frame name="03 · Dashboard" dim="1280×800">
    <div style={{ height: 560 }}>
      <Chrome
        active="Dashboard"
        title="Dashboard"
        crumbs={['Workspace']}
        actions={
          <>
            <Btn>Invite</Btn>
            <Btn kind="primary">+ New project</Btn>
          </>
        }
      >
        <Stack gap={16}>
          <Row gap={12}>
            {STATS.map(([l, v]) => (
              <div
                key={l}
                style={{
                  flex: 1,
                  border: '1px solid var(--lw-line)',
                  borderRadius: 6,
                  padding: 12,
                  background: 'var(--lw-surface)',
                }}
              >
                <div
                  style={{
                    fontFamily: 'var(--lw-font-mono)',
                    fontSize: 10,
                    color: 'var(--lw-ink-4)',
                    letterSpacing: '0.06em',
                    textTransform: 'uppercase',
                  }}
                >
                  {l}
                </div>
                <div style={{ fontSize: 24, fontWeight: 600, marginTop: 4 }}>{v}</div>
              </div>
            ))}
          </Row>
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16 }}>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
              }}
            >
              <Row
                justify="space-between"
                style={{ padding: '10px 14px', borderBottom: '1px solid var(--lw-line-soft)' }}
              >
                <b style={{ fontSize: 13 }}>Recent projects</b>
                <span style={{ fontSize: 11, color: 'var(--lw-ink-3)' }}>View all →</span>
              </Row>
              {PROJECTS.map((n, i) => (
                <Row
                  key={n}
                  gap={12}
                  style={{
                    padding: '10px 14px',
                    borderBottom: i < 3 ? '1px solid var(--lw-line-soft)' : 0,
                  }}
                >
                  <span className={`mod-dot mod-${PROJECT_MODS[i]}`} />
                  <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{n}</span>
                  <Pill tone={PROJECT_TONES[i]}>{PROJECT_LABELS[i]}</Pill>
                  <span
                    style={{
                      fontFamily: 'var(--lw-font-mono)',
                      fontSize: 10,
                      color: 'var(--lw-ink-4)',
                    }}
                  >
                    {PROJECT_AGES[i]} ago
                  </span>
                </Row>
              ))}
            </div>
            <div
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 14,
              }}
            >
              <b style={{ fontSize: 13 }}>Activity</b>
              <Stack gap={10} style={{ marginTop: 12 }}>
                {ACTIVITY.map((t, i) => (
                  <Row key={t} gap={10}>
                    <div
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: '50%',
                        background: 'var(--lw-accent)',
                        marginTop: 6,
                      }}
                    />
                    <div>
                      <div style={{ fontSize: 12 }}>{t}</div>
                      <div
                        style={{
                          fontFamily: 'var(--lw-font-mono)',
                          fontSize: 10,
                          color: 'var(--lw-ink-4)',
                        }}
                      >
                        {ACTIVITY_AGES[i]}
                      </div>
                    </div>
                  </Row>
                ))}
              </Stack>
            </div>
          </div>
        </Stack>
      </Chrome>
    </div>
  </Frame>
);
