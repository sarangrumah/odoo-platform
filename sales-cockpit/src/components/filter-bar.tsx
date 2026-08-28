"use client";

// =============================================================================
// The global filter bar.
//
// State lives in the URL, not in React: every control writes a search param and
// navigates. That makes each view a shareable link and keeps the server
// components authoritative — no client-side cache to fall out of sync.
// =============================================================================

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useTransition } from "react";
import { monthToDate, type Extent } from "@/lib/filters";
import { dayLabel } from "@/lib/format";

export interface FilterOptions {
  stores: { id: number; name: string }[];
  categories: string[];
}

const PRESETS: { label: string; days: number | "mtd" | "all" }[] = [
  { label: "7 hari", days: 7 },
  { label: "30 hari", days: 30 },
  { label: "Bulan ini", days: "mtd" },
  { label: "Semua", days: "all" },
];

export function FilterBar({ options, extent }: { options: FilterOptions; extent: Extent }) {
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

  const set = useCallback(
    (key: string, value: string | null) => {
      const next = new URLSearchParams(params.toString());
      if (value) next.set(key, value);
      else next.delete(key);
      push(next);
    },
    [params, push],
  );

  const from = params.get("from") ?? extent.start;
  const to = params.get("to") ?? extent.end;
  const stores = (params.get("stores") ?? "").split(",").filter(Boolean);
  const categories = (params.get("categories") ?? "").split(",").filter(Boolean);
  const membership = params.get("membership") ?? "";
  const associate = params.get("associate") ?? "";

  const applyPreset = (days: number | "mtd" | "all") => {
    const next = new URLSearchParams(params.toString());
    if (days === "all") {
      next.delete("from");
      next.delete("to");
    } else if (days === "mtd") {
      // Month to date of the last day WITH DATA — the same window the Ringkasan
      // block reports, so the two never disagree.
      const mtd = monthToDate(extent);
      next.set("from", mtd.from);
      next.set("to", mtd.to);
    } else {
      // Anchored to the last day WITH DATA, not to today: the feed runs a day
      // or more behind, and "last 7 days" from today would come back empty.
      const end = new Date(`${extent.end}T00:00:00Z`);
      const start = new Date(end.getTime() - (days - 1) * 86_400_000);
      next.set("from", start.toISOString().slice(0, 10));
      next.set("to", extent.end);
    }
    push(next);
  };

  const clearAll = () => push(new URLSearchParams());

  const storeName = (id: string) =>
    options.stores.find((s) => String(s.id) === id)?.name ?? `Toko ${id}`;

  const activeChips: { key: string; label: string; onRemove: () => void }[] = [
    ...stores.map((id) => ({
      key: `store-${id}`,
      label: storeName(id),
      onRemove: () => set("stores", stores.filter((s) => s !== id).join(",") || null),
    })),
    ...categories.map((c) => ({
      key: `cat-${c}`,
      label: c,
      onRemove: () => set("categories", categories.filter((x) => x !== c).join(",") || null),
    })),
    ...(membership
      ? [
          {
            key: "membership",
            label: membership === "member" ? "Member" : "Non-member",
            onRemove: () => set("membership", null),
          },
        ]
      : []),
    ...(associate
      ? [{ key: "associate", label: associate, onRemove: () => set("associate", null) }]
      : []),
  ];

  return (
    <>
      <div className="filters" style={{ opacity: pending ? 0.6 : 1 }}>
        <div className="field">
          <label htmlFor="f-from">Dari</label>
          <input
            id="f-from"
            type="date"
            value={from}
            min={extent.start}
            max={to}
            onChange={(e) => set("from", e.target.value || null)}
          />
        </div>

        <div className="field">
          <label htmlFor="f-to">Sampai</label>
          <input
            id="f-to"
            type="date"
            value={to}
            min={from}
            max={extent.end}
            onChange={(e) => set("to", e.target.value || null)}
          />
        </div>

        <div className="field">
          <label>Preset</label>
          <div style={{ display: "flex", gap: 4 }}>
            {PRESETS.map((p) => (
              <button key={p.label} type="button" className="btn" onClick={() => applyPreset(p.days)}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label htmlFor="f-store">Toko</label>
          <select
            id="f-store"
            value=""
            onChange={(e) => {
              const v = e.target.value;
              if (v && !stores.includes(v)) set("stores", [...stores, v].join(","));
            }}
          >
            <option value="">Tambah toko…</option>
            {options.stores
              .filter((s) => !stores.includes(String(s.id)))
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-cat">Kategori</label>
          <select
            id="f-cat"
            value=""
            onChange={(e) => {
              const v = e.target.value;
              if (v && !categories.includes(v)) set("categories", [...categories, v].join(","));
            }}
          >
            <option value="">Tambah kategori…</option>
            {options.categories
              .filter((c) => !categories.includes(c))
              .map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="f-member">Keanggotaan</label>
          <select
            id="f-member"
            value={membership}
            onChange={(e) => set("membership", e.target.value || null)}
          >
            <option value="">Semua</option>
            <option value="member">Member</option>
            <option value="guest">Non-member</option>
          </select>
        </div>

        <button type="button" className="btn" onClick={clearAll}>
          Reset
        </button>
      </div>

      {activeChips.length > 0 && (
        <div className="filters" style={{ top: 105, paddingTop: 8, paddingBottom: 8 }}>
          <div className="chips">
            <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
              {dayLabel(from)} – {dayLabel(to)} ·
            </span>
            {activeChips.map((chip) => (
              <span key={chip.key} className="chip">
                {chip.label}
                <button type="button" aria-label={`Hapus filter ${chip.label}`} onClick={chip.onRemove}>
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
