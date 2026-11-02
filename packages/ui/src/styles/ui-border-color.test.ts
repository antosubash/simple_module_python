// @vitest-environment node
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { compile } from '@tailwindcss/node';
import postcss, { type Rule } from 'postcss';
import { beforeAll, describe, expect, it } from 'vitest';

const base = resolve(import.meta.dirname);
let rules: Rule[];

beforeAll(async () => {
  const compiler = await compile(readFileSync(resolve(base, 'globals.css'), 'utf8'), {
    base,
    onDependency() {},
  });
  const css = compiler.build([
    'border',
    'border-b',
    'before:border',
    'after:border-b',
    'border-input',
    'border-transparent',
    'border-red-500',
    'border-current',
  ]);
  rules = [];
  postcss.parse(css).walkRules((rule) => {
    rules.push(rule);
  });
});

const colors = (rule: Rule) =>
  rule.nodes
    .filter((node) => node.type === 'decl' && node.prop === 'border-color')
    .map((node) => (node.type === 'decl' ? node.value : ''));

function inLayer(rule: Rule, layer: string): boolean {
  let parent = rule.parent;
  while (parent) {
    if (parent.type === 'atrule' && parent.name === 'layer' && parent.params === layer) {
      return true;
    }
    parent = parent.parent;
  }
  return false;
}

describe('theme border defaults (#714)', () => {
  it('gives elements and pseudo-elements a theme border in the base layer', () => {
    for (const selector of ['*', '::before', '::after']) {
      expect(
        rules.some(
          (rule) =>
            inLayer(rule, 'base') &&
            rule.selector
              .split(',')
              .map((part) => part.trim())
              .includes(selector) &&
            colors(rule).includes('var(--color-border)'),
        ),
      ).toBe(true);
    }
  });

  it('keeps bare border utilities from overriding the default color', () => {
    for (const selector of ['.border', '.border-b']) {
      const rule = rules.find((rule) => rule.selector === selector);
      expect(rule && colors(rule)).toEqual([]);
    }
  });

  it.each([
    ['.border-input', 'var(--input)'],
    ['.border-transparent', 'transparent'],
    ['.border-red-500', 'var(--color-red-500)'],
    ['.border-current', 'currentcolor'],
  ])('keeps %s in the higher-priority utilities layer', (selector, color) => {
    expect(
      rules.some(
        (rule) =>
          rule.selector === selector && inLayer(rule, 'utilities') && colors(rule).includes(color),
      ),
    ).toBe(true);
  });

  it('resolves the default through the overridable light/dark border token', () => {
    const theme = rules.find((rule) => rule.selector === ':root, :host');
    expect(
      theme?.nodes.some(
        (node) =>
          node.type === 'decl' && node.prop === '--color-border' && node.value === 'var(--border)',
      ),
    ).toBe(true);
    for (const selector of [':root', '.dark']) {
      expect(
        rules.some(
          (rule) =>
            rule.selector === selector &&
            rule.nodes.some((node) => node.type === 'decl' && node.prop === '--border'),
        ),
      ).toBe(true);
    }
  });
});
