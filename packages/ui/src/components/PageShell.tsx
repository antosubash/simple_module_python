import React from 'react';

interface PageShellProps {
    title: string;
    description?: string;
    children: React.ReactNode;
    actions?: React.ReactNode;
}

export function PageShell({ title, description, children, actions }: PageShellProps) {
    return (
        <div className="px-8 py-8">
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-gray-900">{title}</h1>
                    {description && (
                        <p className="mt-1 text-sm text-gray-500">{description}</p>
                    )}
                </div>
                {actions && <div className="flex items-center gap-3">{actions}</div>}
            </div>
            <div>{children}</div>
        </div>
    );
}
