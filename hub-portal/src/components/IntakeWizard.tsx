import { ChangeEvent, DragEvent, useState } from 'react';
import { Check, ChevronLeft, ChevronRight, Plus, Trash2, Upload, X } from 'lucide-react';
import { Badge, Button, Card, Input, Modal, Select, Textarea, Toast } from './ui';
import { colors, radii, spacing, verticals, VerticalValue } from '../tokens';
import { IntakePayload, submitIntake } from '../api';

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: (token: string) => void;
}

const STEPS = ['Company', 'Vertical', 'Modules', 'Narrative', 'BRD'] as const;

export default function IntakeWizard({ open, onClose, onSuccess }: Props) {
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Step 1 — company
  const [companyName, setCompanyName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [npwp, setNpwp] = useState('');
  const [bankName, setBankName] = useState('');
  const [bankAccount, setBankAccount] = useState('');
  const [logo, setLogo] = useState<string | null>(null);

  // Step 2
  const [vertical, setVertical] = useState<VerticalValue>('residensia');

  // Step 3
  const [wishlist, setWishlist] = useState<string[]>([]);
  const [wishDraft, setWishDraft] = useState('');

  // Step 4
  const [narrative, setNarrative] = useState('');

  // Step 5
  const [brdFiles, setBrdFiles] = useState<{ name: string; data: string }[]>([]);

  function reset() {
    setStep(0);
    setCompanyName('');
    setContactEmail('');
    setContactPhone('');
    setNpwp('');
    setBankName('');
    setBankAccount('');
    setLogo(null);
    setVertical('residensia');
    setWishlist([]);
    setWishDraft('');
    setNarrative('');
    setBrdFiles([]);
    setError(null);
  }

  function close() {
    reset();
    onClose();
  }

  async function readFile(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result || ''));
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }

  async function onLogo(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setLogo(await readFile(f));
  }

  async function onBrdDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files);
    const parsed = await Promise.all(files.map(async (f) => ({ name: f.name, data: await readFile(f) })));
    setBrdFiles((prev) => [...prev, ...parsed].slice(0, 5));
  }

  async function onBrdPick(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    const parsed = await Promise.all(files.map(async (f) => ({ name: f.name, data: await readFile(f) })));
    setBrdFiles((prev) => [...prev, ...parsed].slice(0, 5));
  }

  function addWish() {
    const v = wishDraft.trim();
    if (!v) return;
    setWishlist((prev) => [...prev, v]);
    setWishDraft('');
  }

  function validateStep(): string | null {
    if (step === 0) {
      if (companyName.trim().length < 2) return 'Company name is required';
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contactEmail)) return 'Valid email required';
      if (contactPhone.trim().length < 6) return 'Phone is required';
    }
    if (step === 2 && wishlist.length === 0) return 'Add at least one module wish';
    if (step === 3 && narrative.trim().length < 50) return 'Narrative must be at least 50 characters';
    return null;
  }

  function next() {
    const err = validateStep();
    if (err) {
      setError(err);
      return;
    }
    setError(null);
    if (step < STEPS.length - 1) setStep(step + 1);
  }

  async function submit() {
    const err = validateStep();
    if (err) {
      setError(err);
      return;
    }
    setSubmitting(true);
    setError(null);
    const payload: IntakePayload = {
      company_name: companyName,
      contact_email: contactEmail,
      contact_phone: contactPhone,
      npwp: npwp || undefined,
      bank_name: bankName || undefined,
      bank_account: bankAccount || undefined,
      company_logo_base64: logo || undefined,
      vertical_target: vertical,
      modules_wishlist: wishlist,
      business_process_narrative: narrative,
      brd_file_base64s: brdFiles.map((f) => f.data),
      source: 'internal_ba',
    };
    try {
      const resp = await submitIntake(payload);
      setToast(`Intake submitted · token ${resp.token}`);
      onSuccess?.(resp.token);
      setTimeout(close, 1200);
    } catch (e: any) {
      setError(e?.detail || e?.message || 'Submit failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Modal open={open} onClose={close} title="New Onboarding Intake" width={780}>
        {/* Stepper */}
        <div style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.xl }}>
          {STEPS.map((s, i) => {
            const done = i < step;
            const active = i === step;
            return (
              <div key={s} style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6 }}>
                <div
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    background: done ? colors.success : active ? colors.accent : colors.surfaceMuted,
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                >
                  {done ? <Check size={12} /> : i + 1}
                </div>
                <span style={{ fontSize: 11, color: active ? colors.text : colors.textMuted }}>{s}</span>
              </div>
            );
          })}
        </div>

        {error && (
          <div
            style={{
              background: 'rgba(239,68,68,0.1)',
              color: colors.danger,
              padding: 10,
              borderRadius: radii.md,
              fontSize: 13,
              marginBottom: spacing.md,
            }}
          >
            {error}
          </div>
        )}

        {/* Step content */}
        {step === 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md }}>
            <Field label="Company name *">
              <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
            </Field>
            <Field label="Contact email *">
              <Input type="email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} />
            </Field>
            <Field label="Contact phone *">
              <Input value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
            </Field>
            <Field label="NPWP">
              <Input value={npwp} onChange={(e) => setNpwp(e.target.value)} placeholder="00.000.000.0-000.000" />
            </Field>
            <Field label="Bank name">
              <Input value={bankName} onChange={(e) => setBankName(e.target.value)} />
            </Field>
            <Field label="Bank account">
              <Input value={bankAccount} onChange={(e) => setBankAccount(e.target.value)} />
            </Field>
            <Field label="Company logo">
              <input type="file" accept="image/*" onChange={onLogo} />
              {logo && (
                <img
                  src={logo}
                  alt="logo"
                  style={{ marginTop: 6, height: 48, borderRadius: 4, border: `1px solid ${colors.border}` }}
                />
              )}
            </Field>
          </div>
        )}

        {step === 1 && (
          <Field label="Vertical target *">
            <Select value={vertical} onChange={(e) => setVertical(e.target.value as VerticalValue)}>
              {verticals.map((v) => (
                <option key={v.value} value={v.value}>
                  {v.label}
                </option>
              ))}
            </Select>
            <p style={{ color: colors.textMuted, fontSize: 12, marginTop: spacing.sm }}>
              Choose the primary vertical that best fits the new tenant. Cross-vertical extensions can be enabled later.
            </p>
          </Field>
        )}

        {step === 2 && (
          <Field label="Modules wishlist *">
            <div style={{ display: 'flex', gap: 6 }}>
              <Input
                value={wishDraft}
                onChange={(e) => setWishDraft(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addWish())}
                placeholder="e.g. invoice_recurring, hht_scan, pdp_masking"
              />
              <Button variant="secondary" onClick={addWish}>
                <Plus size={14} /> Add
              </Button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: spacing.sm }}>
              {wishlist.map((w, i) => (
                <Badge key={i} tone="info" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                  {w}
                  <button
                    onClick={() => setWishlist(wishlist.filter((_, j) => j !== i))}
                    style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
                  >
                    <X size={10} />
                  </button>
                </Badge>
              ))}
            </div>
          </Field>
        )}

        {step === 3 && (
          <Field label="Business process narrative *">
            <Textarea
              value={narrative}
              onChange={(e) => setNarrative(e.target.value)}
              rows={10}
              placeholder="Describe the partner's core business processes, pain points, integrations…"
            />
            <p style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{narrative.length} / 20000 chars</p>
          </Field>
        )}

        {step === 4 && (
          <Field label="BRD upload (optional, max 5 files)">
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={onBrdDrop}
              style={{
                border: `2px dashed ${colors.border}`,
                borderRadius: radii.md,
                padding: spacing.xxl,
                textAlign: 'center',
                color: colors.textMuted,
              }}
            >
              <Upload size={28} style={{ margin: '0 auto 8px' }} />
              <div>Drop BRD files here</div>
              <div style={{ fontSize: 11, color: colors.textDim, marginTop: 4 }}>or</div>
              <label
                style={{
                  display: 'inline-block',
                  marginTop: 8,
                  padding: '6px 12px',
                  background: colors.surfaceMuted,
                  borderRadius: radii.md,
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                Browse files
                <input type="file" multiple style={{ display: 'none' }} onChange={onBrdPick} />
              </label>
            </div>
            {brdFiles.length > 0 && (
              <div style={{ marginTop: spacing.sm, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {brdFiles.map((f, i) => (
                  <Card key={i} padded={false} style={{ padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
                    <span>{f.name}</span>
                    <button
                      onClick={() => setBrdFiles(brdFiles.filter((_, j) => j !== i))}
                      style={{ background: 'none', border: 'none', color: colors.danger, cursor: 'pointer' }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </Card>
                ))}
              </div>
            )}
          </Field>
        )}

        {/* Navigation */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: spacing.xl }}>
          <Button variant="ghost" onClick={() => (step === 0 ? close() : setStep(step - 1))}>
            <ChevronLeft size={14} /> {step === 0 ? 'Cancel' : 'Back'}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={next}>
              Next <ChevronRight size={14} />
            </Button>
          ) : (
            <Button onClick={submit} disabled={submitting}>
              <Check size={14} /> {submitting ? 'Submitting…' : 'Submit intake'}
            </Button>
          )}
        </div>
      </Modal>
      {toast && <Toast msg={toast} />}
    </>
  );
}

function Field({ label, children }: { label: string; children: any }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: colors.textMuted }}>
      {label}
      <div style={{ marginTop: 2 }}>{children}</div>
    </label>
  );
}
