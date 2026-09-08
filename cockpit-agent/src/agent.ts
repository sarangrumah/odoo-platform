// =============================================================================
// The escalation loop.
//
// This uses the Anthropic SDK's tool runner, NOT the Claude Agent SDK. The
// distinction is the whole security story: the tool runner ships no built-in
// tools — no file read, no bash, no web fetch — so the catalogue below is not a
// permitted subset of a larger toolbox, it is the entire toolbox. There is
// nothing here to disable and nothing to accidentally re-enable.
//
// Claude's job is narrow: read an Indonesian sentence, pick a catalogued
// question, fill in its arguments, and say the answer in one or two sentences.
// =============================================================================

import Anthropic from "@anthropic-ai/sdk";
import type { BetaRunnableTool } from "@anthropic-ai/sdk/lib/tools/BetaRunnableTool";

import { describeSkills, runSkill, type Filters, type SkillResult, type SkillSpec } from "./cockpit.js";

const MODEL = process.env.COCKPIT_AGENT_MODEL ?? "claude-opus-5";
const EFFORT = (process.env.COCKPIT_AGENT_EFFORT ?? "low") as "low" | "medium" | "high";
const MAX_ITERATIONS = 6;
const TIMEOUT_MS = 45_000;

const client = new Anthropic();

function systemPrompt(skills: SkillSpec[], filters: Filters, extent: { start: string; end: string }): string {
  return [
    "Kamu asisten data untuk Levi's Sales Cockpit.",
    "",
    "Satu-satunya sumber pengetahuanmu adalah tool yang tersedia. Tool itu membaca",
    "database POS prd_levis_begbal dan tidak ada yang lain. Kamu TIDAK punya akses ke",
    "internet, file, maupun pengetahuan umum tentang Levi's, dan kamu tidak boleh",
    "menjawab dari ingatan.",
    "",
    `Data POS tersedia ${extent.start} sampai ${extent.end}. Di luar rentang itu tidak ada data.`,
    "",
    "Filter yang sedang aktif di dashboard pembaca:",
    `  periode ${filters.from} sampai ${filters.to}`,
    `  toko: ${filters.stores.length ? filters.stores.join(", ") : "semua"}`,
    `  kategori: ${filters.categories.length ? filters.categories.join(", ") : "semua"}`,
    `  keanggotaan: ${filters.membership ?? "semua"}`,
    "Kalau pertanyaannya tidak menyebut periode atau toko lain, pakai filter ini apa adanya.",
    "",
    "Aturan menjawab:",
    "- Panggil tool dulu. Jangan pernah menyebut angka yang tidak berasal dari hasil tool.",
    "- Kalau tidak ada tool yang bisa menjawab, katakan terus terang kamu tidak tahu dan",
    "  sebutkan apa yang sebenarnya bisa kamu jawab. Jangan mengarang, jangan memperkirakan.",
    "- Jawab dalam Bahasa Indonesia, ringkas (maksimal dua kalimat), dan sebutkan angkanya.",
    "- Jangan mengulang seluruh tabel di teks; tabelnya sudah ditampilkan terpisah.",
    "",
    "Batas data yang harus kamu hormati: tidak ada harga pokok (jadi tidak ada margin atau",
    "laba), seluruh pembayaran POS memakai satu metode SUSPENSE (jadi tidak ada rincian",
    "tunai vs kartu), dan tidak ada data stok, kepegawaian, maupun target.",
    "",
    "Pertanyaan yang bisa dijawab tool:",
    ...skills.map((s) => `- ${s.id}: ${s.description}`),
  ].join("\n");
}

/** The JSON Schema for one skill's arguments, derived from the slots it declares. */
function schemaFor(spec: SkillSpec) {
  const properties: Record<string, unknown> = {};

  if (spec.slots.includes("range")) {
    properties.from = { type: "string", description: "Tanggal mulai, format YYYY-MM-DD." };
    properties.to = { type: "string", description: "Tanggal akhir inklusif, format YYYY-MM-DD." };
  }
  if (spec.slots.includes("stores")) {
    properties.stores = {
      type: "array",
      items: { type: "integer" },
      description: "Id pos_config toko. Kosongkan untuk seluruh toko.",
    };
  }
  if (spec.slots.includes("categories")) {
    properties.categories = {
      type: "array",
      items: { type: "string" },
      description: "Nama kategori level 2 persis seperti yang muncul di dashboard.",
    };
  }
  if (spec.slots.includes("membership")) {
    properties.membership = {
      type: "string",
      enum: ["member", "guest"],
      description: "Batasi ke transaksi member atau non-member saja.",
    };
  }
  if (spec.slots.includes("limit")) {
    properties.limit = { type: "integer", description: "Jumlah baris, maksimal 10." };
  }

  return { type: "object" as const, properties };
}

type SkillArgs = Record<string, unknown>;

/**
 * The last figures a tool produced.
 *
 * The runner hands back Claude's prose; the table and the deep link come from
 * the skill that produced it, so the fallback answer renders identically to a
 * catalogue answer instead of being a wall of text.
 */
interface Trace {
  last: SkillResult | null;
  calls: string[];
}

/**
 * A runnable tool is just a tool definition plus `run` and `parse`, so the
 * catalogue is turned into tools directly. The `betaTool()` helper infers its
 * argument type from a literal schema, which cannot be done for schemas built
 * at runtime from the catalogue the cockpit reports.
 */
function buildTools(
  skills: SkillSpec[],
  base: Filters,
  trace: Trace,
): BetaRunnableTool<SkillArgs>[] {
  return skills.map(
    (spec): BetaRunnableTool<SkillArgs> => ({
      name: spec.id,
      description: spec.description,
      input_schema: schemaFor(spec),
      // The cockpit re-validates every field before it reaches SQL, so this
      // only has to reject a shape that would crash `run` itself.
      parse: (content: unknown): SkillArgs =>
        content && typeof content === "object" ? (content as SkillArgs) : {},
      run: async (args: SkillArgs) => {
        // Arguments are folded onto the reader's filters rather than replacing
        // them, and the cockpit re-validates every field before it reaches SQL.
        const filters: Record<string, string> = {
          from: typeof args.from === "string" ? args.from : base.from,
          to: typeof args.to === "string" ? args.to : base.to,
        };
        const stores = Array.isArray(args.stores) ? args.stores : base.stores;
        if (stores.length) filters.stores = stores.join(",");
        const categories = Array.isArray(args.categories) ? args.categories : base.categories;
        if (categories.length) filters.categories = categories.join(",");
        const membership = args.membership ?? base.membership;
        if (membership === "member" || membership === "guest") filters.membership = membership;

        const limit = typeof args.limit === "number" ? args.limit : undefined;

        trace.calls.push(spec.id);
        const result = await runSkill(spec.id, filters, limit);
        trace.last = result;

        // Claude receives the headline plus the rows, so it can quote a figure
        // from the table rather than only the summary sentence.
        const table = result.table
          ? "\n" +
            [result.table.columns.join(" | "), ...result.table.rows.map((r) => r.join(" | "))].join("\n")
          : "";
        return `${result.headline}${table}${result.note ? `\n(catatan: ${result.note})` : ""}`;
      },
    }),
  );
}

export interface AskRequest {
  question: string;
  filters: Filters;
  extent: { start: string; end: string };
}

let catalogue: Promise<SkillSpec[]> | null = null;

/** Fetched once and kept: the catalogue changes only when the cockpit ships. */
function skills(): Promise<SkillSpec[]> {
  if (!catalogue) {
    catalogue = describeSkills()
      .then((r) => r.skills)
      .catch((err) => {
        catalogue = null;
        throw err;
      });
  }
  return catalogue;
}

export async function ask(req: AskRequest): Promise<SkillResult & { calls: string[] }> {
  const specs = await skills();
  const trace: Trace = { last: null, calls: [] };

  const runner = client.beta.messages.toolRunner(
    {
      model: MODEL,
      max_tokens: 4096,
      max_iterations: MAX_ITERATIONS,
      output_config: { effort: EFFORT },
      system: systemPrompt(specs, req.filters, req.extent),
      tools: buildTools(specs, req.filters, trace),
      messages: [{ role: "user", content: req.question }],
    },
    { signal: AbortSignal.timeout(TIMEOUT_MS) },
  );

  const final = await runner;

  const text = final.content
    .filter((b): b is Anthropic.Beta.BetaTextBlock => b.type === "text")
    .map((b) => b.text.trim())
    .join(" ")
    .trim();

  // A refusal or an exhausted iteration budget leaves no usable prose. Falling
  // back to the last tool headline beats returning an empty bubble; if no tool
  // ever ran, the caller turns a null headline into the honest "tidak tahu".
  const headline = text || trace.last?.headline || "";

  return {
    headline,
    table: trace.last?.table,
    href: trace.last?.href,
    note: trace.last?.note,
    skill: trace.calls[trace.calls.length - 1],
    calls: trace.calls,
  };
}
