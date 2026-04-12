import React from 'react';
import { usePage, Link } from '@inertiajs/react';

interface SharedProps {
    auth: {
        user: { name: string; email: string; roles: string[] } | null;
        isAuthenticated: boolean;
    };
}

export function PublicLayout({ children }: { children: React.ReactNode }) {
    const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;

    return (
        <div className="min-h-screen flex flex-col bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white">
            {/* Nav */}
            <nav className="flex items-center justify-between px-8 py-5">
                <Link href="/" className="flex items-center gap-2">
                    <div className="w-9 h-9 rounded-lg bg-primary-500 flex items-center justify-center">
                        <span className="text-white font-bold text-sm">SM</span>
                    </div>
                    <span className="text-xl font-bold">SimpleModule</span>
                </Link>
                <div className="flex items-center gap-4">
                    {auth?.isAuthenticated ? (
                        <a href="/dashboard" className="btn-primary">
                            Go to Dashboard
                        </a>
                    ) : (
                        <>
                            <a href="/auth/login" className="btn-ghost text-gray-300 hover:text-white">
                                Sign In
                            </a>
                            <a href="/auth/login" className="btn-primary">
                                Get Started
                            </a>
                        </>
                    )}
                </div>
            </nav>

            {/* Content */}
            <main className="flex-1">
                {children}
            </main>

            {/* Footer */}
            <footer className="border-t border-gray-800 py-8 text-center text-sm text-gray-500">
                SimpleModule Framework — Built with FastAPI, Inertia.js, React, and Tailwind CSS
            </footer>
        </div>
    );
}
