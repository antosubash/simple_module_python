/**
 * The unsaved-changes guard both page suites stub out.
 *
 * `UserEdit.test.tsx` and its sibling mock `router` as `{ on: () => () => {} }`,
 * so the prompt and its escape hatch were never exercised — and the escape
 * hatch is the load-bearing half: the page's own save is an Inertia visit too,
 * and prompting on it would ask "discard your changes?" while saving them.
 */
import '@testing-library/jest-dom/vitest';
import { render } from '@testing-library/react';
import { createRef } from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

const handlers: Array<() => boolean> = [];
const stopListening = vi.fn();

vi.mock('@inertiajs/react', () => ({
  router: {
    on: (_event: string, handler: () => boolean) => {
      handlers.push(handler);
      return stopListening;
    },
  },
}));

const { useLeaveGuard } = await import('../permissions/pages/components/useLeaveGuard');

const MESSAGE = 'You have unsaved changes.';

function Harness({ dirty, saving }: { dirty: boolean; saving: { current: boolean } }) {
  useLeaveGuard(dirty, MESSAGE, saving);
  return null;
}

function saveFlag(value = false) {
  const ref = createRef<boolean>() as { current: boolean };
  ref.current = value;
  return ref;
}

let confirm: ReturnType<typeof vi.fn>;

beforeEach(() => {
  handlers.length = 0;
  stopListening.mockClear();
  confirm = vi.fn(() => true);
  vi.stubGlobal('confirm', confirm);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('while there is nothing to lose', () => {
  test('it registers nothing at all', () => {
    render(<Harness dirty={false} saving={saveFlag()} />);

    expect(handlers).toHaveLength(0);
  });
});

describe('with unsaved changes', () => {
  test('leaving asks first, and the answer decides', () => {
    render(<Harness dirty={true} saving={saveFlag()} />);

    expect(handlers).toHaveLength(1);
    expect(handlers[0]()).toBe(true);
    expect(confirm).toHaveBeenCalledWith(MESSAGE);

    confirm.mockReturnValue(false);
    expect(handlers[0]()).toBe(false);
  });

  test("the page's own save is not prompted about", () => {
    // The escape hatch. Saving is an Inertia visit like any other, so without
    // this the guard interrupts the very action that resolves it.
    render(<Harness dirty={true} saving={saveFlag(true)} />);

    expect(handlers[0]()).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
  });

  test('it stops listening when the changes are gone', () => {
    const { rerender } = render(<Harness dirty={true} saving={saveFlag()} />);
    expect(stopListening).not.toHaveBeenCalled();

    rerender(<Harness dirty={false} saving={saveFlag()} />);
    expect(stopListening).toHaveBeenCalled();
  });

  test('it stops listening on unmount', () => {
    const { unmount } = render(<Harness dirty={true} saving={saveFlag()} />);
    unmount();

    expect(stopListening).toHaveBeenCalled();
  });
});

describe('the browser-level guard', () => {
  test('a full page unload is cancelled too, since Inertia never sees it', () => {
    render(<Harness dirty={true} saving={saveFlag()} />);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  test('and is not cancelled when there is nothing to lose', () => {
    render(<Harness dirty={false} saving={saveFlag()} />);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});
