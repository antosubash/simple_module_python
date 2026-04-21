"""JS-workspace file templates (package.json, tsconfig.json) for new_module."""

from __future__ import annotations

from _templates_py import ScaffoldContext


def package_json(ctx: ScaffoldContext) -> str:
    return f"""\
        {{
          "name": "@simple-module-py/{ctx.pkg.replace("_", "-")}",
          "version": "0.1.0",
          "private": true,
          "description": "Frontend assets for the {ctx.class_name} module",
          "peerDependencies": {{
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
            "@inertiajs/react": "^2.0.0",
            "@simple-module-py/ui": "*"
          }},
          "devDependencies": {{
            "@simple-module-py/tsconfig": "*"
          }},
          "dependencies": {{}}
        }}
        """


def tsconfig_json(ctx: ScaffoldContext) -> str:
    return f"""\
        {{
          "extends": "@simple-module-py/tsconfig/base.json",
          "compilerOptions": {{
            "baseUrl": ".",
            "paths": {{
              "@/*": ["./{ctx.pkg}/*"],
              "@simple-module-py/ui/*": ["../../packages/ui/src/*"]
            }}
          }},
          "include": ["{ctx.pkg}/**/*.ts", "{ctx.pkg}/**/*.tsx"]
        }}
        """
