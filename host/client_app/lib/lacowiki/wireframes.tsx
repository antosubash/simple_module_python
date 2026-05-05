import type { ReactNode } from 'react';

import { SectionHead } from './primitives';
import { WfAccount } from './wf/account';
import { WfDashboard } from './wf/dashboard';
import { WfDatasetDetail, WfDatasetsList, WfDatasetUpload } from './wf/datasets';
import { WfLegendBuilder, WfLegendsList } from './wf/legends';
import { WfLanding, WfLogin } from './wf/marketing';
import { WfReportMatrix, WfReportsList } from './wf/reports';
import { WfSamplingDetail, WfSamplingList } from './wf/sampling';
import { WfSamplingGenerator } from './wf/sampling-generator';
import { WfSamplingStrategies } from './wf/sampling-strategies';
import { WfValidationB } from './wf/validation';
import { WfValidationCreate } from './wf/validation-create';

type Section = { id: string; label: string; items: ReactNode[] };

const SECTIONS: Section[] = [
  { id: 'marketing', label: 'Marketing & auth', items: [<WfLanding />, <WfLogin />] },
  { id: 'dashboard', label: 'Dashboard', items: [<WfDashboard />] },
  {
    id: 'datasets',
    label: 'Datasets',
    items: [<WfDatasetsList />, <WfDatasetUpload />, <WfDatasetDetail />],
  },
  { id: 'legends', label: 'Legends', items: [<WfLegendsList />, <WfLegendBuilder />] },
  {
    id: 'sampling',
    label: 'Sampling',
    items: [
      <WfSamplingList />,
      <WfSamplingGenerator />,
      <WfSamplingStrategies />,
      <WfSamplingDetail />,
    ],
  },
  { id: 'validation', label: 'Validation', items: [<WfValidationCreate />, <WfValidationB />] },
  { id: 'reports', label: 'Reports', items: [<WfReportsList />, <WfReportMatrix />] },
  { id: 'account', label: 'Account', items: [<WfAccount />] },
];

const sectionPad = (i: number) => (i + 1 < 10 ? `0${i + 1}` : String(i + 1));

const gridClassFor = (s: Section) => {
  if (s.id === 'validation') return 'wf-grid-2';
  if (s.items.length >= 2) return 'wf-grid-2';
  return '';
};

export const Wireframes = () => (
  <div>
    <div className="eyebrow">02 — Wireframes</div>
    <h1 className="h-display">Screens.</h1>
    <p className="lede">
      Mid-fidelity, one accent color, tabular numerals. Validation focuses on one sample at a time —
      a single classify panel beside the map.
    </p>

    <div className="wf-toc">
      {SECTIONS.map((s) => (
        <a key={s.id} href={`#${s.id}`}>
          ↳ {s.label}
        </a>
      ))}
    </div>

    {SECTIONS.map((s, i) => (
      <section key={s.id} id={s.id} className="wf-section">
        <SectionHead id={s.id} label={`${sectionPad(i)} · module`}>
          {s.label}
        </SectionHead>
        <div className={gridClassFor(s)}>
          {s.items.map((Item, idx) => (
            <div key={idx}>{Item}</div>
          ))}
        </div>
      </section>
    ))}
  </div>
);
