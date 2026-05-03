import { defineConfig } from "vitepress";

export default defineConfig({
  title: "simple_module_python",
  description:
    "A modular-monolith framework for Python: FastAPI + SQLModel + Inertia + React, with plugin modules that compose at boot.",
  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: true,

  srcExclude: [
    "**/node_modules/**",
    "plans/**",
    "superpowers/**",
    "release-notes/**",
    "README.md",
  ],

  head: [
    ["meta", { name: "theme-color", content: "#3c82f6" }],
    ["meta", { property: "og:title", content: "simple_module_python" }],
    [
      "meta",
      {
        property: "og:description",
        content: "Modular-monolith framework for Python",
      },
    ],
  ],

  themeConfig: {
    nav: [
      { text: "Guide", link: "/guide/introduction", activeMatch: "/guide/" },
      {
        text: "Framework",
        link: "/framework/overview",
        activeMatch: "/framework/",
      },
      {
        text: "Database",
        link: "/database/models",
        activeMatch: "/database/",
      },
      {
        text: "Frontend",
        link: "/frontend/inertia",
        activeMatch: "/frontend/",
      },
      { text: "Testing", link: "/testing/overview", activeMatch: "/testing/" },
      {
        text: "Modules",
        link: "/modules/",
        activeMatch: "/modules/",
      },
      {
        text: "Reference",
        link: "/reference/make-commands",
        activeMatch: "/reference/",
      },
    ],

    socialLinks: [
      {
        icon: "github",
        link: "https://github.com/antosubash/simple_module_python",
      },
    ],

    search: { provider: "local" },

    editLink: {
      pattern:
        "https://github.com/antosubash/simple_module_python/edit/main/docs/:path",
      text: "Edit this page on GitHub",
    },

    footer: {
      message: "Released under the MIT License.",
      copyright: "Copyright © 2026 simple_module_python contributors",
    },

    outline: { level: [2, 3] },

    sidebar: {
      "/guide/": [
        {
          text: "Getting Started",
          collapsed: false,
          items: [
            { text: "Introduction", link: "/guide/introduction" },
            { text: "Installation", link: "/guide/installation" },
            { text: "Quickstart", link: "/guide/quickstart" },
            { text: "Project structure", link: "/guide/project-structure" },
            { text: "Configuration", link: "/guide/configuration" },
            { text: "Your first module", link: "/guide/first-module" },
          ],
        },
        {
          text: "Existing deep dives",
          collapsed: true,
          items: [
            {
              text: "Framework conventions",
              link: "/framework-conventions",
            },
            { text: "Module authoring", link: "/module-authoring" },
            { text: "E2E testing", link: "/e2e-testing" },
            { text: "Release playbook", link: "/release" },
          ],
        },
      ],

      "/framework/": [
        {
          text: "Framework",
          collapsed: false,
          items: [
            { text: "Overview", link: "/framework/overview" },
            { text: "Discovery & entry points", link: "/framework/discovery" },
            { text: "Lifecycle hooks", link: "/framework/lifecycle" },
            { text: "Middleware pipeline", link: "/framework/middleware" },
            { text: "Settings & app.state", link: "/framework/settings" },
            { text: "Permissions", link: "/framework/permissions" },
            { text: "Events", link: "/framework/events" },
            { text: "Internationalization", link: "/framework/i18n" },
          ],
        },
      ],

      "/database/": [
        {
          text: "Database",
          collapsed: false,
          items: [
            { text: "Models with SQLModel", link: "/database/models" },
            { text: "Per-module Base", link: "/database/per-module-base" },
            { text: "Mixins", link: "/database/mixins" },
            { text: "Session lifecycle", link: "/database/sessions" },
            { text: "Migrations", link: "/database/migrations" },
          ],
        },
      ],

      "/frontend/": [
        {
          text: "Frontend",
          collapsed: false,
          items: [
            { text: "Inertia basics", link: "/frontend/inertia" },
            { text: "Pages & discovery", link: "/frontend/pages" },
            { text: "Shared props & layout", link: "/frontend/shared-props" },
          ],
        },
      ],

      "/testing/": [
        {
          text: "Testing",
          collapsed: false,
          items: [
            { text: "Overview", link: "/testing/overview" },
            { text: "Fixtures", link: "/testing/fixtures" },
            { text: "E2E tests", link: "/e2e-testing" },
          ],
        },
      ],

      "/modules/": [
        {
          text: "Bundled modules",
          collapsed: false,
          items: [
            { text: "Overview", link: "/modules/" },
            { text: "auth", link: "/modules/auth" },
            { text: "users", link: "/modules/users" },
            { text: "permissions", link: "/modules/permissions" },
            { text: "settings", link: "/modules/settings" },
            { text: "feature_flags", link: "/modules/feature_flags" },
            { text: "file_storage", link: "/modules/file_storage" },
            { text: "background_tasks", link: "/modules/background_tasks" },
            { text: "dashboard", link: "/modules/dashboard" },
          ],
        },
      ],

      "/reference/": [
        {
          text: "Reference",
          collapsed: false,
          items: [
            { text: "Commands", link: "/reference/make-commands" },
            { text: "Environment variables", link: "/reference/env-vars" },
            {
              text: "Diagnostic codes",
              link: "/reference/diagnostic-codes",
            },
            { text: "Deployment", link: "/reference/deployment" },
          ],
        },
      ],
    },
  },
});
