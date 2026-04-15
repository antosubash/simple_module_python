import { useT } from '@simple-module/i18n';
import { z } from 'zod';

/**
 * Builds the product form schema inside a React component so that validation
 * messages are resolved against the currently-active locale.
 */
export function useProductSchema() {
  const { t } = useT();
  return z.object({
    name: z
      .string()
      .min(1, t('products.validation.name_required'))
      .max(200, t('products.validation.name_too_long')),
    description: z.string().max(2000).optional().default(''),
    price: z
      .string()
      .min(1, t('products.validation.price_required'))
      .refine((v) => Number(v) > 0, t('products.validation.price_positive')),
    is_active: z.boolean().optional(),
  });
}

export type ProductFormData = z.infer<ReturnType<typeof useProductSchema>>;

export function useValidateProduct() {
  const schema = useProductSchema();
  return function validateProduct(data: { name: string; price: string }): Record<string, string> {
    const result = schema.safeParse(data);
    if (result.success) return {};
    const errors: Record<string, string> = {};
    for (const issue of result.error.issues) {
      const field = String(issue.path[0] ?? 'general');
      if (!errors[field]) errors[field] = issue.message;
    }
    return errors;
  };
}
