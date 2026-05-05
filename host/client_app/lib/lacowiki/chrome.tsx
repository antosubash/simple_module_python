import type { CSSProperties, ReactNode } from 'react';
import { Fragment } from 'react';

export const ProductSidebar = ({ active = 'Datasets' }: { active?: string }) => {
  const items = [
    { name: 'Dashboard', mod: '' },
    { name: 'Datasets', mod: 'datasets' },
    { name: 'Legends', mod: 'legends' },
    { name: 'Sampling', mod: 'sampling' },
    { name: 'Validation', mod: 'validation' },
    { name: 'Reports', mod: 'reports' },
    { name: 'Notifications', mod: 'notif' },
  ];
  return (
    <div
      style={{
        width: 200,
        padding: '16px 12px',
        borderRight: '1px solid var(--lw-line-soft)',
        background: 'var(--lw-bg-alt)',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 8px 12px',
          borderBottom: '1px solid var(--lw-line-soft)',
          marginBottom: 8,
        }}
      >
        <div
          style={{
            width: 18,
            height: 18,
            background: 'var(--lw-ink-1)',
            borderRadius: 4,
            display: 'grid',
            placeItems: 'center',
            color: 'white',
            fontSize: 10,
            fontWeight: 700,
            fontFamily: 'var(--lw-font-mono)',
          }}
        >
          L
        </div>
        <span style={{ fontSize: 12, fontWeight: 600 }}>LacoWiki</span>
      </div>
      {items.map((it) => (
        <div
          key={it.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 8px',
            borderRadius: 4,
            fontSize: 12,
            background: it.name === active ? 'var(--lw-surface)' : 'transparent',
            color: it.name === active ? 'var(--lw-ink-1)' : 'var(--lw-ink-3)',
            fontWeight: it.name === active ? 600 : 500,
            border: it.name === active ? '1px solid var(--lw-line)' : '1px solid transparent',
          }}
        >
          {it.mod && <span className={`mod-dot mod-${it.mod}`} />}
          {!it.mod && (
            <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--lw-ink-5)' }} />
          )}
          {it.name}
        </div>
      ))}
      <div
        style={{
          marginTop: 'auto',
          paddingTop: 12,
          borderTop: '1px solid var(--lw-line-soft)',
          fontFamily: 'var(--lw-font-mono)',
          fontSize: 10,
          color: 'var(--lw-ink-4)',
        }}
      >
        v2.0 · python · alpha
      </div>
    </div>
  );
};

export const ProductTopbar = ({
  title,
  crumbs = [],
  actions,
}: {
  title: string;
  crumbs?: string[];
  actions?: ReactNode;
}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '10px 16px',
      borderBottom: '1px solid var(--lw-line-soft)',
      background: 'var(--lw-surface)',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
      {crumbs.map((c, i) => (
        <Fragment key={i}>
          <span style={{ color: 'var(--lw-ink-4)' }}>{c}</span>
          {i < crumbs.length - 1 && <span style={{ color: 'var(--lw-ink-5)' }}>/</span>}
        </Fragment>
      ))}
      {crumbs.length > 0 && <span style={{ color: 'var(--lw-ink-5)' }}>/</span>}
      <span style={{ fontWeight: 600 }}>{title}</span>
    </div>
    <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
      {actions}
      <div
        style={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: 'var(--lw-bg-sunk)',
          border: '1px solid var(--lw-line)',
        }}
      />
    </div>
  </div>
);

export const Chrome = ({
  active,
  title,
  crumbs,
  actions,
  children,
  contentStyle,
}: {
  active?: string;
  title: string;
  crumbs?: string[];
  actions?: ReactNode;
  children?: ReactNode;
  contentStyle?: CSSProperties;
}) => (
  <div style={{ display: 'flex', height: '100%' }}>
    <ProductSidebar active={active} />
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <ProductTopbar title={title} crumbs={crumbs} actions={actions} />
      <div style={{ flex: 1, padding: 16, overflow: 'hidden', ...contentStyle }}>{children}</div>
    </div>
  </div>
);
