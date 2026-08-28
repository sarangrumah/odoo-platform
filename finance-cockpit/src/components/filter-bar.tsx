"use client";

// =============================================================================
// The global filter bar, finance edition.
//
// One control dominates: the cut-off. Finance questions are almost always "as
// of when", and every figure on every page is measured at this date — so it is
// the first thing on the bar and it is never hidden behind a menu.
//
// State lives in the URL, not in React, so each view is a shareable link. That
// matters more here than on the sales side: "the number I am looking at" has to
// be reproducible by whoever the accountant sends it to.
// =============================================================================

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useTransition } from "react";

import { startOfMonth } from "@/lib/finance-filters";
import { dayLabel } from "@/lib/format";

export interface FinanceFilterOptions {
  /** The company's lock dates, offered as one-click cut-offs. */
  fiscalyearLockDate: string | null;
  /** Last day that carries any posted line — the natural "now". */
  lastPostedDate: string | null;
  today: string;
}

export function FilterBar({ options }: { options: FinanceFilterOptions }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  const params = useMemo(() => new URLSearchParams(searchParams.toString()), [searchParams]);

  const push = useCallback(
    (next: URLSearchParams) => {
      const qs = next.toString();
      startTransition(() => router.push(qs ? `${pathname}?${qs}` : pathname));
    },
    [pathname, router],
  );

  const setParam = useCallback(
    (key: string, value: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (value) next.set(key, value);
      else next.delete(key);
      // The movement window is derived from the cut-off unless it was set
      // explicitly; moving the cut-off must not leave `from` stranded in a
      // month the user is no longer looking at.
      if (key === "asOf" && !params.get("from")) next.delete("from");
      push(next);
    },
    [params, push],
  );

  const asOf = params.get("asOf") ?? options.today;
  const from = params.get("from") ?? startOfMonth(asOf);

  const presets: { label: string; value: string | null; title: string }[] = [
    { label: "Hari ini", value: null, title: options.today },
    {
      label: "Akhir bulan lalu",
      value: previousMonthEnd(options.today),
      title: previousMonthEnd(options.today),
    },
  ];

  if (options.fiscalyearLockDate) {
    presets.push({
      label: "Tanggal kunci buku",
      value: options.fiscalyearLockDate,
      title: `fiscalyear_lock_date = ${options.fiscalyearLockDate}`,
    });
  }
  if (options.lastPostedDate) {
    presets.push({
      label: "Baris terakhir",
      value: options.lastPostedDate,
      title: `Baris terposting terakhir: ${options.lastPostedDate}`,
    });
  }

  return (
    <div className="filters" data-pending={pending ? "1" : undefined}>
      <div className="field">
        <label htmlFor="asOf">Per tanggal</label>
        <input
          id="asOf"
          type="date"
          value={asOf}
          onChange={(e) => setParam("asOf", e.target.value || null)}
        />
      </div>

      <div className="field">
        <label htmlFor="from">Mutasi sejak</label>
        <input
          id="from"
          type="date"
          value={from}
          max={asOf}
          onChange={(e) => setParam("from", e.target.value || null)}
        />
      </div>

      <div className="chips" role="group" aria-label="Tanggal potong cepat">
        {presets.map((p) => (
          <button
            key={p.label}
            type="button"
            className="chip"
            title={p.title}
            aria-pressed={asOf === (p.value ?? options.today)}
            onClick={() => setParam("asOf", p.value)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
        Semua angka diukur per {dayLabel(asOf)}
        {pending ? " · memuat…" : ""}
      </span>
    </div>
  );
}

/** Last day of the month before the one `iso` falls in. */
function previousMonthEnd(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 0)).toISOString().slice(0, 10);
}
