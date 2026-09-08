// =============================================================================
// The orchestrator: question in, answer out.
//
// Order matters here. Questions the data cannot answer are caught FIRST, before
// the matcher gets a chance to half-match one of them onto a skill — "berapa
// margin bulan lalu" contains "bulan lalu" and "berapa", and would otherwise
// score as a KPI question and return an omzet figure to somebody who asked
// about profit. That is the single worst failure this file can have.
// =============================================================================

import { catalog } from "@/lib/agent/catalog";
import { detectUnanswerable, matchIntent } from "@/lib/agent/intent";
import { applySlots, extractSlots } from "@/lib/agent/slots";
import { SKILL_BY_ID, type SkillResult } from "@/lib/agent/skills";
import { dayLabel } from "@/lib/format";
import type { Extent, Filters } from "@/lib/filters";

export type AnswerSource = "catalog" | "claude" | "refused" | "unmatched";

export interface Answer extends SkillResult {
  source: AnswerSource;
  skill?: string;
  /** Example questions, offered when we could not answer. */
  suggestions?: string[];
}

/** Shown on first open and whenever the assistant has to give up. */
export const SUGGESTIONS = [
  "Penjualan bulan lalu berapa?",
  "Toko mana yang paling tinggi?",
  "Produk terlaris minggu ini",
  "Ada yang perlu saya perhatikan?",
  "Data sampai tanggal berapa?",
];

export interface AskOutcome {
  answer: Answer;
  /** Filters the answer was computed under — echoed for the audit log. */
  filters: Filters;
}

/**
 * Try to answer without a model.
 *
 * Returns null only when the sentence is a legitimate question that the
 * catalogue does not cover — that is the one case worth escalating.
 */
export async function answerFromCatalog(
  question: string,
  base: Filters,
  extent: Extent,
): Promise<AskOutcome | null> {
  const refusal = detectUnanswerable(question);
  if (refusal) {
    return {
      filters: base,
      answer: { source: "refused", headline: refusal, suggestions: SUGGESTIONS.slice(0, 3) },
    };
  }

  const slots = extractSlots(question, extent, await catalog());
  if (slots.outOfRange) {
    return {
      filters: base,
      answer: {
        source: "refused",
        headline:
          `Tidak ada data untuk periode itu. Data POS prd_levis_begbal hanya mencakup ` +
          `${dayLabel(extent.start)} sampai ${dayLabel(extent.end)}.`,
      },
    };
  }

  const match = matchIntent(question, {
    hasStore: slots.storeIds.length > 0,
    hasRange: slots.range !== null,
  });
  if (!match) return null;

  const skill = SKILL_BY_ID.get(match.skill);
  if (!skill) return null;

  const filters = applySlots(base, slots);
  const result = await skill.run({
    filters,
    extent,
    limit: skill.slots.includes("limit") ? slots.limit : undefined,
  });

  // A recognised period that fell partly outside the data would otherwise be
  // reported as a plain number for a window the reader did not ask about.
  const clippedNote =
    slots.range?.clipped
      ? `Rentang dipangkas ke data yang tersedia (${dayLabel(extent.start)} – ${dayLabel(extent.end)}).`
      : undefined;

  return {
    filters,
    answer: {
      ...result,
      source: "catalog",
      skill: skill.id,
      note: [result.note, clippedNote].filter(Boolean).join(" ") || undefined,
    },
  };
}

/** The answer given when neither the catalogue nor the fallback can help. */
export function giveUp(extent: Extent): Answer {
  return {
    source: "unmatched",
    headline:
      "Maaf, saya belum bisa menjawab itu. Saya hanya membaca data POS Levi's di prd_levis_begbal " +
      `(${dayLabel(extent.start)} – ${dayLabel(extent.end)}).`,
    suggestions: SUGGESTIONS,
  };
}
