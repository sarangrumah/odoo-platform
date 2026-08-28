// =============================================================================
// The orchestrator: question in, answer out.
//
// Order matters here. Questions the data cannot answer are caught FIRST, before
// the matcher gets a chance to half-match one of them onto a skill — "berapa
// PPN masukan bulan lalu" contains "bulan lalu" and "berapa", and would
// otherwise score as a payables question and return a confident rupiah figure
// to somebody who asked about tax. On an accounting dashboard that is the worst
// failure this file can have, because somebody may act on it.
// =============================================================================

import { catalog } from "@/lib/agent/catalog";
import { detectUnanswerable, matchIntent } from "@/lib/agent/intent";
import { extractSlots } from "@/lib/agent/slots";
import { SKILL_BY_ID, type SkillResult } from "@/lib/agent/skills";

export type AnswerSource = "catalog" | "claude" | "refused" | "unmatched";

export interface Answer extends SkillResult {
  source: AnswerSource;
  skill?: string;
  /** Example questions, offered when we could not answer. */
  suggestions?: string[];
}

/** Shown on first open and whenever the assistant has to give up. */
export const SUGGESTIONS = [
  "Berapa hutang yang lewat jatuh tempo?",
  "Apa yang perlu saya kerjakan hari ini?",
  "Open item mana yang paling tua?",
  "Posisi GR/IR berapa?",
  "Apakah buku bisa ditutup?",
];

export interface AskContext {
  companies: number[];
  /** Today, supplied by the caller so nothing here reads the wall clock. */
  today: string;
  /** The cut-off currently on screen; used when the question names no period. */
  asOf: string;
}

export interface AskOutcome {
  answer: Answer;
  /** The cut-off the answer was computed at — echoed for the audit log. */
  asOf: string;
}

/**
 * Try to answer without a model.
 *
 * Returns null only when the sentence is a legitimate question that the
 * catalogue does not cover — that is the one case worth escalating.
 */
export async function answerFromCatalog(
  question: string,
  ctx: AskContext,
): Promise<AskOutcome | null> {
  const refusal = detectUnanswerable(question);
  if (refusal) {
    return {
      asOf: ctx.asOf,
      answer: { source: "refused", headline: refusal, suggestions: SUGGESTIONS.slice(0, 3) },
    };
  }

  const cat = await catalog();
  const slots = extractSlots(question, ctx.today, cat);

  const match = matchIntent(question, {
    hasAccount: slots.accountIds.length > 0,
    hasPartner: slots.partnerIds.length > 0,
  });
  if (!match) return null;

  const skill = SKILL_BY_ID.get(match.skill);
  if (!skill) return null;

  // A question that names no period is answered at whatever cut-off the reader
  // is looking at, not silently at today — otherwise the assistant and the page
  // behind it would quietly disagree.
  const asOf = slots.asOf?.asOf ?? ctx.asOf;

  const result = await skill.run({
    asOf,
    companies: ctx.companies,
    accountIds: slots.accountIds,
    partnerIds: slots.partnerIds,
    limit: slots.limit,
    asOfLabel: slots.asOf?.label,
    todayIso: ctx.today,
  });

  const periodNote = slots.asOf
    ? undefined
    : `Dihitung pada tanggal potong yang sedang dipilih (${asOf}). Sebutkan periodenya untuk mengubah.`;

  return {
    asOf,
    answer: {
      ...result,
      source: "catalog",
      skill: skill.id,
      note: [result.note, periodNote].filter(Boolean).join(" ") || undefined,
    },
  };
}

/** The answer given when neither the catalogue nor the fallback can help. */
export function giveUp(): Answer {
  return {
    source: "unmatched",
    headline:
      "Maaf, saya belum bisa menjawab itu. Saya hanya membaca buku besar, rekening koran dan " +
      "run kliring POS di prd_levis_begbal — bukan penjualan, pajak, stok, atau anggaran.",
    suggestions: SUGGESTIONS,
  };
}
