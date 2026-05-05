import { Stack } from '@simple-module-py/ui/lacowiki/primitives';
import '@simple-module-py/ui/lacowiki/styles.css';
import { WfLegendBuilder, WfLegendsList } from '@simple-module-py/ui/lacowiki/wf/legends';

function LacoWikiLegends() {
  return (
    <div className="lw-app" data-density="normal">
      <main>
        <div className="eyebrow">Legends</div>
        <h1 className="h-display">Legends — list, builder.</h1>
        <p className="lede">Templates and custom legends; class editor with color and code.</p>
        <Stack gap={32}>
          <WfLegendsList />
          <WfLegendBuilder />
        </Stack>
      </main>
    </div>
  );
}

LacoWikiLegends.layout = (page: React.ReactNode) => page;

export default LacoWikiLegends;
