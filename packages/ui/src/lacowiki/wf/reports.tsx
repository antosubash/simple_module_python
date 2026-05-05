import { Chrome } from '../chrome';
import { Btn, Frame, Pill, Row, Stack } from '../primitives';

export { WfReportMatrix } from './report-matrix';

const REPORT_CARDS: [string, string, string, string][] = [
  ['Africa LC 2020 — accuracy', '87.3%', '±2.1', '2h'],
  ['Tropical forest 2024', '91.2%', '±1.4', '1d'],
  ['EU urban v2', '78.5%', '±3.0', '3d'],
  ['Sahel cropmask v1', '82.1%', '±2.8', '1w'],
];

const monoUpper: React.CSSProperties = {
  fontFamily: 'var(--lw-font-mono)',
  fontSize: 10,
  color: 'var(--lw-ink-4)',
  textTransform: 'uppercase',
};

export const WfReportsList = () => (
  <Frame name="13 · Reports — list" dim="1280×720">
    <div style={{ height: 500 }}>
      <Chrome
        active="Reports"
        title="Reports"
        crumbs={['Workspace']}
        actions={<Btn kind="primary">+ New report</Btn>}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12 }}>
          {REPORT_CARDS.map((r) => (
            <div
              key={r[0]}
              style={{
                border: '1px solid var(--lw-line)',
                borderRadius: 6,
                background: 'var(--lw-surface)',
                padding: 16,
              }}
            >
              <Row gap={8} style={{ marginBottom: 8 }}>
                <span className="mod-dot mod-reports" />
                <span style={monoUpper}>Accuracy report</span>
                <Pill tone="ok">computed</Pill>
              </Row>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>{r[0]}</div>
              <Row gap={20}>
                <Stack gap={2}>
                  <span style={monoUpper}>OA</span>
                  <span style={{ fontSize: 22, fontWeight: 600 }}>{r[1]}</span>
                  <span
                    style={{
                      fontFamily: 'var(--lw-font-mono)',
                      fontSize: 10,
                      color: 'var(--lw-ink-3)',
                    }}
                  >
                    {r[2]}% CI
                  </span>
                </Stack>
                <Stack gap={2}>
                  <span style={monoUpper}>κ</span>
                  <span style={{ fontSize: 22, fontWeight: 600 }}>0.81</span>
                </Stack>
                <Stack gap={2} style={{ marginLeft: 'auto' }}>
                  <span
                    style={{
                      fontFamily: 'var(--lw-font-mono)',
                      fontSize: 10,
                      color: 'var(--lw-ink-4)',
                    }}
                  >
                    {r[3]} ago
                  </span>
                </Stack>
              </Row>
            </div>
          ))}
        </div>
      </Chrome>
    </div>
  </Frame>
);
