import { z } from 'zod';

export const productSchema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .max(200, 'Name must be under 200 characters'),
  description: z.string().max(2000).optional().default(''),
  price: z
    .string()
    .min(1, 'Price is required')
    .refine((v) => Number(v) > 0, 'Price must be greater than 0'),
  is_active: z.boolean().optional(),
});

export type ProductFormData = z.infer<typeof productSchema>;

export function validateProduct(data: {
  name: string;
  price: string;
}): Record<string, string> {
  const result = productSchema.safeParse(data);
  if (result.success) return {};
  const errors: Record<string, string> = {};
  for (const issue of result.error.issues) {
    const field = String(issue.path[0] ?? 'general');
    if (!errors[field]) errors[field] = issue.message;
  }
  return errors;
}
