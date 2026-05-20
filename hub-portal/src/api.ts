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

// Public-intake inbox: submissions that haven't been promoted yet.
export const listPublicSubmissions = (status: string = 'submitted') =>
  jsonrpc<any[]>('onboarding.public.submission', 'search_read', [[['status', '=', status]]], {
    fields: ['id', 'name', 'status', 'public_token', 'submitted_at', 'raw_payload_json', 'journey_id'],
    limit: 200,
    order: 'submitted_at desc',
  });

export const promoteSubmission = (id: number) =>
  jsonrpc<any>('onboarding.public.submission', 'action_promote_to_journey', [[id]], {});

export const rejectSubmission = (id: number) =>
  jsonrpc<boolean>('onboarding.public.submission', 'action_reject', [[id]], {});

export const listJourneys = (filters: JourneyFilters = {}) => {
  const domain: any[] = [];
  if (filters.stage) domain.push(['stage', '=', filters.stage]);
  if (filters.ba_user_id) domain.push(['ba_id', '=', filters.ba_user_id]);
  if (filters.search) {
    // Search both journey name and the linked partner's name.
    domain.push('|', ['name', 'ilike', filters.search], ['partner_id.name', 'ilike', filters.search]);
  }
  return jsonrpc<any[]>('onboarding.journey', 'search_read', [domain], {
    fields: [
      'id',
      'name',
      'partner_id',
      'stage',
      'mandays_estimate',
      'ba_id',
      'target_go_live',
      'progress_pct',
      'public_status_token',
      'company_profile_json',
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

// brd.recommendation lives on a brd.document; filter via journey -> document chain.
export const listRecommendations = (journeyId: number) =>
  jsonrpc<any[]>(
    'brd.recommendation',
    'search_read',
    [[['document_id.journey_id', '=', journeyId]]],
    {
      fields: [
        'id',
        'name',
        'scope',
        'severity',
        'estimated_md',
        'state',
        'justification',
        'breaking_change',
        'compat_strategy',
        'impact_severity',
        'cross_vertical_impact_json',
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
    fields: ['id', 'module_name', 'category', 'maturity', 'version', 'summary',
             'models_own_count', 'models_inherit_count', 'deployment_count', 'last_scanned'],
    limit: 500,
    order: 'category, module_name',
  });

export const listDeployments = (filters: { tenant_id?: number; catalog_id?: number } = {}) => {
  const domain: any[] = [];
  if (filters.tenant_id) domain.push(['tenant_id', '=', filters.tenant_id]);
  if (filters.catalog_id) domain.push(['catalog_id', '=', filters.catalog_id]);
  return jsonrpc<any[]>('custom.hub.module.deployment', 'search_read', [domain], {
    fields: [
      'id',
      'catalog_id',
      'tenant_id',
      'deploy_mode',
      'state',
      'canary_phase',
      'requested_at',
      'started_at',
      'completed_at',
      'rollback_snapshot_id',
      'healthcheck_passed',
      'error_message',
    ],
    limit: 200,
    order: 'requested_at desc',
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
      'env_progress',
      'assignee_id',
      'estimate_md',
      'actual_md',
      'branch_name',
      'repo_url',
      'journey_id',
      'brd_recommendation_id',
      'module_target_id',
      'pr_count',
      'deployment_count',
      'created_at',
    ],
    limit: 300,
    order: 'write_date desc',
  });
};

export const createDevCycle = (payload: any) =>
  jsonrpc<number>('dev.cycle', 'create', [payload]);

export const listDevCyclePrs = (cycleId: number) =>
  jsonrpc<any[]>('dev.cycle.pr', 'search_read', [[['cycle_id', '=', cycleId]]], {
    fields: ['id', 'provider', 'pr_number', 'pr_url', 'state', 'ci_status',
             'reviewers', 'merged_at', 'merged_by', 'last_synced_at'],
    limit: 100,
    order: 'last_synced_at desc',
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
