// Browser-side API client for hub-portal.
// All calls hit the local Express proxy (server/index.mjs) which handles
// HMAC signing for orchestrator and JSON-RPC plumbing for Odoo.
//
// Schema parity with tenant-orchestrator /v1/* and Odoo addons:
//   - onboarding.journey
//   - brd.recommendation
//   - tenant.vps
//   - custom.hub.module.{catalog,deployment}
//   - dev.cycle, dev.cycle.pr
//
// TODO: tighten types — most payloads typed as any for now.

export interface ApiError extends Error {
  status?: number;
  detail?: string;
}

async function http<T = any>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  body?: any,
): Promise<T> {
  const resp = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body == null ? undefined : JSON.stringify(body),
    credentials: 'include',
  });
  const text = await resp.text();
  if (!resp.ok) {
    const err: ApiError = new Error(`${method} ${path} -> ${resp.status}`);
    err.status = resp.status;
    err.detail = text.slice(0, 500);
    throw err;
  }
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

// JSON-RPC helper for Odoo calls (proxied via /api/odoo/jsonrpc).
async function jsonrpc<T = any>(
  model: string,
  method: string,
  args: any[] = [],
  kwargs: Record<string, any> = {},
): Promise<T> {
  return http<T>('POST', '/api/odoo/jsonrpc', { model, method, args, kwargs });
}

// ---------------------------------------------------------------------------
// Auth — proxied to Odoo /web/session/* via server/index.mjs.
// ---------------------------------------------------------------------------
export interface AuthUser {
  uid: number;
  name: string;
  login: string;
}

export interface LoginResponse extends AuthUser {
  ok: true;
}

export const auth = {
  login: (email: string, password: string) =>
    http<LoginResponse>('POST', '/api/auth/login', { email, password }),
  logout: () => http<{ ok: true }>('POST', '/api/auth/logout'),
  me: () => http<AuthUser>('GET', '/api/auth/me'),
};

// ---------------------------------------------------------------------------
// Intake (Track G)
// ---------------------------------------------------------------------------
export interface IntakePayload {
  company_name: string;
  contact_email: string;
  contact_phone: string;
  npwp?: string;
  bank_name?: string;
  bank_account?: string;
  company_logo_base64?: string;
  vertical_target: string;
  modules_wishlist: string[];
  business_process_narrative: string;
  brd_file_base64s?: string[];
  source?: 'public' | 'internal_ba';
}

export interface IntakeResponse {
  token: string;
  status_url: string;
  journey_id?: number | null;
}

export const submitIntake = (payload: IntakePayload) =>
  http<IntakeResponse>('POST', '/api/intake/submit', payload);

export const getIntakeStatus = (token: string) =>
  http<any>('GET', `/api/intake/status/${encodeURIComponent(token)}`);

// ---------------------------------------------------------------------------
// Onboarding journeys (Track C)
// ---------------------------------------------------------------------------
export interface JourneyFilters {
  stage?: string;
  ba_user_id?: number;
  vertical?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export const listJourneys = (filters: JourneyFilters = {}) => {
  const domain: any[] = [];
  if (filters.stage) domain.push(['stage', '=', filters.stage]);
  if (filters.ba_user_id) domain.push(['ba_user_id', '=', filters.ba_user_id]);
  if (filters.vertical) domain.push(['vertical_target', '=', filters.vertical]);
  if (filters.search) domain.push(['partner_name', 'ilike', filters.search]);
  return jsonrpc<any[]>('onboarding.journey', 'search_read', [domain], {
    fields: [
      'id',
      'name',
      'partner_name',
      'vertical_target',
      'stage',
      'mandays_estimate',
      'ba_user_id',
      'target_go_live',
      'progress_pct',
      'token',
    ],
    limit: filters.limit ?? 200,
    offset: filters.offset ?? 0,
    order: 'create_date desc',
  });
};

export const getJourney = (id: number) =>
  jsonrpc<any[]>('onboarding.journey', 'read', [[id]], {});

export const updateJourneyStage = (id: number, stage: string) =>
  jsonrpc<boolean>('onboarding.journey', 'write', [[id], { stage }]);

export const listRecommendations = (journeyId: number) =>
  jsonrpc<any[]>(
    'brd.recommendation',
    'search_read',
    [[['journey_id', '=', journeyId]]],
    {
      fields: [
        'id',
        'name',
        'severity',
        'category',
        'rationale',
        'cross_vertical_impact_json',
        'estimate_md',
        'status',
      ],
      limit: 200,
    },
  );

// ---------------------------------------------------------------------------
// VPS (Track E, orchestrator + Odoo)
// ---------------------------------------------------------------------------
export const listVps = () => http<any[]>('GET', '/api/vps');
export const getVps = (id: number) => http<any>('GET', `/api/vps/${id}`);
export const registerVps = (payload: any) =>
  http<any>('POST', '/api/vps/register', payload);
export const bootstrapVps = (id: number) =>
  http<any>('POST', `/api/vps/${id}/bootstrap`);
export const deployStack = (vpsId: number, env: string) =>
  http<any>('POST', `/api/vps/${vpsId}/deploy`, { env });

// ---------------------------------------------------------------------------
// Module deployments (Track H)
// ---------------------------------------------------------------------------
export const listModuleCatalog = () =>
  jsonrpc<any[]>('custom.hub.module.catalog', 'search_read', [[]], {
    fields: ['id', 'name', 'technical_name', 'category', 'version', 'description', 'is_canary_enabled'],
    limit: 500,
  });

export const listDeployments = (filters: { tenant_id?: number; module_id?: number } = {}) => {
  const domain: any[] = [];
  if (filters.tenant_id) domain.push(['tenant_id', '=', filters.tenant_id]);
  if (filters.module_id) domain.push(['module_id', '=', filters.module_id]);
  return jsonrpc<any[]>('custom.hub.module.deployment', 'search_read', [domain], {
    fields: [
      'id',
      'name',
      'module_id',
      'tenant_id',
      'env',
      'state',
      'canary_phase',
      'deployed_at',
      'rollback_to',
    ],
    limit: 200,
    order: 'deployed_at desc',
  });
};

export const createDeployment = (payload: any) =>
  jsonrpc<number>('custom.hub.module.deployment', 'create', [payload]);

// ---------------------------------------------------------------------------
// Dev cycles (Track H)
// ---------------------------------------------------------------------------
export const listDevCycles = (filters: { state?: string; assignee_id?: number } = {}) => {
  const domain: any[] = [];
  if (filters.state) domain.push(['state', '=', filters.state]);
  if (filters.assignee_id) domain.push(['assignee_id', '=', filters.assignee_id]);
  return jsonrpc<any[]>('dev.cycle', 'search_read', [domain], {
    fields: [
      'id',
      'name',
      'state',
      'assignee_id',
      'estimate_md',
      'pr_count',
      'open_pr_count',
      'merged_pr_count',
      'ci_status',
      'journey_id',
    ],
    limit: 300,
    order: 'priority desc, write_date desc',
  });
};

export const createDevCycle = (payload: any) =>
  jsonrpc<number>('dev.cycle', 'create', [payload]);

export const listDevCyclePrs = (cycleId: number) =>
  jsonrpc<any[]>('dev.cycle.pr', 'search_read', [[['cycle_id', '=', cycleId]]], {
    fields: ['id', 'name', 'url', 'state', 'ci_status', 'merged_at'],
    limit: 100,
  });

// ---------------------------------------------------------------------------
// Backups
// ---------------------------------------------------------------------------
export const replicateBackup = (backupId: number, target: string) =>
  http<any>('POST', `/api/backups/${backupId}/replicate`, { target });

// ---------------------------------------------------------------------------
// Tenants / Users / Monitoring / Costs / Audit (existing pages)
// ---------------------------------------------------------------------------
export const health = () => http<any>('GET', '/api/health');
export const listTenants = () => http<any[]>('GET', '/api/tenants');
export const getTenant = (slug: string) => http<any>('GET', `/api/tenants/${slug}`);
export const listUsers = () => http<any[]>('GET', '/api/users');
export const getMetrics = () => http<any>('GET', '/api/monitoring/metrics');
export const getCosts = () => http<any>('GET', '/api/costs');
export const listAudit = (limit = 100) =>
  http<any[]>('GET', `/api/audit?limit=${limit}`);
export const listDocuments = () => http<any[]>('GET', '/api/documents');

// Back-compat shortcuts used by user's existing .jsx pages.
const monitoring = () => http<any>('GET', '/api/monitoring');
const costs = () => http<any>('GET', '/api/costs');
const users = () => http<any[]>('GET', '/api/users');
const audit = () => http<any[]>('GET', '/api/audit');
const documents = () => http<any[]>('GET', '/api/documents');

export const api = {
  // legacy aliases (jsx pages)
  health,
  listTenants,
  getTenant,
  monitoring,
  costs,
  users,
  audit,
  documents,
  // new (tsx pages)
  auth,
  submitIntake,
  getIntakeStatus,
  listJourneys,
  getJourney,
  updateJourneyStage,
  listRecommendations,
  listVps,
  getVps,
  registerVps,
  bootstrapVps,
  deployStack,
  listModuleCatalog,
  listDeployments,
  createDeployment,
  listDevCycles,
  createDevCycle,
  listDevCyclePrs,
  replicateBackup,
  listUsers,
  getMetrics,
  getCosts,
  listAudit,
  listDocuments,
};

export default api;
