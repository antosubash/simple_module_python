// Splits a FastAPI/pydantic 422 `detail` list into per-field messages and
// form-level ones. An error is attached to a field when its `loc` starts with
// (or, after FastAPI's `body` prefix, contains at its head) a known field name;
// anything else -- a model-level validator (empty `loc`), a `loc` naming no
// field -- is surfaced at form level so a 422 is never swallowed.

import { keys, type TranslationKey, t } from '@simple-module-py/i18n';

export interface ValidationDetail {
  loc?: (string | number)[];
  msg: string;
  type?: string;
  ctx?: Record<string, unknown>;
}

export interface SplitErrors {
  fields: Record<string, string>;
  form: string[];
}

const VALUE_ERROR_PREFIX = /^Value error, /;

/** Pydantic prefixes a validator's ValueError message with "Value error, ". */
export function stripValueErrorPrefix(message: string): string {
  return message.replace(VALUE_ERROR_PREFIX, '');
}

function validationMessage(error: ValidationDetail): string {
  const fallback = stripValueErrorPrefix(String(error?.msg ?? ''));
  const k = keys.settings.validation;
  const messages: Record<string, [TranslationKey, string?]> = {
    greater_than: [k.greater_than, 'gt'],
    greater_than_equal: [k.greater_than_equal, 'ge'],
    less_than: [k.less_than, 'lt'],
    less_than_equal: [k.less_than_equal, 'le'],
    int_parsing: [k.integer],
    int_from_float: [k.integer],
    float_parsing: [k.number],
    bool_parsing: [k.boolean],
    missing: [k.required],
    string_too_short: [k.string_too_short, 'min_length'],
    string_too_long: [k.string_too_long, 'max_length'],
    too_long: [k.too_long, 'max_length'],
    url_parsing: [k.url],
    url_scheme: [k.url_scheme, 'expected_schemes'],
    literal_error: [k.choice, 'expected'],
    enum: [k.choice, 'expected'],
    json_invalid: [k.json],
  };
  const type = error?.type ?? '';
  if (!Object.hasOwn(messages, type)) return fallback;
  const [key, context] = messages[type];
  const value = context ? error.ctx?.[context] : undefined;
  if (context && typeof value !== 'string' && typeof value !== 'number') return fallback;
  return t(key, { limit: value, expected: value });
}

export function splitValidationErrors(
  detail: unknown,
  fieldNames?: readonly string[],
): SplitErrors {
  const out: SplitErrors = { fields: {}, form: [] };
  if (typeof detail === 'string') {
    if (detail) out.form.push(detail);
    return out;
  }
  if (!Array.isArray(detail)) return out;
  const known = fieldNames ? new Set(fieldNames) : null;
  for (const d of detail as ValidationDetail[]) {
    const msg = validationMessage(d);
    if (!msg) continue;
    let loc = (d?.loc ?? []).map(String);
    if (loc[0] === 'body') loc = loc.slice(1);
    const head = loc[0];
    if (head !== undefined && (!known || known.has(head))) {
      const rest = loc.slice(1).join('.');
      const text = rest ? `${rest}: ${msg}` : msg;
      out.fields[head] = out.fields[head] ? `${out.fields[head]}; ${text}` : text;
    } else {
      out.form.push(loc.length ? `${loc.join('.')}: ${msg}` : msg);
    }
  }
  return out;
}
