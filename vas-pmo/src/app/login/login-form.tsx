"use client";

import { useActionState } from "react";

import { login, type LoginState } from "./actions";

export default function LoginForm({ next }: { next: string }) {
  const [state, formAction, pending] = useActionState<LoginState, FormData>(login, {});

  return (
    <main className="login-wrap">
      <div className="card login-card">
        <header>
          <div>
            <h2>VAS PMO</h2>
            <span className="eyebrow">Product Owner · Value-Added Services</span>
          </div>
        </header>
        <form action={formAction} className="body stackv">
          {state.error ? <p className="alert">{state.error}</p> : null}
          <input type="hidden" name="next" value={next} />
          <div>
            <label htmlFor="login">Email</label>
            <input id="login" name="login" type="text" autoComplete="username" required />
          </div>
          <div>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </div>
          <button className="btn pri" type="submit" disabled={pending}>
            {pending ? "Masuk…" : "Masuk"}
          </button>
          <p className="dim" style={{ fontSize: 12, margin: 0 }}>
            Akun yang sama dengan Odoo. Sesi disimpan di cookie httpOnly.
          </p>
        </form>
      </div>
    </main>
  );
}
