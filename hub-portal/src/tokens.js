// Erajaya brand design tokens.
// Primary: corporate red from logo. Accent: navy blue from the swoosh.
export const tokens = {
  brand: '#E30613',
  brandDeep: '#B8050F',
  brandSoft: '#FEE2E4',
  accent: '#1E3A8A',         // Erajaya navy
  accentDeep: '#1E2F6B',
  accentSoft: '#DBE4FF',

  ink: '#0A0A0B',
  inkSoft: '#18181B',
  surface: '#FAFAF9',
  surfaceAlt: '#F4F4F2',
  border: '#E7E5E2',
  borderDark: '#27272A',
  muted: '#71717A',

  ok: '#10B981',
  warn: '#F59E0B',
  err: '#EF4444',
  info: '#3B82F6',
};

// ---------------------------------------------------------------------------
// Aliases used by the TS admin pages (OnboardingPipeline / VpsConsole etc).
// Keep these in sync with `tokens` above.
// ---------------------------------------------------------------------------
export const colors = {
  brand: tokens.brand,
  brandDeep: tokens.brandDeep,
  brandSoft: tokens.brandSoft,
  accent: tokens.accent,
  ink: tokens.ink,
  surface: tokens.surface,
  surfaceAlt: tokens.surfaceAlt,
  border: tokens.border,
  muted: tokens.muted,
  ok: tokens.ok,
  warn: tokens.warn,
  err: tokens.err,
  info: tokens.info,
  text: tokens.ink,
  textMuted: tokens.muted,
  bg: tokens.surface,
  bgAlt: tokens.surfaceAlt,
};

export const radii = { sm: 4, md: 6, lg: 8, xl: 12, pill: 999 };
export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, '2xl': 32, '3xl': 48 };

// Onboarding journey stages → display color
export const stageColors = {
  intake:             tokens.muted,
  brd_uploaded:       tokens.info,
  brd_analyzed:       tokens.info,
  go_no_go:           tokens.warn,
  vps_assigned:       tokens.accent,
  provisioning:       tokens.accent,
  modules_deploying:  tokens.accent,
  uat:                tokens.warn,
  go_live:            tokens.ok,
  closed:             tokens.muted,
  rejected:           tokens.err,
};

// Vertical options for the onboarding intake form + admin filters.
// Each entry: { value: short code stored in onboarding.journey.vertical_target, label: BA-friendly }
export const verticals = [
  { value: 'drone_services',  label: 'Drone Show Services (event-based)' },
  { value: 'drone_rental',    label: 'Drone Rental & Sales' },
  { value: 'retail',          label: 'Retail / POS' },
  { value: 'distrib',         label: 'Wholesale Distribution' },
  { value: 'fnb',             label: 'Food & Beverage' },
  { value: 'manufacturing',   label: 'Manufacturing' },
  { value: 'services',        label: 'Professional Services' },
  { value: 'rental',          label: 'Equipment Rental (general)' },
  { value: 'logistics',       label: 'Logistics & Fleet' },
  { value: 'healthcare',      label: 'Healthcare' },
  { value: 'finance',         label: 'Finance / Fintech' },
  { value: 'government',      label: 'Government / Public Sector' },
  { value: 'other',           label: 'Other (specify in narrative)' },
];

// Module catalog for the intake wizard tick-box selection. Grouped by domain so
// BA can scan; each entry has a business-friendly label + the underlying
// technical name (sent to the orchestrator).
export const moduleCatalog = [
  {
    group: 'Finance & Accounting',
    items: [
      { code: 'custom_accounting_full',      label: 'Core Accounting (GL, AR, AP, journals)' },
      { code: 'custom_accounting_asset',     label: 'Fixed Asset Register + Depreciation' },
      { code: 'custom_accounting_recurring', label: 'Recurring Journals (accruals, prepayments)' },
      { code: 'custom_bank_import',          label: 'Bank Statement Import (BCA, Mandiri, BNI, BRI)' },
      { code: 'custom_approval_engine',      label: 'Multi-tier Approval Matrix' },
      { code: 'custom_3way_match',           label: '3-Way Match (PO + GRN + Invoice)' },
      { code: 'custom_accounting_budget',    label: 'Budget Planning & Variance' },
    ],
  },
  {
    group: 'Indonesia Compliance',
    items: [
      { code: 'custom_coretax',         label: 'Coretax e-Faktur (DJP)' },
      { code: 'custom_coretax_bupot',   label: 'Bupot Unifikasi (PPh withholding tax slip)' },
      { code: 'custom_coretax_pajakku', label: 'Pajakku ASPP Integration' },
      { code: 'custom_pph_witholding',  label: 'PPh Withholding Engine (PMK-131)' },
      { code: 'custom_pdp_masking',     label: 'PDP Field Masking (UU 27/2022)' },
    ],
  },
  {
    group: 'Sales / Rental / Service',
    items: [
      { code: 'custom_drone_show',       label: 'Drone Show Event Management (site survey, permissions, choreography)' },
      { code: 'custom_pilot_procurement',label: 'External Pilot Procurement (vendor pool, SKK, rates)' },
      { code: 'custom_flight_permission',label: 'Flight Permission Tracking (NOTAM, KKOP, izin)' },
      { code: 'custom_rental',           label: 'Rental Management (booking, return, fees)' },
      { code: 'custom_rental_drone',     label: 'Drone Rental Extension (equipment check, battery, warranty)' },
      { code: 'custom_damage_claim',     label: 'Damage Claim Workflow' },
      { code: 'custom_drone_repair',     label: 'Drone Repair Orders (local, overseas, principal)' },
      { code: 'custom_drone_kit',        label: 'Drone Kit Bundling (auto-expand accessories)' },
      { code: 'custom_pos_id',           label: 'Point of Sale (Indonesia)' },
      { code: 'custom_retail_pos_offline', label: 'Offline-first POS (outlet-grade)' },
      { code: 'custom_subscription',     label: 'Subscription Billing' },
    ],
  },
  {
    group: 'Inventory & Logistics',
    items: [
      { code: 'custom_wms_putaway',      label: 'WMS Putaway Rules' },
      { code: 'custom_wms_cycle_count',  label: 'WMS Cycle Count' },
      { code: 'custom_wms_to_engine',    label: 'Transfer Order Engine (multi-leg routing)' },
      { code: 'custom_hht_bridge',       label: 'Handheld Terminal (HHT) Bridge' },
      { code: 'custom_iot_bridge',       label: 'IoT Sensor Bridge' },
      { code: 'custom_drone_fleet',      label: 'Drone Fleet Master (per-SN tracking, flight hours)' },
      { code: 'custom_drone_dropship',   label: 'Drone Drop-Ship Route' },
    ],
  },
  {
    group: 'Operations & Platform',
    items: [
      { code: 'custom_tenant_infra',     label: 'VPS + Environment Lifecycle' },
      { code: 'custom_hub_console',      label: 'Module Catalog + Canary Deploy' },
      { code: 'custom_ops_monitor',      label: 'Service Health + Incident' },
      { code: 'custom_dev_cycle',        label: 'Dev Cycle Tracking (PR + CI webhook)' },
      { code: 'custom_onboarding_journey', label: 'Tenant Onboarding State Machine' },
    ],
  },
  {
    group: 'AI & Data',
    items: [
      { code: 'custom_brd_analyzer',     label: 'AI BRD Analyzer (GAP report + mandays)' },
      { code: 'custom_ai_features',      label: 'AI Features (NLQ chat, anomaly scan, Ask AI)' },
      { code: 'custom_documents',        label: 'Documents Workspace (versioning, ACL)' },
      { code: 'custom_appointments',     label: 'Appointments / Scheduling' },
    ],
  },
  {
    group: 'HR & People',
    items: [
      { code: 'custom_hr_payroll_id',    label: 'Payroll Indonesia (TER, BPJS, PPh 21)' },
      { code: 'custom_hr_appraisal',     label: 'HR Appraisal' },
      { code: 'custom_hr_referral',      label: 'Employee Referral' },
      { code: 'custom_planning',         label: 'Resource Planning' },
    ],
  },
];

// Six Erajaya business verticals — must mirror the operational segmentation
// behind the multi-tenant Odoo platform (see docs/architecture.md).
export const verticalDefs = [
  { id: 'fnb',     name: 'F&B Erajaya',         tagline: 'Restaurant & café operations',   icon: '🍽️', color: tokens.brand },
  { id: 'active',  name: 'Active Lifestyle',    tagline: 'Sports & fitness retail',         icon: '🏃', color: '#F59E0B' },
  { id: 'retail',  name: 'Erajaya Retail',      tagline: 'Eraspace & device retail',        icon: '📱', color: tokens.accent },
  { id: 'distrib', name: 'Distribution',        tagline: 'Wholesale & logistics',           icon: '🚚', color: '#10B981' },
  { id: 'service', name: 'Service Center',      tagline: 'After-sales & repair',            icon: '🔧', color: '#8B5CF6' },
  { id: 'corp',    name: 'Corporate Services',  tagline: 'Shared services & VAS',           icon: '🏢', color: '#EC4899' },
];
