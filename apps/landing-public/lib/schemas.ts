import { z } from 'zod';

export const companyStepSchema = z.object({
  company_name: z.string().min(2, 'Company name is required').max(200),
  contact_email: z.string().email('Valid email required'),
  contact_phone: z.string().min(6).max(32),
  npwp: z
    .string()
    .regex(/^[0-9.\-]{15,25}$/, 'NPWP format invalid')
    .optional()
    .or(z.literal('')),
  bank_name: z.string().max(100).optional().or(z.literal('')),
  bank_account: z.string().max(64).optional().or(z.literal('')),
  company_logo_base64: z.string().optional(),
});

export const verticalTargetEnum = z.enum([
  'residensia',
  'ppob',
  'arkaim',
  'jds',
  'telco',
  'komdigi',
  'other',
]);

export const verticalStepSchema = z.object({
  vertical_target: verticalTargetEnum,
});

export const modulesStepSchema = z.object({
  modules_wishlist: z
    .array(z.string().min(1).max(80))
    .min(1, 'At least one module wish required')
    .max(50),
});

export const narrativeStepSchema = z.object({
  business_process_narrative: z
    .string()
    .min(50, 'Please describe your business process in detail (>= 50 chars)')
    .max(20000),
});

export const brdStepSchema = z.object({
  brd_file_base64s: z.array(z.string()).max(5).optional(),
  turnstile_token: z.string().min(1, 'Captcha required'),
});

export const intakeSchema = companyStepSchema
  .merge(verticalStepSchema)
  .merge(modulesStepSchema)
  .merge(narrativeStepSchema)
  .merge(brdStepSchema);

export type IntakeFormValues = z.infer<typeof intakeSchema>;

export const intakeResponseSchema = z.object({
  token: z.string(),
  status_url: z.string(),
});

export const statusResponseSchema = z.object({
  token: z.string(),
  stage: z.string(),
  status: z.string(),
  target_go_live: z.string().nullable().optional(),
  progress_pct: z.number().min(0).max(100).optional(),
  journey_id: z.number().nullable().optional(),
});

export type StatusResponse = z.infer<typeof statusResponseSchema>;
