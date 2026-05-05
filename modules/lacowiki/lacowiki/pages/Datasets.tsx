import { Stack } from '@simple-module-py/ui/lacowiki/primitives';
import '@simple-module-py/ui/lacowiki/styles.css';
import { WfDatasetDetail } from '@simple-module-py/ui/lacowiki/wf/dataset-detail';
import { WfDatasetsList, WfDatasetUpload } from '@simple-module-py/ui/lacowiki/wf/datasets';

function LacoWikiDatasets() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Datasets</div>
        <h1 className="h-display">Datasets — list, upload, detail.</h1>
        <p className="lede">Per-dataset surface: list view, upload flow, detail with sharing.</p>
        <Stack gap={32}>
          <WfDatasetsList />
          <WfDatasetUpload />
          <WfDatasetDetail />
        </Stack>
      </main>
    </div>
  );
}

LacoWikiDatasets.layout = (page: React.ReactNode) => page;

export default LacoWikiDatasets;
