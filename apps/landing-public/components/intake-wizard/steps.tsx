'use client';

import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { X } from 'lucide-react';
import type { IntakeFormValues } from '@/lib/schemas';
import { Turnstile } from '@/components/turnstile';

type Form = UseFormReturn<IntakeFormValues>;

function ErrorMsg({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="text-sm text-destructive mt-1">{msg}</p>;
}

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',')[1] || '');
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export function CompanyStep({ form }: { form: Form }) {
  const {
    register,
    setValue,
    watch,
    formState: { errors },
  } = form;
  const logo = watch('company_logo_base64');

  return (
    <div className="space-y-4">
      <div>
        <Label>Company Name *</Label>
        <Input {...register('company_name')} placeholder="PT Acme Indonesia" />
        <ErrorMsg msg={errors.company_name?.message} />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label>Contact Email *</Label>
          <Input type="email" {...register('contact_email')} />
          <ErrorMsg msg={errors.contact_email?.message} />
        </div>
        <div>
          <Label>Contact Phone *</Label>
          <Input {...register('contact_phone')} placeholder="+62..." />
          <ErrorMsg msg={errors.contact_phone?.message} />
        </div>
      </div>
      <div>
        <Label>Company Logo (optional)</Label>
        <Input
          type="file"
          accept="image/*"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) setValue('company_logo_base64', await fileToBase64(f));
          }}
        />
        {logo && (
          <div className="mt-2 inline-block rounded border p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/*;base64,${logo}`} alt="Logo preview" className="h-16" />
          </div>
        )}
      </div>
      <div className="grid md:grid-cols-3 gap-4">
        <div>
          <Label>NPWP</Label>
          <Input {...register('npwp')} placeholder="00.000.000.0-000.000" />
          <ErrorMsg msg={errors.npwp?.message} />
        </div>
        <div>
          <Label>Bank Name</Label>
          <Input {...register('bank_name')} />
        </div>
        <div>
          <Label>Bank Account</Label>
          <Input {...register('bank_account')} />
        </div>
      </div>
    </div>
  );
}

export function VerticalStep({ form }: { form: Form }) {
  const {
    setValue,
    watch,
    formState: { errors },
  } = form;
  const v = watch('vertical_target');

  return (
    <div className="space-y-2">
      <Label>Target Vertical *</Label>
      <Select value={v} onValueChange={(val) => setValue('vertical_target', val as IntakeFormValues['vertical_target'], { shouldValidate: true })}>
        <SelectTrigger>
          <SelectValue placeholder="Select vertical..." />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="residensia">Residensia (community/HOA)</SelectItem>
          <SelectItem value="ppob">PPOB (payment point)</SelectItem>
          <SelectItem value="arkaim">Arkaim</SelectItem>
          <SelectItem value="jds">JDS</SelectItem>
          <SelectItem value="telco">e-Telekomunikasi</SelectItem>
          <SelectItem value="komdigi">Komdigi</SelectItem>
          <SelectItem value="other">Other / New vertical</SelectItem>
        </SelectContent>
      </Select>
      <ErrorMsg msg={errors.vertical_target?.message} />
    </div>
  );
}

export function ModulesStep({ form }: { form: Form }) {
  const {
    setValue,
    watch,
    formState: { errors },
  } = form;
  const list = watch('modules_wishlist') || [];
  const [draft, setDraft] = useState('');

  const add = () => {
    const v = draft.trim();
    if (!v) return;
    setValue('modules_wishlist', [...list, v], { shouldValidate: true });
    setDraft('');
  };

  const remove = (i: number) =>
    setValue(
      'modules_wishlist',
      list.filter((_, idx) => idx !== i),
      { shouldValidate: true },
    );

  return (
    <div className="space-y-3">
      <Label>Modules Wishlist *</Label>
      <p className="text-sm text-muted-foreground">
        Add modules / features you'd like (free text). e.g. "billing", "loyalty",
        "fleet tracking", etc.
      </p>
      <div className="flex gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              add();
            }
          }}
          placeholder="Type and press Enter..."
        />
        <Button type="button" onClick={add}>
          Add
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {list.map((m, i) => (
          <Badge key={`${m}-${i}`} variant="secondary" className="gap-1 pr-1">
            {m}
            <button
              type="button"
              onClick={() => remove(i)}
              className="ml-1 rounded-full hover:bg-destructive/20 p-0.5"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <ErrorMsg msg={errors.modules_wishlist?.message as string | undefined} />
    </div>
  );
}

export function NarrativeStep({ form }: { form: Form }) {
  const {
    register,
    formState: { errors },
  } = form;
  return (
    <div className="space-y-2">
      <Label>Business Process Narrative *</Label>
      <p className="text-sm text-muted-foreground">
        Describe your end-to-end business flow, pain points, integrations needed.
        Minimum 50 chars.
      </p>
      <Textarea rows={10} {...register('business_process_narrative')} />
      <ErrorMsg msg={errors.business_process_narrative?.message} />
    </div>
  );
}

export function BrdStep({ form }: { form: Form }) {
  const {
    setValue,
    watch,
    formState: { errors },
  } = form;
  const files = watch('brd_file_base64s') || [];

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const list = Array.from(e.dataTransfer.files);
    const encoded = await Promise.all(list.map(fileToBase64));
    setValue('brd_file_base64s', [...files, ...encoded].slice(0, 5));
  };

  return (
    <div className="space-y-4">
      <div>
        <Label>BRD Files (optional, max 5)</Label>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
          className="mt-2 rounded-md border-2 border-dashed p-8 text-center text-sm text-muted-foreground hover:border-primary cursor-pointer"
        >
          <p>Drag & drop BRD documents here (PDF, DOCX, etc.)</p>
          <p className="text-xs mt-1">or use the picker below</p>
          <Input
            type="file"
            multiple
            className="mt-3"
            onChange={async (e) => {
              const list = Array.from(e.target.files || []);
              const encoded = await Promise.all(list.map(fileToBase64));
              setValue('brd_file_base64s', [...files, ...encoded].slice(0, 5));
            }}
          />
        </div>
        {files.length > 0 && (
          <p className="text-sm text-muted-foreground mt-2">{files.length} file(s) attached</p>
        )}
      </div>
      <div>
        <Label>Verify you are human *</Label>
        <div className="mt-2">
          <Turnstile onToken={(t) => setValue('turnstile_token', t, { shouldValidate: true })} />
        </div>
        <ErrorMsg msg={errors.turnstile_token?.message} />
      </div>
    </div>
  );
}
