import React, { useState } from 'react';
import { usePage, Link } from '@inertiajs/react';

interface SharedProps {
    auth: {
        user: { name: string; email: string; roles: string[] } | null;
        isAuthenticated: boolean;
    };
}

export function PublicLayout({ children }: { children: React.ReactNode }) {
    const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <div className="min-h-screen flex flex-col bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white">
            {/* Nav */}
            <nav className="px-4 py-4 sm:px-8 sm:py-5">
                <div className="flex items-center justify-between">
                    <Link href="/" className="flex items-center gap-2">
                        <div className="w-9 h-9 rounded-lg bg-primary-500 flex items-center justify-center">
                            <span className="text-white font-bold text-sm">SM</span>
                        </div>
                        <span className="text-xl font-bold">SimpleModule</span>
                    </Link>

                    {/* Desktop nav */}
                    <div className="hidden sm:flex items-center gap-4">
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

                    {/* Mobile hamburger */}
                    <button
                        onClick={() => setMenuOpen(!menuOpen)}
                        className="sm:hidden p-2 rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors"
                    >
                        {menuOpen ? (
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                            </svg>
                        ) : (
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                            </svg>
                        )}
                    </button>
                </div>

                {/* Mobile menu */}
                {menuOpen && (
                    <div className="sm:hidden mt-4 pt-4 border-t border-white/10 flex flex-col gap-3">
                        {auth?.isAuthenticated ? (
                            <a href="/dashboard" className="btn-primary w-full text-center">
                                Go to Dashboard
                            </a>
                        ) : (
                            <>
                                <a href="/auth/login" className="btn-primary w-full text-center">
                                    Get Started
                                </a>
                                <a href="/auth/login" className="btn-ghost text-gray-300 hover:text-white w-full text-center">
                                    Sign In
                                </a>
                            </>
                        )}
                    </div>
                )}
            </nav>

            {/* Content */}
            <main className="flex-1">
                {children}
            </main>

            {/* Footer */}
            <footer className="border-t border-gray-800 py-6 px-4 text-center text-sm text-gray-500 sm:py-8">
                SimpleModule Framework — Built with FastAPI, Inertia.js, React, and Tailwind CSS
            </footer>
        </div>
    );
}
