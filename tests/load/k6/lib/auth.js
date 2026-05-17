// Odoo session login — POST /web/session/authenticate, capture cookie jar.

import http from 'k6/http';
import { check, fail } from 'k6';

export function login(baseUrl, dbName, login, password) {
  const res = http.post(
    `${baseUrl}/web/session/authenticate`,
    JSON.stringify({
      jsonrpc: '2.0',
      params: { db: dbName, login, password },
    }),
    { headers: { 'Content-Type': 'application/json' } },
  );
  const ok = check(res, {
    'login 200': (r) => r.status === 200,
    'login has session': (r) => {
      try {
        const body = r.json();
        return body && body.result && body.result.uid;
      } catch {
        return false;
      }
    },
  });
  if (!ok) {
    fail(`Login to ${baseUrl} failed: ${res.status} ${res.body && r.body.substring && r.body.substring(0, 200)}`);
  }
  return res.cookies;
}
