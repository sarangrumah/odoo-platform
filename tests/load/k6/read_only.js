// Smoke variant — read-only Odoo list views + dashboard.
// Used to validate stack reachability before the full mixed run.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { tenantForVu, tenantBaseUrl, TENANT_LOGIN, TENANT_PASSWORD } from './lib/tenants.js';
import { login } from './lib/auth.js';

export const options = {
  thresholds: {
    http_req_failed: ['rate<0.001'],
    http_req_duration: ['p(95)<3000', 'p(99)<5000'],
  },
};

export function setup() {
  // Reuse the same login per VU within a single run via init context.
  return {};
}

export default function () {
  const slug = tenantForVu(__VU);
  const base = tenantBaseUrl(slug);
  login(base, slug, TENANT_LOGIN, TENANT_PASSWORD);

  // Hit the main list views (partners, invoices, payslips, approval inbox)
  const targets = [
    `${base}/odoo/contacts`,
    `${base}/odoo/accounting`,
    `${base}/odoo/purchase`,
    `${base}/odoo/sales`,
    `${base}/web/dataset/call_kw`,
  ];
  for (const url of targets) {
    const r = http.get(url);
    check(r, { 'status < 500': (res) => res.status < 500 });
    sleep(0.5);
  }
}
