import type { ReactNode } from 'react';

interface Props {
  hero: ReactNode;
  title: string;
  description: string;
  details?: ReactNode;
  children: ReactNode;
}

export function ErrorScreen({ hero, title, description, details, children }: Props) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="text-center max-w-md">
        <p className="text-8xl font-extrabold font-[var(--font-display)] text-primary">{hero}</p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-4xl">
          {title}
        </h1>
        <p className="mt-3 text-base text-muted-foreground leading-relaxed">{description}</p>
        {details}
        <div className="mt-8 flex items-center justify-center gap-4">{children}</div>
      </div>
    </div>
  );
}
