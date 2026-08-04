"use client";

import { useActionState, useOptimistic, useState } from "react";

import { moveStage, type StageActionState } from "./actions";

interface Stage {
  id: number;
  name: string;
  code: string;
  is_hold: boolean;
}

/**
 * Optimistic stage move.
 *
 * Odoo round-trips in 200–400 ms, which is enough to make a click feel unacknowledged. So
 * the new stage is shown the moment it is submitted and rolled back by the server's answer
 * if the transition was refused — the rules still live in Odoo, this only removes the wait.
 */
export default function StageForm({
  taskId,
  stages,
  currentCode,
  currentStageName,
}: {
  taskId: number;
  stages: Stage[];
  currentCode: string;
  currentStageName: string;
}) {
  const [state, formAction, pending] = useActionState<StageActionState, FormData>(moveStage, {});
  const [choice, setChoice] = useState(currentCode);
  const [optimisticStage, setOptimisticStage] = useOptimistic(
    currentStageName,
    (_current: string, next: string) => next,
  );

  const selected = stages.find((stage) => stage.code === choice);
  const needsReason = Boolean(selected?.is_hold);

  return (
    <form
      action={(formData: FormData) => {
        setOptimisticStage(selected?.name ?? currentStageName);
        return formAction(formData);
      }}
      className="stackv"
    >
      {state.error ? <p className="alert">{state.error}</p> : null}
      {state.message ? (
        <p className="pill ok" style={{ padding: "7px 10px" }}>
          {state.message}
        </p>
      ) : null}

      <div className="row">
        <span className="eyebrow">Stage sekarang</span>
        <span className={`pill acc ${pending ? "pending" : ""}`}>{optimisticStage}</span>
      </div>

      <input type="hidden" name="task_id" value={taskId} />
      <div>
        <label htmlFor="stage_code">Pindah ke stage</label>
        <select
          id="stage_code"
          name="stage_code"
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
        >
          {stages.map((stage) => (
            <option key={stage.id} value={stage.code}>
              {stage.name}
            </option>
          ))}
        </select>
      </div>

      {needsReason ? (
        <div>
          <label htmlFor="hold_reason">Alasan hold — wajib</label>
          <input
            id="hold_reason"
            name="hold_reason"
            type="text"
            required
            placeholder="mis. menunggu data toko dari brand"
          />
        </div>
      ) : (
        <input type="hidden" name="hold_reason" value="" />
      )}

      <button className="btn pri" type="submit" disabled={pending || choice === currentCode}>
        {pending ? "Menyimpan…" : "Simpan stage"}
      </button>
    </form>
  );
}
