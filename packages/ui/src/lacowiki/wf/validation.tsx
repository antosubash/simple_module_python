import { MapPh } from '../primitives';
import { ActiveSample, ClassifyPanel, ValidationCommon } from './validation-shared';

const BASEMAP_TABS = ['Sentinel-2', 'Bing', 'PlanetScope', 'Sentinel-1'];

export const WfValidationB = () => (
  <ValidationCommon label="12 · Validation — classify">
    <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 320px' }}>
      <div style={{ position: 'relative' }}>
        <MapPh h={490}>
          <ActiveSample kind="polygon" />
        </MapPh>
        <div style={{ position: 'absolute', bottom: 12, left: 12, display: 'flex', gap: 6 }}>
          {BASEMAP_TABS.map((b, i) => (
            <span
              key={b}
              style={{
                padding: '4px 10px',
                background: i === 0 ? 'var(--lw-ink-1)' : 'var(--lw-surface)',
                color: i === 0 ? 'white' : 'var(--lw-ink-2)',
                border: '1px solid var(--lw-line)',
                borderRadius: 3,
                fontSize: 11,
              }}
            >
              {b}
            </span>
          ))}
        </div>
      </div>
      <div
        style={{
          borderLeft: '1px solid var(--lw-line-soft)',
          background: 'var(--lw-bg-alt)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <ClassifyPanel />
        <div
          style={{
            marginTop: 'auto',
            padding: 12,
            borderTop: '1px solid var(--lw-line-soft)',
            fontFamily: 'var(--lw-font-mono)',
            fontSize: 10,
            color: 'var(--lw-ink-4)',
          }}
        >
          47 / 500 · 9.4%
        </div>
      </div>
    </div>
  </ValidationCommon>
);
