import { Stack } from '@simple-module-py/ui/lacowiki/primitives';
import '@simple-module-py/ui/lacowiki/styles.css';
import { WfValidationB } from '@simple-module-py/ui/lacowiki/wf/validation';
import { WfValidationCreate } from '@simple-module-py/ui/lacowiki/wf/validation-create';

function LacoWikiValidation() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Validation</div>
        <h1 className="h-display">Validation — campaign + classify.</h1>
        <p className="lede">
          Single-sample focus: buffer, crosshair guides, classify panel beside the map.
        </p>
        <Stack gap={32}>
          <WfValidationCreate />
          <WfValidationB />
        </Stack>
      </main>
    </div>
  );
}

LacoWikiValidation.layout = (page: React.ReactNode) => page;

export default LacoWikiValidation;
