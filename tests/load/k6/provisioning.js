// Stress the tenant-orchestrator with parallel POST /v1/tenants.
// Verifies the provisioning path holds under 10 concurrent creations.

import http from 'k6/http';
import { check } from 'k6';
import { signCustom } from './lib/hmac.js';

const ORCHESTRATOR_URL =
  __ENV.ORCHESTRATOR_URL || 'http://localhost:18091';
const SECRET = __ENV.ORCHESTRATOR_SHARED_SECRET;

export const options = {
  vus: 10,
  iterations: 10,         // each VU provisions once
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<60000'],   // provisioning is slow (DB create + module install)
  },
};

export default function () {
  if (!SECRET) {
    throw new Error('ORCHESTRATOR_SHARED_SECRET env var required');
  }
  const slug = `loadtest${__VU}${Date.now() % 100000}`;
  const body = JSON.stringify({
    slug,
    display_name: `Load Test ${slug}`,
    plan_tier: 'trial',
    contact_email: `ops@${slug}.test`,
    features: { pajakku: false },
  });
  const { header } = signCustom(SECRET, body);
  const r = http.post(`${ORCHESTRATOR_URL}/v1/tenants`, body, {
    headers: {
      'Content-Type': 'application/json',
      'X-Custom-Signature': header,
      'X-Custom-Actor': 'k6-loadtest',
    },
  });
  check(r, {
    'provision 201': (res) => res.status === 201,
    'provision returns admin_password': (res) => {
      try { return Boolean(res.json().admin_password); } catch { return false; }
    },
  });
}
