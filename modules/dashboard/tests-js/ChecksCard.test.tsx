import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ChecksCard } from '../dashboard/ui/components/doctor/ChecksCard';

configureI18n({ locale: 'en', messages: {} });

test('long finding paths can wrap and Fix keeps a square mobile hit target', () => {
  const file = 'modules/guides/guides/pages/ForgotPassword.tsx';
  const copy = vi.fn();
  render(
    <ChecksCard
      available
      checks={[
        {
          id: 'pages',
          status: 'fail',
          command: 'make gen',
          findings: [
            {
              code: 'SM003',
              module: 'Guides',
              message: 'Missing page',
              file,
              level: 'error',
              suggestion: null,
            },
          ],
        },
      ]}
      onCopyCommand={copy}
    />,
  );
  expect(screen.getByText(file)).toHaveClass('[overflow-wrap:anywhere]');
  const fix = screen.getByRole('button', { name: keys.dashboard.doctor.fix });
  expect(fix).toHaveClass('max-lg:min-h-11', 'max-lg:min-w-11');
  fireEvent.click(fix);
  expect(copy).toHaveBeenCalledWith('make gen');
});
