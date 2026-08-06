import { Head } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

export default function Index() {
  return (
    <PageShell title="{{MODULE_NAME}}" description="Scaffolded by smpy create-module — replace this page.">
      <Head title="{{MODULE_NAME}}" />
      <p className="text-sm text-muted-foreground">
        Edit <code>pages/Index.tsx</code> to build the {{MODULE_NAME}} UI.
      </p>
    </PageShell>
  );
}
