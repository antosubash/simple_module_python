import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Convert a snake_case module directory name to the PascalCase component
 * namespace used by ModuleMeta.name. Must mirror ``to_class_name()`` in
 * scripts/new_module.py — the two decide the same "blog_posts" → "BlogPosts"
 * mapping on the frontend and backend respectively.
 */
export function toPascalCase(name: string): string {
  return name
    .split('_')
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join('');
}
