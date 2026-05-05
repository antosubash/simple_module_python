import { Stack } from '@simple-module-py/ui/lacowiki/primitives';
import '@simple-module-py/ui/lacowiki/styles.css';
import { WfReportMatrix } from '@simple-module-py/ui/lacowiki/wf/report-matrix';
import { WfReportsList } from '@simple-module-py/ui/lacowiki/wf/reports';

function LacoWikiReports() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Reports</div>
        <h1 className="h-display">Reports — list, confusion matrix.</h1>
        <p className="lede">Accuracy reports per dataset; confusion matrix with UA/PA per class.</p>
        <Stack gap={32}>
          <WfReportsList />
          <WfReportMatrix />
        </Stack>
      </main>
    </div>
  );
}

LacoWikiReports.layout = (page: React.ReactNode) => page;

export default LacoWikiReports;
