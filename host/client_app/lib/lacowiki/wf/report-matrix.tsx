import { Fragment } from 'react';

import { Chrome } from '../chrome';
import { Btn, Frame, Row, Stack } from '../primitives';

const CLASSES = ['Forest', 'Crop', 'Grass', 'Wet', 'Settl', 'Other'];
const MATRIX: number[][] = [
  [82, 3, 1, 0, 0, 2],
  [4, 76, 5, 1, 0, 3],
  [2, 6, 71, 2, 0, 4],
  [1, 1, 2, 42, 0, 1],
  [0, 1, 0, 0, 33, 2],
  [3, 2, 4, 1, 1, 15],
];
const UA = [93, 82, 75, 89, 89, 58];
const PA = [89, 84, 84, 91, 97, 57];
const MAX = 82;

const monoLabel: React.CSSProperties = {
  fontFamily: 'var(--lw-font-mono)',
  fontSize: 10,
  color: 'var(--lw-ink-4)',
  textAlign: 'right',
  padding: '4px 8px',
};

const MatrixGrid = () => (
  <div
    style={{
      border: '1px solid var(--lw-line)',
      borderRadius: 6,
      background: 'var(--lw-surface)',
      padding: 16,
      overflow: 'auto',
    }}
  >
    <Row justify="space-between" style={{ marginBottom: 14 }}>
      <b style={{ fontSize: 13 }}>Confusion matrix · classes</b>
      <span style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 10, color: 'var(--lw-ink-4)' }}>
        rows = reference · cols = predicted
      </span>
    </Row>
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `100px repeat(6, 1fr) 80px`,
        gap: 2,
        fontSize: 11,
      }}
    >
      <span></span>
      {CLASSES.map((c) => (
        <span
          key={c}
          style={{
            fontFamily: 'var(--lw-font-mono)',
            fontSize: 10,
            color: 'var(--lw-ink-4)',
            textAlign: 'center',
            padding: '4px 0',
          }}
        >
          {c}
        </span>
      ))}
      <span style={monoLabel}>UA</span>
      {MATRIX.map((row, i) => (
        <Fragment key={i}>
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 10,
              color: 'var(--lw-ink-4)',
              padding: '8px 4px',
              textAlign: 'right',
            }}
          >
            {CLASSES[i]}
          </span>
          {row.map((v, j) => {
            const intensity = v / MAX;
            return (
              <div
                key={j}
                style={{
                  background:
                    i === j
                      ? `oklch(0.62 0.12 200 / ${0.15 + intensity * 0.7})`
                      : `oklch(0.62 0.04 200 / ${intensity * 0.5})`,
                  padding: '10px 0',
                  textAlign: 'center',
                  fontFamily: 'var(--lw-font-mono)',
                  fontWeight: i === j ? 600 : 400,
                  fontSize: 11,
                  borderRadius: 2,
                  color: intensity > 0.6 ? 'white' : 'var(--lw-ink-1)',
                }}
              >
                {v}
              </div>
            );
          })}
          <span
            style={{
              fontFamily: 'var(--lw-font-mono)',
              fontSize: 11,
              padding: 8,
              textAlign: 'right',
            }}
          >
            {UA[i]}%
          </span>
        </Fragment>
      ))}
      <span style={monoLabel}>PA</span>
      {PA.map((v, i) => (
        <span
          key={i}
          style={{
            fontFamily: 'var(--lw-font-mono)',
            fontSize: 11,
            padding: '4px 0',
            textAlign: 'center',
            color: 'var(--lw-ink-3)',
          }}
        >
          {v}%
        </span>
      ))}
      <span></span>
    </div>
  </div>
);

const MatrixSidebar = () => (
  <Stack gap={12}>
    <div
      style={{
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        background: 'var(--lw-surface)',
        padding: 14,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 10,
          color: 'var(--lw-ink-4)',
          textTransform: 'uppercase',
        }}
      >
        Overall accuracy
      </span>
      <div style={{ fontSize: 36, fontWeight: 600, letterSpacing: '-0.02em', marginTop: 4 }}>
        87.3%
      </div>
      <div style={{ fontFamily: 'var(--lw-font-mono)', fontSize: 11, color: 'var(--lw-ink-3)' }}>
        ±2.1% · 95% CI
      </div>
    </div>
    <div
      style={{
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        background: 'var(--lw-surface)',
        padding: 14,
      }}
    >
      <Row justify="space-between">
        <span style={{ fontSize: 12 }}>Cohen's κ</span>
        <b style={{ fontFamily: 'var(--lw-font-mono)' }}>0.81</b>
      </Row>
      <Row justify="space-between" style={{ marginTop: 6 }}>
        <span style={{ fontSize: 12 }}>Quantity disagreement</span>
        <b style={{ fontFamily: 'var(--lw-font-mono)' }}>4.1%</b>
      </Row>
      <Row justify="space-between" style={{ marginTop: 6 }}>
        <span style={{ fontSize: 12 }}>Allocation disagreement</span>
        <b style={{ fontFamily: 'var(--lw-font-mono)' }}>8.6%</b>
      </Row>
    </div>
    <div
      style={{
        border: '1px solid var(--lw-line)',
        borderRadius: 6,
        background: 'var(--lw-surface)',
        padding: 14,
        fontFamily: 'var(--lw-font-mono)',
        fontSize: 10,
        color: 'var(--lw-ink-3)',
      }}
    >
      <div
        style={{
          color: 'var(--lw-ink-1)',
          fontFamily: 'var(--lw-font-ui)',
          fontWeight: 600,
          fontSize: 12,
          marginBottom: 8,
        }}
      >
        Methodology
      </div>
      <div>n = 500 stratified random</div>
      <div>seed = 4831</div>
      <div>est. = Olofsson 2014</div>
      <div>computed = 2h ago</div>
    </div>
  </Stack>
);

export const WfReportMatrix = () => (
  <Frame name="14 · Report — confusion matrix" dim="1280×800">
    <div style={{ height: 560 }}>
      <Chrome
        active="Reports"
        title="Africa LC 2020 — accuracy"
        crumbs={['Reports']}
        actions={
          <>
            <Btn>Export CSV</Btn>
            <Btn>Export PDF</Btn>
            <Btn kind="primary">Share</Btn>
          </>
        }
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, height: '100%' }}>
          <MatrixGrid />
          <MatrixSidebar />
        </div>
      </Chrome>
    </div>
  </Frame>
);
