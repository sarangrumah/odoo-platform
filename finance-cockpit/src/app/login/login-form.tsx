"use client";

// React 18.3 here, so the hook is `useFormState` from react-dom — the React 19
// name `useActionState` does not exist in this version.
import { useFormState, useFormStatus } from "react-dom";
import { login, type LoginState } from "./actions";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className="btn primary" disabled={pending} style={{ width: "100%" }}>
      {pending ? "Memeriksa…" : "Masuk"}
    </button>
  );
}

export function LoginForm({ next }: { next: string }) {
  const [state, formAction] = useFormState<LoginState, FormData>(login, {});

  return (
    <form action={formAction} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <input type="hidden" name="next" value={next} />

      <div className="field">
        <label htmlFor="login">Login Odoo</label>
        <input id="login" name="login" autoComplete="username" autoFocus required />
      </div>

      <div className="field">
        <label htmlFor="password">Kata sandi</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required />
      </div>

      {state.error && (
        <div className="note" style={{ borderLeftColor: "var(--critical)" }} role="alert">
          {state.error}
        </div>
      )}

      <SubmitButton />
    </form>
  );
}
