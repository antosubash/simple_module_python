import { usePage } from '@inertiajs/react';
import { PublicLayout } from '@ui/layouts/PublicLayout';

interface Props {
    isAuthenticated: boolean;
}

function Landing() {
    const { isAuthenticated } = usePage<{ props: Props }>().props as unknown as Props;

    return (
        <>
            {/* Hero */}
            <section className="max-w-5xl mx-auto px-8 pt-24 pb-20 text-center">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-500/10 border border-primary-500/20 text-primary-300 text-sm font-medium mb-8">
                    <span className="w-2 h-2 rounded-full bg-primary-400 animate-pulse" />
                    Built with FastAPI + Inertia.js + React
                </div>

                <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tight leading-tight">
                    Modular Monolith
                    <br />
                    <span className="bg-gradient-to-r from-primary-400 to-primary-200 bg-clip-text text-transparent">
                        Framework for Python
                    </span>
                </h1>

                <p className="mt-6 text-lg text-gray-400 max-w-2xl mx-auto leading-relaxed">
                    Build scalable applications with independent modules, each with its own
                    database schema, API endpoints, and React pages — all in one deployable unit.
                </p>

                <div className="mt-10 flex items-center justify-center gap-4">
                    <a href="/auth/login" className="btn-primary px-6 py-3 text-base">
                        {isAuthenticated ? 'Open Dashboard' : 'Get Started'}
                    </a>
                    <a
                        href="https://github.com"
                        className="btn-secondary px-6 py-3 text-base border-gray-600 text-gray-300 hover:text-white hover:border-gray-500"
                    >
                        Documentation
                    </a>
                </div>
            </section>

            {/* Features */}
            <section className="max-w-6xl mx-auto px-8 pb-24">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
                            </svg>
                        }
                        title="Module System"
                        description="Each module is a self-contained package with its own models, services, API endpoints, and React pages. Discovered automatically via Python entry_points."
                    />
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z" />
                            </svg>
                        }
                        title="Keycloak Auth"
                        description="Cookie-based OIDC authentication with Keycloak. Server-side sessions, permission-based access control, and role-filtered menus."
                    />
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
                            </svg>
                        }
                        title="Schema Isolation"
                        description="Each module gets its own database schema on PostgreSQL or table prefix on SQLite. Full audit trails, soft deletes, and multi-tenancy built in."
                    />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
                            </svg>
                        }
                        title="Inertia.js + React"
                        description="Server-driven SPA — FastAPI renders props, React renders the UI. No separate API client, no state duplication, full-stack type safety."
                    />
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
                            </svg>
                        }
                        title="Diagnostics"
                        description="Built-in module validator catches orphan pages, phantom renders, unguarded endpoints, and circular dependencies at startup."
                    />
                    <FeatureCard
                        icon={
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
                            </svg>
                        }
                        title="Developer Tools"
                        description="uv workspaces, Tailwind CSS 4, Vite HMR, auto-discovered pages, 97 tests in 0.4s, and a CLI scaffolding tool."
                    />
                </div>
            </section>
        </>
    );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
    return (
        <div className="rounded-xl border border-gray-700/50 bg-gray-800/50 p-6 backdrop-blur-sm hover:border-gray-600/50 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-primary-500/10 flex items-center justify-center text-primary-400 mb-4">
                {icon}
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
            <p className="text-sm text-gray-400 leading-relaxed">{description}</p>
        </div>
    );
}

Landing.layout = (page: React.ReactNode) => <PublicLayout>{page}</PublicLayout>;
export default Landing;
