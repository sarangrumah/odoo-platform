'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ProgressIndicator } from '@/components/intake-wizard/progress-indicator';
import {
  BrdStep,
  CompanyStep,
  ModulesStep,
  NarrativeStep,
  VerticalStep,
} from '@/components/intake-wizard/steps';
import {
  brdStepSchema,
  companyStepSchema,
  intakeSchema,
  modulesStepSchema,
  narrativeStepSchema,
  verticalStepSchema,
  type IntakeFormValues,
} from '@/lib/schemas';
import { ZodSchema } from 'zod';

const STEPS = ['Company', 'Vertical', 'Modules', 'Narrative', 'BRD + Verify'];
const STEP_SCHEMAS: ZodSchema[] = [
  companyStepSchema,
  verticalStepSchema,
  modulesStepSchema,
  narrativeStepSchema,
  brdStepSchema,
];

export default function IntakePage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [serverErr, setServerErr] = useState<string | null>(null);

  const form = useForm<IntakeFormValues>({
    resolver: zodResolver(intakeSchema),
    mode: 'onBlur',
    defaultValues: {
      company_name: '',
      contact_email: '',
      contact_phone: '',
      npwp: '',
      bank_name: '',
      bank_account: '',
      vertical_target: undefined as unknown as IntakeFormValues['vertical_target'],
      modules_wishlist: [],
      business_process_narrative: '',
      brd_file_base64s: [],
      turnstile_token: '',
    },
  });

  const next = async () => {
    const schema = STEP_SCHEMAS[step];
    const values = form.getValues();
    const result = schema.safeParse(values);
    if (!result.success) {
      // trigger field validation so messages appear
      await form.trigger();
      return;
    }
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const prev = () => setStep((s) => Math.max(0, s - 1));

  const onSubmit = async (data: IntakeFormValues) => {
    setSubmitting(true);
    setServerErr(null);
    try {
      const resp = await fetch('/api/intake', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      const json = await resp.json();
      if (!resp.ok) {
        throw new Error(json?.error || `Submission failed (${resp.status})`);
      }
      router.push(`/status/${encodeURIComponent(json.token)}`);
    } catch (e) {
      setServerErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>Vertical Onboarding Intake</CardTitle>
          <CardDescription>
            Step {step + 1} of {STEPS.length} — {STEPS[step]}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ProgressIndicator steps={STEPS} current={step} />
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {step === 0 && <CompanyStep form={form} />}
            {step === 1 && <VerticalStep form={form} />}
            {step === 2 && <ModulesStep form={form} />}
            {step === 3 && <NarrativeStep form={form} />}
            {step === 4 && <BrdStep form={form} />}

            {serverErr && (
              <div className="rounded border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
                {serverErr}
              </div>
            )}

            <div className="flex justify-between pt-4">
              <Button type="button" variant="outline" onClick={prev} disabled={step === 0}>
                Back
              </Button>
              {step < STEPS.length - 1 ? (
                <Button type="button" onClick={next}>
                  Next
                </Button>
              ) : (
                <Button type="submit" disabled={submitting}>
                  {submitting ? 'Submitting...' : 'Submit Intake'}
                </Button>
              )}
            </div>
          </form>
        </CardContent>
        <CardFooter className="text-xs text-muted-foreground">
          By submitting you agree to our processing of submitted data for the
          purpose of platform onboarding.
        </CardFooter>
      </Card>
    </div>
  );
}
