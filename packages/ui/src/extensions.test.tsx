import { usePage } from '@inertiajs/react';
import { cleanup, render, screen } from '@testing-library/react';
import { lazy } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { NavIcon } from './components/NavIcon';
import { ExtensionRegistry, ExtensionsProvider, Slot, slots } from './extensions';
import { LayoutComponentsProvider, useLayoutComponents } from './layouts/LayoutComponentsProvider';

vi.mock('@inertiajs/react', async (original) => ({
  ...(await original<object>()),
  usePage: vi.fn(() => ({ props: { auth: { permissions: [] } } })),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('orders contributions by order and keeps registration order for ties', () => {
  const registry = new ExtensionRegistry();
  for (const [id, order] of [
    ['last', 20],
    ['first', -1],
    ['tie', -1],
    ['default', undefined],
  ] as const) {
    registry.registerSlot(slots.usersEditPanels, {
      id,
      order,
      component: ({ userId }) => <p>{`${id}:${userId}`}</p>,
    });
  }
  render(
    <ExtensionsProvider registry={registry}>
      <Slot name={slots.usersEditPanels} props={{ userId: '42' }} />
    </ExtensionsProvider>,
  );
  expect(screen.getAllByRole('paragraph').map((p) => p.textContent)).toEqual([
    'first:42',
    'tie:42',
    'default:42',
    'last:42',
  ]);
});

it('hides restricted contributions without loading their chunks and rechecks navigation permissions', async () => {
  const registry = new ExtensionRegistry();
  const load = vi.fn(async () => ({ default: () => <p>private panel</p> }));
  registry.registerSlot(slots.usersEditPanels, {
    id: 'private',
    permission: 'profile.read',
    component: lazy(load),
    fallback: <p>loading panel</p>,
  });
  const tree = (
    <ExtensionsProvider registry={registry}>
      <Slot name={slots.usersEditPanels} props={{ userId: '42' }} />
    </ExtensionsProvider>
  );
  vi.mocked(usePage).mockReturnValue({ props: { auth: { permissions: [] } } } as ReturnType<
    typeof usePage
  >);
  const view = render(tree);
  expect(view.container).toBeEmptyDOMElement();
  expect(load).not.toHaveBeenCalled();
  vi.mocked(usePage).mockReturnValue({
    props: { auth: { permissions: ['profile.read'] } },
  } as ReturnType<typeof usePage>);
  view.rerender(
    <ExtensionsProvider registry={registry}>
      <Slot name={slots.usersEditPanels} props={{ userId: '43' }} />
    </ExtensionsProvider>,
  );
  expect(screen.getByText('loading panel')).toBeInTheDocument();
  expect(await screen.findByText('private panel')).toBeInTheDocument();
  vi.mocked(usePage).mockReturnValue({ props: { auth: { permissions: [] } } } as ReturnType<
    typeof usePage
  >);
  view.rerender(
    <ExtensionsProvider registry={registry}>
      <Slot name={slots.usersEditPanels} props={{ userId: '44' }} />
    </ExtensionsProvider>,
  );
  expect(screen.queryByText('private panel')).not.toBeInTheDocument();
});

it('renders an unregistered slot without adding markup', () => {
  const view = render(
    <ExtensionsProvider registry={new ExtensionRegistry()}>
      <Slot
        name={slots.tenantsSettingsSections}
        props={{ tenant: { id: 't', name: 'T', slug: 't' } }}
      />
    </ExtensionsProvider>,
  );
  expect(view.container).toBeEmptyDOMElement();
});

it('runs each entry only once per registry', () => {
  const registry = new ExtensionRegistry();
  const register = vi.fn();
  registry.runOnce('module', register);
  registry.runOnce('module', register);
  expect(register).toHaveBeenCalledTimes(1);
  new ExtensionRegistry().runOnce('module', register);
  expect(register).toHaveBeenCalledTimes(2);
});

it('rejects duplicate contribution ids instead of rendering duplicate React keys', () => {
  const registry = new ExtensionRegistry();
  const entry = { id: 'panel', component: () => null };
  registry.registerSlot(slots.usersEditPanels, entry);
  expect(() => registry.registerSlot(slots.usersEditPanels, entry)).toThrow(/panel/);
});

function Chrome() {
  const { Topbar } = useLayoutComponents();
  return <Topbar navItems={[]} accountItems={[]} currentUrl="/" activeMenuItem={null} />;
}

it('uses the default topbar and replaces it through the same registry', () => {
  const registry = new ExtensionRegistry();
  const view = render(
    <ExtensionsProvider registry={registry}>
      <LayoutComponentsProvider>
        <Chrome />
      </LayoutComponentsProvider>
    </ExtensionsProvider>,
  );
  expect(view.container.querySelector('header')).toBeInTheDocument();
  view.unmount();
  registry.registerLayout('Topbar', () => <header>custom chrome</header>);
  render(
    <ExtensionsProvider registry={registry}>
      <LayoutComponentsProvider>
        <Chrome />
      </LayoutComponentsProvider>
    </ExtensionsProvider>,
  );
  expect(screen.getByText('custom chrome')).toBeInTheDocument();
});

it('adds module icons, preserves built-ins and warns for unknown names', () => {
  const registry = new ExtensionRegistry();
  registry.registerIcon('custom', (props) => (
    <svg {...props}>
      <title>custom icon</title>
    </svg>
  ));
  registry.registerIcon('home', () => <span>replaced home</span>);
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const view = render(
    <ExtensionsProvider registry={registry}>
      <NavIcon name="custom" className="size-6" />
      <NavIcon name="home" />
      <NavIcon name="unknown" />
      <NavIcon name="toString" />
    </ExtensionsProvider>,
  );
  expect(screen.getByTitle('custom icon').parentElement).toHaveClass('size-6');
  expect(view.container.querySelectorAll('svg')).toHaveLength(2);
  expect(screen.queryByText('replaced home')).not.toBeInTheDocument();
  expect(view.container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(2);
  expect(warn).toHaveBeenCalledWith(expect.stringContaining('unknown'));
});
