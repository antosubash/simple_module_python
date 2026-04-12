import React, { useState } from 'react';
import { usePage, Link } from '@inertiajs/react';

interface MenuItem {
    label: string;
    url: string;
    icon: string;
}

interface SharedProps {
    auth: {
        user: { name: string; email: string; roles: string[] } | null;
        isAuthenticated: boolean;
    };
    menus: {
        sidebar: MenuItem[];
        adminSidebar: MenuItem[];
        navbar: MenuItem[];
        userDropdown: MenuItem[];
    };
}

export function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
    const { auth, menus } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
    const currentUrl = usePage().url;
    const [sidebarOpen, setSidebarOpen] = useState(false);

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Mobile header */}
            <div className="sticky top-0 z-40 flex h-14 items-center gap-3 bg-sidebar px-4 lg:hidden">
                <button
                    onClick={() => setSidebarOpen(true)}
                    className="p-1.5 rounded-lg text-gray-300 hover:text-white hover:bg-sidebar-hover transition-colors"
                >
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                    </svg>
                </button>
                <Link href="/dashboard" className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-md bg-primary-500 flex items-center justify-center">
                        <span className="text-white font-bold text-xs">SM</span>
                    </div>
                    <span className="text-base font-semibold text-white">SimpleModule</span>
                </Link>
            </div>

            {/* Mobile sidebar backdrop */}
            {sidebarOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/50 lg:hidden"
                    onClick={() => setSidebarOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-sidebar flex flex-col border-r border-gray-800 transition-transform duration-200 ease-in-out lg:translate-x-0 lg:z-30 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
                {/* Brand */}
                <div className="h-14 lg:h-16 flex items-center justify-between px-4 lg:px-6 border-b border-white/10">
                    <Link href="/dashboard" className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-lg bg-primary-500 flex items-center justify-center">
                            <span className="text-white font-bold text-sm">SM</span>
                        </div>
                        <span className="text-lg font-semibold text-white">SimpleModule</span>
                    </Link>
                    {/* Close button - mobile only */}
                    <button
                        onClick={() => setSidebarOpen(false)}
                        className="lg:hidden p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-sidebar-hover transition-colors"
                    >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Navigation */}
                <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
                    {menus?.sidebar?.map((item) => {
                        const isActive = currentUrl.startsWith(item.url);
                        return (
                            <Link
                                key={item.url}
                                href={item.url}
                                onClick={() => setSidebarOpen(false)}
                                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                                    isActive
                                        ? 'bg-primary-600/20 text-white'
                                        : 'text-sidebar-text hover:bg-sidebar-hover hover:text-white'
                                }`}
                            >
                                <NavIcon name={item.icon} />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>

                {/* User footer */}
                {auth?.user && (
                    <div className="px-3 py-4 border-t border-white/10">
                        <div className="flex items-center gap-3 px-3 py-2">
                            <div className="w-8 h-8 rounded-full bg-primary-700 flex items-center justify-center">
                                <span className="text-xs font-medium text-white">
                                    {auth.user.name?.charAt(0)?.toUpperCase() || 'U'}
                                </span>
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-white truncate">{auth.user.name}</p>
                                <p className="text-xs text-sidebar-text-muted truncate">{auth.user.email}</p>
                            </div>
                        </div>
                        {menus?.userDropdown?.map((item) => (
                            <Link
                                key={item.url}
                                href={item.url}
                                onClick={() => setSidebarOpen(false)}
                                className="flex items-center gap-3 px-3 py-2 mt-1 rounded-lg text-sm text-sidebar-text-muted hover:text-white hover:bg-sidebar-hover transition-colors"
                            >
                                <NavIcon name={item.icon} />
                                {item.label}
                            </Link>
                        ))}
                    </div>
                )}
            </aside>

            {/* Main content */}
            <main className="min-h-screen lg:ml-64">
                {children}
            </main>
        </div>
    );
}

function NavIcon({ name }: { name: string }) {
    const icons: Record<string, React.ReactNode> = {
        home: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 12 8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
        ),
        package: (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9" />
            </svg>
        ),
        'log-out': (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
            </svg>
        ),
    };

    return <>{icons[name] || <span className="w-5 h-5" />}</>;
}
