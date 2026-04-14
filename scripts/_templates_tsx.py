"""Template generators for the three React/Inertia page TSX files."""

from __future__ import annotations

from _templates_py import ScaffoldContext


def browse_tsx(ctx: ScaffoldContext) -> str:
    return f"""\
        type {ctx.singular_class} = {{
          id: number;
          name: string;
          description: string | null;
          is_active: boolean;
        }};

        type Props = {{ {ctx.name}: {ctx.singular_class}[] }};

        export default function Browse({{ {ctx.name} }}: Props) {{
          return (
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h1 className="text-2xl font-semibold">{ctx.class_name}</h1>
                <a
                  href="/{ctx.name}/create"
                  className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
                >
                  New {ctx.singular_class}
                </a>
              </div>
              <ul className="divide-y">
                {{{ctx.name}.map(({ctx.singular}) => (
                  <li key={{{ctx.singular}.id}} className="py-2 flex justify-between">
                    <span>{{{ctx.singular}.name}}</span>
                    <a href={{`/{ctx.name}/${{{ctx.singular}.id}}/edit`}}>Edit</a>
                  </li>
                ))}}
              </ul>
            </div>
          );
        }}
        """


def create_tsx(ctx: ScaffoldContext) -> str:
    return f"""\
        export default function Create() {{
          return (
            <div className="p-6 max-w-xl">
              <h1 className="text-2xl font-semibold mb-4">New {ctx.singular_class}</h1>
              <form method="post" action="/{ctx.name}" className="space-y-3">
                <label className="block">
                  <span className="block text-sm">Name</span>
                  <input name="name" required className="border rounded w-full p-2" />
                </label>
                <label className="block">
                  <span className="block text-sm">Description</span>
                  <textarea name="description" className="border rounded w-full p-2" />
                </label>
                <button
                  type="submit"
                  className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
                >
                  Create
                </button>
              </form>
            </div>
          );
        }}
        """


def edit_tsx(ctx: ScaffoldContext) -> str:
    return f"""\
        type {ctx.singular_class} = {{
          id: number;
          name: string;
          description: string | null;
          is_active: boolean;
        }};

        type Props = {{ {ctx.singular}: {ctx.singular_class} }};

        export default function Edit({{ {ctx.singular} }}: Props) {{
          return (
            <div className="p-6 max-w-xl">
              <h1 className="text-2xl font-semibold mb-4">Edit {ctx.singular_class}</h1>
              <form
                method="post"
                action={{`/{ctx.name}/${{{ctx.singular}.id}}`}}
                className="space-y-3"
              >
                <input type="hidden" name="_method" value="put" />
                <label className="block">
                  <span className="block text-sm">Name</span>
                  <input
                    name="name"
                    defaultValue={{{ctx.singular}.name}}
                    required
                    className="border rounded w-full p-2"
                  />
                </label>
                <label className="block">
                  <span className="block text-sm">Description</span>
                  <textarea
                    name="description"
                    defaultValue={{{ctx.singular}.description ?? ""}}
                    className="border rounded w-full p-2"
                  />
                </label>
                <button
                  type="submit"
                  className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
                >
                  Save
                </button>
              </form>
            </div>
          );
        }}
        """
