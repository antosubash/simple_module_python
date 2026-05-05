import { Stack } from '@simple-module-py/ui/lacowiki/primitives';
import '@simple-module-py/ui/lacowiki/styles.css';
import { WfSamplingDetail, WfSamplingList } from '@simple-module-py/ui/lacowiki/wf/sampling';
import { WfSamplingGenerator } from '@simple-module-py/ui/lacowiki/wf/sampling-generator';
import { WfSamplingStrategies } from '@simple-module-py/ui/lacowiki/wf/sampling-strategies';

function LacoWikiSampling() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Sampling</div>
        <h1 className="h-display">Sampling — designs, generator, detail.</h1>
        <p className="lede">
          Seven strategies; per-strategy parameter cards swap the generator's right panel.
        </p>
        <Stack gap={32}>
          <WfSamplingList />
          <WfSamplingGenerator />
          <WfSamplingStrategies />
          <WfSamplingDetail />
        </Stack>
      </main>
    </div>
  );
}

LacoWikiSampling.layout = (page: React.ReactNode) => page;

export default LacoWikiSampling;
