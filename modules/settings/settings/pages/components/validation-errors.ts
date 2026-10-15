// Splits a FastAPI/pydantic 422 `detail` list into per-field messages and
// form-level ones. A model-level validator (cross-field rule) reports an empty
// `loc`, which has no field to hang the message on.

export interface ValidationDetail {
  loc?: (string | number)[];
  msg: string;
}

export interface SplitErrors {
  fields: Record<string, string>;
  form: string[];
}

const VALUE_ERROR_PREFIX = /^Value error, /;

export function splitValidationErrors(detail: unknown): SplitErrors {
  const out: SplitErrors = { fields: {}, form: [] };
  if (!Array.isArray(detail)) return out;
  for (const d of detail as ValidationDetail[]) {
    const msg = String(d?.msg ?? '').replace(VALUE_ERROR_PREFIX, '');
    if (d?.loc?.length) out.fields[String(d.loc[d.loc.length - 1])] = msg;
    else if (msg) out.form.push(msg);
  }
  return out;
}
