import type { CSSProperties, ReactNode } from 'react';

type LineWidth = 'short' | 'med' | 'long' | 'title' | 'head';
type PillTone = 'default' | 'accent' | 'ok' | 'warn';
type BtnKind = 'default' | 'primary' | 'accent';

export const Frame = ({
  name,
  dim,
  children,
  padded = false,
  style,
}: {
  name: string;
  dim: string;
  children?: ReactNode;
  padded?: boolean;
  style?: CSSProperties;
}) => (
  <div className="frame" style={style}>
    <div className="frame-cap">
      <span className="name">{name}</span>
      <span className="dim">{dim}</span>
    </div>
    <div className={padded ? 'frame-body padded' : 'frame-body'}>{children}</div>
  </div>
);

export const Line = ({
  w = 'long',
  dark = false,
  style,
}: {
  w?: LineWidth;
  dark?: boolean;
  style?: CSSProperties;
}) => <div className={`wf-line ${w} ${dark ? 'dark' : ''}`} style={style} />;

export const Stack = ({
  gap = 8,
  children,
  style,
}: {
  gap?: number;
  children?: ReactNode;
  style?: CSSProperties;
}) => <div style={{ display: 'flex', flexDirection: 'column', gap, ...style }}>{children}</div>;

export const Row = ({
  gap = 8,
  align = 'center',
  justify = 'flex-start',
  children,
  style,
}: {
  gap?: number;
  align?: CSSProperties['alignItems'];
  justify?: CSSProperties['justifyContent'];
  children?: ReactNode;
  style?: CSSProperties;
}) => (
  <div style={{ display: 'flex', alignItems: align, justifyContent: justify, gap, ...style }}>
    {children}
  </div>
);

export const Pill = ({ children, tone = 'default' }: { children?: ReactNode; tone?: PillTone }) => (
  <span className={`wf-pill ${tone === 'default' ? '' : tone}`}>{children}</span>
);

export const Btn = ({
  children,
  kind = 'default',
  icon,
}: {
  children?: ReactNode;
  kind?: BtnKind;
  icon?: string;
}) => (
  <span className={`wf-btn ${kind === 'default' ? '' : kind}`}>
    {icon ? <span style={{ fontSize: 10 }}>{icon}</span> : null}
    {children}
  </span>
);

export const Placeholder = ({
  label,
  h = 100,
  style,
}: {
  label: string;
  h?: number;
  style?: CSSProperties;
}) => (
  <div className="placeholder" style={{ height: h, ...style }}>
    {label}
  </div>
);

export const MapPh = ({
  h = 280,
  style,
  children,
}: {
  h?: number;
  style?: CSSProperties;
  children?: ReactNode;
}) => (
  <div className="map-ph" style={{ height: h, ...style }}>
    {children}
  </div>
);

export const SectionHead = ({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children?: ReactNode;
}) => (
  <div className="wf-section-head">
    <div>
      <div
        style={{
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 10,
          color: 'var(--lw-ink-4)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          marginBottom: 6,
        }}
      >
        {label}
      </div>
      <h2 id={id}>{children}</h2>
    </div>
    <div className="id">#{id}</div>
  </div>
);
