import { Head, useForm } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';

export default function Create() {
  const { t } = useT();
  const form = useForm({ name: '', description: '' });
  return (
    <PageShell title={t(keys.{{PACKAGE_NAME}}.create.title)}>
      <Head title={t(keys.{{PACKAGE_NAME}}.create.title)} />
      <form
        className="max-w-xl space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          form.post('/{{MODULE_SLUG}}/');
        }}
      >
        <label className="block">
          <span className="block text-sm">{t(keys.{{PACKAGE_NAME}}.form.name_label)}</span>
          <input
            required
            value={form.data.name}
            onChange={(e) => form.setData('name', e.target.value)}
            className="w-full rounded border p-2"
          />
        </label>
        <label className="block">
          <span className="block text-sm">{t(keys.{{PACKAGE_NAME}}.form.description_label)}</span>
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
          {t(keys.{{PACKAGE_NAME}}.create.submit_button)}
        </button>
      </form>
    </PageShell>
  );
}
