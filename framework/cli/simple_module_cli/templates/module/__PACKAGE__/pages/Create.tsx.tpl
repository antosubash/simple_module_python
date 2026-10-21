import { Head, useForm } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

export default function Create() {
  const form = useForm({ name: '', description: '' });
  return (
    <PageShell title="New {{SINGULAR_CLASS}}">
      <Head title="New {{SINGULAR_CLASS}}" />
      <form
        className="max-w-xl space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          form.post('/{{MODULE_SLUG}}/');
        }}
      >
        <label className="block">
          <span className="block text-sm">Name</span>
          <input
            required
            value={form.data.name}
            onChange={(e) => form.setData('name', e.target.value)}
            className="w-full rounded border p-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm">Description</span>
          <textarea
            value={form.data.description}
            onChange={(e) => form.setData('description', e.target.value)}
            className="w-full rounded border p-2"
          />
        </label>
        <button
          type="submit"
          disabled={form.processing}
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
          Create
        </button>
      </form>
    </PageShell>
  );
}
