import { Chrome } from '../chrome';
import { Btn, Frame, Row, Stack } from '../primitives';

const SECTIONS = ['Profile', 'Workspaces', 'API tokens', 'Notifications', 'Billing', 'Danger zone'];

const FIELDS: [string, string][] = [
  ['Display name', 'Myroslava Lesiv'],
  ['Email', 'm.lesiv@iiasa.ac.at'],
  ['ORCID', '0000-0001-9856-1804'],
  ['Affiliation', 'IIASA · Novel Data Ecosystems'],
];

export const WfAccount = () => (
  <Frame name="15 · Account & settings" dim="1280×800">
    <div style={{ height: 540 }}>
      <Chrome active="Dashboard" title="Settings" crumbs={['Account']}>
        <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 24, height: '100%' }}>
          <Stack gap={2}>
            {SECTIONS.map((s, i) => (
              <div
                key={s}
                style={{
                  padding: '8px 12px',
                  borderRadius: 4,
                  background: i === 0 ? 'var(--lw-bg-alt)' : 'transparent',
                  fontSize: 13,
                  fontWeight: i === 0 ? 600 : 500,
                  color: i === 0 ? 'var(--lw-ink-1)' : 'var(--lw-ink-3)',
                }}
              >
                {s}
              </div>
            ))}
          </Stack>
          <Stack gap={20}>
            <div>
              <b style={{ fontSize: 18 }}>Profile</b>
              <div style={{ fontSize: 12, color: 'var(--lw-ink-3)', marginTop: 2 }}>
                Visible to your collaborators across LacoWiki.
              </div>
            </div>
            <Row gap={16}>
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  background: 'var(--lw-bg-sunk)',
                  border: '1px solid var(--lw-line)',
                }}
              />
              <Stack gap={6}>
                <Btn>Upload photo</Btn>
                <span style={{ fontSize: 11, color: 'var(--lw-ink-4)' }}>PNG/JPG · 1MB max</span>
              </Stack>
            </Row>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {FIELDS.map(([l, v]) => (
                <Stack key={l} gap={4}>
                  <span style={{ fontSize: 12, fontWeight: 500 }}>{l}</span>
                  <div
                    style={{
                      height: 32,
                      border: '1px solid var(--lw-line)',
                      borderRadius: 4,
                      padding: '0 10px',
                      fontSize: 13,
                      display: 'flex',
                      alignItems: 'center',
                      background: 'var(--lw-surface)',
                    }}
                  >
                    {v}
                  </div>
                </Stack>
              ))}
            </div>
            <Row gap={8}>
              <Btn>Cancel</Btn>
              <Btn kind="primary">Save changes</Btn>
            </Row>
          </Stack>
        </div>
      </Chrome>
    </div>
  </Frame>
);
