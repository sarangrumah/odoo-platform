// Main load suite — 60% read / 30% write / 10% report.
// Ramped: 0 → 500 VUs over 5min, hold 20min, ramp down 5min = 30min total.

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';
import { tenantForVu, tenantBaseUrl, TENANT_LOGIN, TENANT_PASSWORD } from './lib/tenants.js';
import { login } from './lib/auth.js';

// --- Custom metrics ---
const readDuration = new Trend('read_duration', true);
const writeDuration = new Trend('write_duration', true);
const reportDuration = new Trend('report_duration', true);
const businessErrors = new Counter('business_errors');
const writeSuccess = new Rate('write_success_rate');

// --- Test options ---
export const options = {
  stages: [
    { duration: '5m', target: 500 },   // ramp up
    { duration: '20m', target: 500 },  // sustain
    { duration: '5m', target: 0 },     // ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.001'],          // < 0.1% errors
    http_req_duration: ['p(95)<3000', 'p(99)<5000'],
    read_duration: ['p(95)<2000'],
    write_duration: ['p(95)<4000'],
    report_duration: ['p(95)<8000'],
    write_success_rate: ['rate>0.999'],
  },
};

// --- VU lifecycle ---
export default function () {
  const slug = tenantForVu(__VU);
  const base = tenantBaseUrl(slug);

  // Login once per VU iteration (k6 keeps cookie jar)
  login(base, slug, TENANT_LOGIN, TENANT_PASSWORD);

  // Weighted action selection per iteration
  const roll = Math.random();
  if (roll < 0.6) {
    readPhase(base);
  } else if (roll < 0.9) {
    writePhase(base);
  } else {
    reportPhase(base);
  }
  sleep(1);
}

// --- Phases ---

function readPhase(base) {
  group('read', () => {
    const t0 = Date.now();
    const r1 = http.get(`${base}/odoo/contacts`);
    const r2 = http.get(`${base}/odoo/accounting`);
    const r3 = http.get(`${base}/odoo/purchase`);
    readDuration.add(Date.now() - t0);

    [r1, r2, r3].forEach((res) => {
      const ok = check(res, { 'read status<500': (r) => r.status < 500 });
      if (!ok) businessErrors.add(1);
    });
  });
}

function writePhase(base) {
  group('write', () => {
    const t0 = Date.now();
    // Create a draft vendor bill via JSON-RPC call_kw on account.move
    const body = JSON.stringify({
      jsonrpc: '2.0',
      method: 'call',
      params: {
        model: 'account.move',
        method: 'create',
        args: [{
          move_type: 'in_invoice',
          partner_id: 1,  // assume seeded partner
          invoice_line_ids: [[0, 0, {
            name: 'k6 load line',
            quantity: 1,
            price_unit: 100000,
          }]],
        }],
        kwargs: {},
      },
    });
    const r = http.post(`${base}/web/dataset/call_kw`, body, {
      headers: { 'Content-Type': 'application/json' },
    });
    writeDuration.add(Date.now() - t0);
    const ok = check(r, {
      'write returned 200': (res) => res.status === 200,
      'write body ok': (res) => {
        try {
          return !res.json().error;
        } catch { return false; }
      },
    });
    writeSuccess.add(ok ? 1 : 0);
    if (!ok) businessErrors.add(1);
  });
}

function reportPhase(base) {
  group('report', () => {
    const t0 = Date.now();
    // Trigger a heavier endpoint — accounting trial balance
    const body = JSON.stringify({
      jsonrpc: '2.0',
      method: 'call',
      params: {
        model: 'account.move.line',
        method: 'read_group',
        args: [[], ['debit:sum', 'credit:sum'], ['account_id']],
        kwargs: {},
      },
    });
    const r = http.post(`${base}/web/dataset/call_kw`, body, {
      headers: { 'Content-Type': 'application/json' },
    });
    reportDuration.add(Date.now() - t0);
    const ok = check(r, { 'report status 200': (res) => res.status === 200 });
    if (!ok) businessErrors.add(1);
  });
}

// --- Teardown summary stamp ---
export function handleSummary(data) {
  const errors = data.metrics.business_errors ? data.metrics.business_errors.values.count : 0;
  const reqs = data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0;
  console.log(`\n=== Load run summary ===`);
  console.log(`Total requests: ${reqs}`);
  console.log(`Business errors: ${errors}`);
  console.log(`Effective error rate: ${reqs ? (errors / reqs * 100).toFixed(4) : 0}%`);
  return {
    'summary.json': JSON.stringify(data, null, 2),
  };
}
