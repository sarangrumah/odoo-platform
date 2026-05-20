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

// Vertical codes used by the onboarding intake form + filters.
export const verticals = ['fnb', 'active', 'retail', 'distrib', 'service', 'corp'];

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
