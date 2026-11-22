// @vitest-environment node
import { renderToString } from 'react-dom/server';
import { expect, it } from 'vitest';
import { Toaster } from './ui/sonner';

it('renders without a document during SSR', () => {
  expect(typeof document).toBe('undefined');
  expect(() => renderToString(<Toaster />)).not.toThrow();
});
