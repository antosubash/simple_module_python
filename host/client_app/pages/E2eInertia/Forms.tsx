// i18n-exempt-file: e2e fixture page, never shown to users
import { useForm } from '@inertiajs/react';
import { buttonClass, E2ePage } from './components/E2ePage';

function DemoForm({ bag }: { bag: 'default' | 'second' }) {
  const form = useForm({ name: '', email: '' });
  return (
    <form
      noValidate
      data-testid={`e2e-form-${bag}`}
      className="space-y-2 rounded border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        form.post(`/__e2e/inertia/forms/${bag}`, {
          errorBag: bag === 'second' ? 'second' : undefined,
        });
      }}
    >
      <h2>{bag === 'default' ? 'Default form' : 'Second form'}</h2>
      {(['name', 'email'] as const).map((field) => (
        <div key={field}>
          <label htmlFor={`${bag}-${field}`}>{field === 'name' ? 'Name' : 'Email'}</label>
          <input
            id={`${bag}-${field}`}
            data-testid={`e2e-${bag}-${field}`}
            className="block rounded border p-2"
            type={field === 'email' ? 'email' : 'text'}
            value={form.data[field]}
            aria-invalid={!!form.errors[field]}
            aria-describedby={`${bag}-${field}-error`}
            onChange={(event) => form.setData(field, event.target.value)}
          />
          <p id={`${bag}-${field}-error`} role="alert" data-testid={`e2e-${bag}-${field}-error`}>
            {form.errors[field]}
          </p>
        </div>
      ))}
      <button
        type="submit"
        className={buttonClass}
        disabled={form.processing}
        data-testid={`e2e-${bag}-submit`}
      >
        Submit
      </button>
      {bag === 'default' && (
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-validated-submit"
          onClick={() => form.post('/__e2e/inertia/forms/validated')}
        >
          Submit via FastAPI validation
        </button>
      )}
    </form>
  );
}

export default function Forms({ success }: { success: string }) {
  return (
    <E2ePage title="Forms and error bags">
      <p data-testid="e2e-form-success">{success ? `Saved ${success} form` : ''}</p>
      <DemoForm bag="default" />
      <DemoForm bag="second" />
    </E2ePage>
  );
}
