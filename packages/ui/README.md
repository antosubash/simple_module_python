# @simple-module-py/ui

shadcn-derived React UI components and layouts for [simple_module](https://github.com/antosubash/simple_module_python) apps. Buttons, Cards, Forms, Dialogs, sidebar Layouts — the toolbox every module page pulls from.

## Install

```bash
npm install @simple-module-py/ui
```

Peer-depends on React 19. Assumes Tailwind CSS 4 is configured in the consuming app.

## What it provides

- Core primitives: `Button`, `Input`, `Label`, `Textarea`, `Select`, `Switch`, `Checkbox`.
- Composite components: `Card`, `Dialog`, `Sheet`, `Popover`, `Tooltip`, `Toaster`, `Form` (react-hook-form bindings).
- Layouts: `AppLayout` (sidebar + content), `AuthLayout` (centred form).
- Small set of icons from `lucide-react`, re-exported.

All components ship as `.ts` / `.tsx` source (no bundling step) — any modern bundler (Vite, Next, etc.) handles them transparently.

## Usage

```tsx
import { Button, Card, CardHeader, CardContent, CardTitle } from "@simple-module-py/ui";

export default function ProductCard({ product }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{product.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <Button onClick={...}>Add to cart</Button>
      </CardContent>
    </Card>
  );
}
```

### Owning the source (shadcn-style)

If you want to edit a component's source directly:

```bash
cp -r node_modules/@simple-module-py/ui/src packages/ui-local
# add to your tsconfig paths and package.json, then import from @/ui-local
```

At that point you've forked the library — `npm update` will no longer bring changes in.

## Depends on

- `@simple-module-py/i18n`
- Peer: `react ^19.0.0`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
