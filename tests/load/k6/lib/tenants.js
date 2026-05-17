// Tenant pool — VUs are pinned to one tenant so sessions don't cross.

const slugs = (__ENV.TENANT_SLUGS || 'acme,widgetco,studio')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);

export function tenantForVu(vu) {
  // Stable round-robin so VU 1 always hits the same tenant
  return slugs[(vu - 1) % slugs.length];
}

export function tenantBaseUrl(slug) {
  const root = (__ENV.PLATFORM_BASE || 'https://platform.localhost').replace(/\/$/, '');
  // Caddy wildcard routes <slug>.platform.localhost → tenant DB
  return root.replace('//', `//${slug}.`);
}

export const TENANT_LOGIN = __ENV.TENANT_LOGIN || 'admin';
export const TENANT_PASSWORD = __ENV.TENANT_PASSWORD || 'changeme';
