// Design tokens shared across hub-portal.
// Mirrors palette from docs/erajaya-odoo-hub.jsx reference design.

export const colors = {
  bg: '#0b1220',
  bgElevated: '#111a2e',
  surface: '#0f1729',
  surfaceMuted: '#152038',
  border: '#23304d',
  borderStrong: '#2f3f64',
  text: '#e6edf7',
  textMuted: '#9aa6c2',
  textDim: '#6b7896',
  accent: '#6366f1',
  accentSoft: '#4f46e5',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',
  brand: '#f97316', // Erajaya orange
} as const;

export const radii = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const shadows = {
  sm: '0 1px 2px rgba(0,0,0,0.2)',
  md: '0 4px 12px rgba(0,0,0,0.25)',
  lg: '0 12px 32px rgba(0,0,0,0.35)',
} as const;

export const stageColors: Record<string, string> = {
  intake: '#3b82f6',
  brd_uploaded: '#06b6d4',
  brd_analyzed: '#0ea5e9',
  go_no_go: '#a855f7',
  vps_assigned: '#8b5cf6',
  provisioning: '#f59e0b',
  modules_deploying: '#eab308',
  uat: '#f97316',
  go_live: '#22c55e',
  closed: '#6b7280',
};

export const verticals = [
  { value: 'residensia', label: 'Residensia' },
  { value: 'ppob', label: 'PPOB' },
  { value: 'arkaim', label: 'Arkaim' },
  { value: 'jds', label: 'JDS' },
  { value: 'telco', label: 'Telco' },
  { value: 'komdigi', label: 'Komdigi' },
  { value: 'other', label: 'Other' },
] as const;

export type VerticalValue = (typeof verticals)[number]['value'];
