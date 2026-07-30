"use client";

import { useActionState } from "react";

import type { SettingsState } from "./actions";

/**
 * One editable row = one form.
 *
 * Deliberately not a live-saving grid: master data changes behaviour for the whole team
 * and every write is audited, so an explicit Save (and a visible result) is the honest
 * interaction. The row dims while the write is in flight.
 */
export default function RowForm({
  action,
  children,
  id,
}: {
  action: (prev: SettingsState, formData: FormData) => Promise<SettingsState>;
  children: React.ReactNode;
  id: number;
}) {
  const [state, formAction, pending] = useActionState<SettingsState, FormData>(action, {});

  return (
    <form action={formAction} className={pending ? "pending" : undefined}>
      <input type="hidden" name="id" value={id} />
      <div className="row" style={{ gap: 10 }}>
        {children}
        <button className="btn" type="submit" disabled={pending}>
          {pending ? "…" : "Simpan"}
        </button>
      </div>
      {state.error ? (
        <p className="alert" style={{ marginTop: 8, fontSize: 12 }}>
          {state.error}
        </p>
      ) : null}
      {state.message ? (
        <p className="pill ok" style={{ marginTop: 8, padding: "5px 8px" }}>
          {state.message}
        </p>
      ) : null}
    </form>
  );
}
