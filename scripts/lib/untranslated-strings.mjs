/**
 * Find user-visible string literals in a `.tsx` source.
 *
 * Shipping `locales/en.json` never proved a page read it: `SM013`–`SM016` only
 * compare catalogs against each other, so with `i18n_supported_locales = ["en"]`
 * they never fire, and `tsc` is happy with hardcoded English. This is the check
 * that notices.
 *
 * Parses rather than greps: no regex over JSX can tell `<p>Save</p>` from the
 * `Promise<void>` in a type annotation, and one that tries flags both.
 *
 * Known blind spot: a string reaching the screen through a variable or a config
 * object (`const THEME = { mobileTitleLabel: 'Admin' }`) is invisible here —
 * catching that needs taint analysis, and guessing instead would produce the
 * false positives that get a check switched off.
 */

import { parse } from '@babel/parser';

/**
 * Attributes whose string value reaches the user. Deliberately a closed list —
 * `className`, `variant`, `role` and `type` carry machine tokens, and flagging
 * those would train people to reach for the exemption instead of the catalog.
 */
export const TEXT_ATTRIBUTES = new Set([
  'alt',
  'aria-description',
  'aria-label',
  'aria-placeholder',
  'aria-roledescription',
  'aria-valuetext',
  'cancelLabel',
  'confirmLabel',
  'description',
  'emptyText',
  'heading',
  'helperText',
  'label',
  'placeholder',
  'submitLabel',
  'subtitle',
  'title',
  'tooltip',
]);

/** Calls whose first string argument is shown to the user. */
export const TEXT_CALLS = new Set([
  'alert',
  'confirm',
  'prompt',
  'toast',
  'toast.error',
  'toast.info',
  'toast.loading',
  'toast.message',
  'toast.success',
  'toast.warning',
  'window.alert',
  'window.confirm',
  'window.prompt',
]);

/**
 * Elements whose content is a technical literal by definition — a shell
 * command, an env var name, a JSON example. Translating those would be wrong.
 */
const LITERAL_ELEMENTS = new Set(['code', 'pre', 'kbd', 'samp', 'var']);

const EXEMPT_LINE = /i18n-exempt/;
const EXEMPT_FILE = /i18n-exempt-file/;

/**
 * Is this copy a reader would notice, rather than punctuation or a glyph?
 * Text with no letter is "—", "·", "/", "4"; a single character is an avatar
 * initial or a fallback like `name[0] ?? 'S'`, never a sentence.
 */
const isCopy = (value) => value.length > 1 && /\p{L}/u.test(value);

/** Dotted callee name, e.g. "toast.success" or "window.confirm". */
function calleeName(node) {
  if (!node) return '';
  if (node.type === 'Identifier') return node.name;
  if (node.type === 'MemberExpression' && !node.computed) {
    const object = calleeName(node.object);
    const property = node.property.type === 'Identifier' ? node.property.name : '';
    return object && property ? `${object}.${property}` : '';
  }
  return '';
}

function attributeName(node) {
  if (node.name.type === 'JSXIdentifier') return node.name.name;
  if (node.name.type === 'JSXNamespacedName') {
    return `${node.name.namespace.name}:${node.name.name.name}`;
  }
  return '';
}

function elementName(node) {
  const name = node.openingElement?.name;
  return name?.type === 'JSXIdentifier' ? name.name.toLowerCase() : '';
}

/**
 * Literal text an expression can render, or '' when it is fully dynamic.
 *
 * Recurses through the shapes that hide copy inside an expression —
 * `cond ? 'Close menu' : 'Open menu'`, `x && 'Saved'` — because those read as
 * dynamic to a naive check while still putting English on screen.
 */
function literalText(node) {
  if (!node) return '';
  switch (node.type) {
    case 'StringLiteral':
      return node.value;
    case 'TemplateLiteral':
      return node.quasis.map((q) => q.value.cooked ?? '').join(' ');
    case 'ConditionalExpression':
      return `${literalText(node.consequent)} ${literalText(node.alternate)}`;
    case 'LogicalExpression':
      return `${literalText(node.left)} ${literalText(node.right)}`;
    case 'JSXExpressionContainer':
      return literalText(node.expression);
    default:
      return '';
  }
}

/**
 * @param {string} source  TSX source text.
 * @returns {{line: number, kind: string, value: string}[]}
 */
export function findUntranslated(source) {
  if (EXEMPT_FILE.test(source.slice(0, 800))) return [];

  const lines = source.split('\n');
  let ast;
  try {
    ast = parse(source, { sourceType: 'module', plugins: ['jsx', 'typescript'] });
  } catch (error) {
    // Fail closed: an unparseable file must not silently pass the gate.
    return [{ line: 1, kind: 'parse-error', value: String(error.message).slice(0, 80) }];
  }

  const findings = [];
  // The marker may sit on the offending line or the line above it, since the
  // formatter routinely pushes an attribute or child onto its own line.
  const exempt = (line) =>
    EXEMPT_LINE.test(lines[line - 1] ?? '') || EXEMPT_LINE.test(lines[line - 2] ?? '');

  const report = (node, kind, value) => {
    const line = node.loc?.start.line ?? 1;
    if (exempt(line)) return;
    findings.push({ line, kind, value: value.trim().replace(/\s+/g, ' ').slice(0, 72) });
  };

  const visit = (node, literalDepth, inTextPosition) => {
    if (!node || typeof node.type !== 'string') return;

    if (node.type === 'JSXText') {
      const value = node.value.trim();
      if (isCopy(value) && literalDepth === 0) report(node, 'jsx-text', value);
    } else if (node.type === 'JSXAttribute') {
      const name = attributeName(node);
      if (TEXT_ATTRIBUTES.has(name)) {
        const value = literalText(node.value).trim();
        if (isCopy(value)) report(node, `attr:${name}`, value);
      }
    } else if (node.type === 'JSXExpressionContainer' && inTextPosition) {
      // `<span>{'Saved'}</span>` and `{ok ? 'Saved' : 'Failed'}` render copy
      // just as surely as bare JSX text does.
      const value = literalText(node.expression).trim();
      if (isCopy(value) && literalDepth === 0) report(node, 'jsx-expression', value);
    } else if (node.type === 'CallExpression') {
      const name = calleeName(node.callee);
      if (TEXT_CALLS.has(name)) {
        const value = literalText(node.arguments[0]).trim();
        if (isCopy(value)) report(node, `call:${name}`, value);
      }
    }

    const nextDepth =
      node.type === 'JSXElement' && LITERAL_ELEMENTS.has(elementName(node))
        ? literalDepth + 1
        : literalDepth;

    const isElement = node.type === 'JSXElement' || node.type === 'JSXFragment';
    for (const key of Object.keys(node)) {
      if (key === 'loc' || key === 'leadingComments' || key === 'trailingComments') continue;
      const child = node[key];
      // Only `children` sit in text position; an attribute's container does not.
      const childInText = isElement && key === 'children';
      if (Array.isArray(child)) {
        for (const item of child) visit(item, nextDepth, childInText);
      } else if (child && typeof child === 'object') {
        visit(child, nextDepth, childInText);
      }
    }
  };

  visit(ast.program, 0, false);
  return findings;
}
