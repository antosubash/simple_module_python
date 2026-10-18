// Splits a FastAPI/pydantic 422 `detail` list into per-field messages and
// form-level ones. An error is attached to a field when its `loc` starts with
// (or, after FastAPI's `body` prefix, contains at its head) a known field name;
// anything else -- a model-level validator (empty `loc`), a `loc` naming no
// field -- is surfaced at form level so a 422 is never swallowed.

export interface ValidationDetail {
  loc?: (string | number)[];
  msg: string;
}

export interface SplitErrors {
  fields: Record<string, string>;
  form: string[];
}

const VALUE_ERROR_PREFIX = /^Value error, /;

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
    const msg = String(d?.msg ?? '').replace(VALUE_ERROR_PREFIX, '');
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
