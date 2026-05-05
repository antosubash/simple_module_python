import { Btn, Frame, MapPh, Pill, Row, Stack } from '../primitives';

export const WfLanding = () => (
  <Frame name="01 · Landing (public)" dim="1280×800">
    <div
      style={{ background: 'var(--lw-bg)', height: 520, display: 'flex', flexDirection: 'column' }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '14px 32px',
          borderBottom: '1px solid var(--lw-line-soft)',
        }}
      >
        <Row gap={10}>
          <div style={{ width: 18, height: 18, background: 'var(--lw-ink-1)', borderRadius: 4 }} />
          <b style={{ fontSize: 13 }}>LacoWiki</b>
        </Row>
        <Row gap={20} style={{ marginLeft: 32, fontSize: 12, color: 'var(--lw-ink-3)' }}>
          <span>Product</span>
          <span>Datasets</span>
          <span>Methodology</span>
          <span>Docs</span>
        </Row>
        <Row gap={8} style={{ marginLeft: 'auto' }}>
          <Btn>Sign in</Btn>
          <Btn kind="primary">Request access</Btn>
        </Row>
      </div>
      <div
        style={{
          flex: 1,
          padding: '48px 32px',
          display: 'grid',
          gridTemplateColumns: '1.1fr 1fr',
          gap: 40,
          alignItems: 'center',
        }}
      >
        <Stack gap={16}>
          <Pill>Open platform · IIASA</Pill>
          <div
            style={{ fontSize: 40, lineHeight: 1.05, letterSpacing: '-0.02em', fontWeight: 600 }}
          >
            Validate land cover
            <br />
            maps with confidence.
          </div>
          <div style={{ fontSize: 14, color: 'var(--lw-ink-3)', maxWidth: 440 }}>
            Upload classifications, design sampling, validate against high-resolution imagery, and
            publish accuracy reports — all in one workspace.
          </div>
          <Row gap={8}>
            <Btn kind="primary">Get started</Btn>
            <Btn>Watch demo · 2 min</Btn>
          </Row>
          <Row
            gap={20}
            style={{
              marginTop: 8,
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 11,
              color: 'var(--lw-ink-4)',
            }}
          >
            <span>14k+ datasets</span>
            <span>·</span>
            <span>2.4M validated points</span>
            <span>·</span>
            <span>open source</span>
          </Row>
        </Stack>
        <div style={{ position: 'relative' }}>
          <MapPh h={300} style={{ borderRadius: 8, border: '1px solid var(--lw-line)' }}>
            {(
              [
                [30, 40],
                [60, 55],
                [75, 30],
                [45, 70],
                [20, 55],
              ] as [number, number][]
            ).map(([x, y], i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: `${x}%`,
                  top: `${y}%`,
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  background: i === 2 ? 'var(--lw-accent)' : 'var(--lw-surface)',
                  border: '1.5px solid var(--lw-ink-1)',
                  transform: 'translate(-50%,-50%)',
                }}
              />
            ))}
          </MapPh>
          <div
            style={{
              position: 'absolute',
              bottom: -16,
              right: -16,
              background: 'var(--lw-surface)',
              border: '1px solid var(--lw-line)',
              borderRadius: 6,
              padding: 12,
              width: 200,
              fontSize: 11,
            }}
          >
            <div
              style={{
                fontFamily: 'var(--lw-font-mono)',
                fontSize: 10,
                color: 'var(--lw-ink-4)',
                marginBottom: 6,
              }}
            >
              OVERALL ACCURACY
            </div>
            <div style={{ fontSize: 24, fontWeight: 600 }}>87.3%</div>
            <div style={{ color: 'var(--lw-ink-3)', marginTop: 2 }}>±2.1% at 95% CI</div>
          </div>
        </div>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4,1fr)',
          gap: 16,
          padding: '0 32px 32px',
        }}
      >
        {(
          [
            ['Datasets', 'Upload COG/PMTiles'],
            ['Sampling', '7 strategies'],
            ['Validation', 'Map-side classify'],
            ['Reports', 'Confusion matrix'],
          ] as [string, string][]
        ).map(([t, s]) => (
          <div key={t} style={{ padding: 12, borderTop: '1px solid var(--lw-line)' }}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>{t}</div>
            <div style={{ fontSize: 11, color: 'var(--lw-ink-3)' }}>{s}</div>
          </div>
        ))}
      </div>
    </div>
  </Frame>
);

const inputCss = {
  height: 36,
  border: '1px solid var(--lw-line)',
  borderRadius: 4,
  padding: '0 10px',
  fontSize: 13,
  display: 'flex',
  alignItems: 'center',
  color: 'var(--lw-ink-3)',
} as const;

export const WfLogin = () => (
  <Frame name="02 · Sign in" dim="1280×800">
    <div style={{ height: 520, display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
      <div
        style={{
          padding: 48,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          maxWidth: 360,
          margin: '0 auto',
        }}
      >
        <Row gap={10} style={{ marginBottom: 40 }}>
          <div style={{ width: 22, height: 22, background: 'var(--lw-ink-1)', borderRadius: 4 }} />
          <b>LacoWiki</b>
        </Row>
        <div style={{ fontSize: 24, fontWeight: 600, letterSpacing: '-0.01em' }}>Welcome back</div>
        <div style={{ fontSize: 13, color: 'var(--lw-ink-3)', marginBottom: 24 }}>
          Sign in to continue your validation work.
        </div>
        <Stack gap={12}>
          <Stack gap={4}>
            <span style={{ fontSize: 12, fontWeight: 500 }}>Email</span>
            <div style={inputCss}>you@institution.org</div>
          </Stack>
          <Stack gap={4}>
            <Row justify="space-between">
              <span style={{ fontSize: 12, fontWeight: 500 }}>Password</span>
              <span style={{ fontSize: 11, color: 'var(--lw-accent-ink)' }}>Forgot?</span>
            </Row>
            <div style={inputCss}>••••••••</div>
          </Stack>
          <Btn kind="primary">Sign in</Btn>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              color: 'var(--lw-ink-4)',
              fontSize: 11,
            }}
          >
            <span style={{ flex: 1, height: 1, background: 'var(--lw-line)' }} />
            OR
            <span style={{ flex: 1, height: 1, background: 'var(--lw-line)' }} />
          </div>
          <Btn>Continue with ORCID</Btn>
          <Btn>Continue with institutional SSO</Btn>
        </Stack>
      </div>
      <div
        style={{
          background: 'var(--lw-bg-alt)',
          borderLeft: '1px solid var(--lw-line-soft)',
          display: 'grid',
          placeItems: 'center',
        }}
      >
        <MapPh
          h={360}
          style={{ width: '80%', borderRadius: 8, border: '1px solid var(--lw-line)' }}
        />
      </div>
    </div>
  </Frame>
);
