// Data and helpers. The site reads the dataset straight from radar/ at the repository root.
import releasesFile from "../../../radar/releases.json";
import summaryFile from "../../../radar/summary.json";
import {
  FLAGS,
  SCALES,
  THEME_LABEL,
  THRESHOLD,
  pct,
  says,
  type GuidanceClass,
  type Peers,
  type Release,
  type ScaleKey,
} from "./reading";

export * from "./reading";

export type Block = {
  n: number;
  guidance: Record<GuidanceClass, number>;
  guidance_net: number;
  scores: Record<string, number>;
  flags: Record<string, number>;
  themes: Record<string, number | null>;
};

export type Quarter = Block & { quarter: string; partial: boolean };
export type Sector = Block & { sector: string; companies: number; prior: Block | null };
export type Company = {
  ticker: string;
  name: string;
  sector: string;
  n: number;
  last_date: string;
  last_guidance: GuidanceClass;
  prev_guidance: GuidanceClass | null;
};
export type Latest = {
  id: string;
  ticker: string;
  name: string;
  sector: string;
  date: string;
  guidance: GuidanceClass;
  prev_guidance: GuidanceClass | null;
  guidance_confidence: number;
  demand_weakness: number;
  margin_pressure: number;
  themes: string[];
  url: string;
};

export const releases = releasesFile.releases as unknown as Release[];
export const summary = summaryFile as unknown as {
  meta: {
    generated_utc: string;
    model: string;
    releases: number;
    companies: number;
    first_date: string;
    last_date: string;
    api_cost_usd: number;
    theme_threshold: number;
    has_themes: boolean;
    guidance_classes: Record<GuidanceClass, string>;
    questions: Record<string, string>;
    theme_questions: Record<string, string>;
    validation: null | {
      labelled: number;
      agree_strict: number;
      agree_lenient: number;
      agree_direction: number;
      by_model_class: Record<string, { n: number; agree_strict: number; agree_lenient: number }>;
      disagreements: { id: string; accessionNumber: string; model: string; reader: string; alt: string; note: string }[];
      unclear: { id: string; accessionNumber: string; model: string; note: string }[];
    };
  };
  quarters: Quarter[];
  sectors: Sector[];
  companies: Company[];
  latest: Latest[];
};
if (summary.meta.theme_threshold !== THRESHOLD) throw new Error("THRESHOLD in reading.ts is out of step with the dataset");

// A partial quarter enters the charts once enough companies have reported for a share to mean something.
const MIN_PARTIAL = 30;
export const chartQuarters = summary.quarters.filter((q) => !q.partial || q.n >= MIN_PARTIAL);
export const inProgress = summary.quarters.find((q) => q.partial) ?? null;
export const lastFull = [...summary.quarters].reverse().find((q) => !q.partial)!;
export const yearBefore = (q: Quarter) =>
  summary.quarters.find((x) => x.quarter === `${Number(q.quarter.slice(0, 4)) - 1}${q.quarter.slice(4)}`) ?? null;

// Below this many companies a sector's shares swing on a single release.
export const SMALL_SECTOR = 5;
export const sectorRows = [
  ...summary.sectors.filter((s) => s.companies >= SMALL_SECTOR),
  ...summary.sectors.filter((s) => s.companies < SMALL_SECTOR),
];

export const quarterLabel = (q: string) => `${q.slice(4)} ${q.slice(0, 4)}`;
const MONTHS = ["Jan–Mar", "Apr–Jun", "Jul–Sep", "Oct–Dec"];
export const quarterMonths = (q: string) => MONTHS[Number(q.slice(5)) - 1];

// Consecutive items that share a year, for the year labels under a chart.
export const yearGroups = (years: string[]) =>
  years.reduce<{ year: string; span: number }[]>((acc, y) => {
    const last = acc[acc.length - 1];
    if (last && last.year === y) last.span += 1;
    else acc.push({ year: y, span: 1 });
    return acc;
  }, []);

export type Tip = { title: string; rows: [string, string, string?][] };
export const tip = (t: Tip) => JSON.stringify(t);

// =========================================================================== one company
const byTicker = new Map<string, Release[]>();
for (const r of releases) {
  if (!byTicker.has(r.ticker)) byTicker.set(r.ticker, []);
  byTicker.get(r.ticker)!.push(r); // releases.json is sorted oldest first
}
export const historyOf = (ticker: string) => byTicker.get(ticker) ?? [];
export const latestOf = (ticker: string) => historyOf(ticker).at(-1)!;

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

// What the on-demand analysis is set against: the latest release of every company in the dataset.
const latestAll = summary.companies.map((c) => latestOf(c.ticker));
export const benchmark: Peers = {
  label: `${summary.companies.length} large US companies`,
  n: latestAll.length,
  median: Object.fromEntries(SCALES.map((s) => [s.key, median(latestAll.map((r) => r[s.key]))])) as Record<ScaleKey, number>,
  values: Object.fromEntries(
    SCALES.map((s) => [s.key, latestAll.map((r) => r[s.key]).sort((a, b) => a - b)]),
  ) as Record<ScaleKey, number[]>,
  share: Object.fromEntries(FLAGS.map((f) => [f.key, latestAll.filter((r) => says(r, f.key)).length / latestAll.length])),
};

// =========================================================================== trends
// Every series of the trends page: a share of the releases published in a quarter.
const byQuarter = new Map<string, Release[]>();
for (const r of releases) {
  if (!byQuarter.has(r.quarter)) byQuarter.set(r.quarter, []);
  byQuarter.get(r.quarter)!.push(r);
}
export const releasesIn = (quarter: string) => byQuarter.get(quarter) ?? [];
const shareOf = (q: Quarter, test: (r: Release) => boolean) => releasesIn(q.quarter).filter(test).length / q.n;

const THEME_NOTE: Record<string, string> = {
  tariffs: "Releases that say tariffs or trade restrictions affect the business",
  ai: "Releases that present AI as a driver of demand, revenue or investment",
  supply_chain: "Releases that say supply chain problems hurt results or the outlook",
  restructuring: "Releases that report job cuts or restructuring",
};

export type Series = {
  key: string;
  title: string;
  note: string;
  group: "guidance" | "tone" | "pressure" | "theme";
  value: (q: Quarter) => number;
};
export const SERIES: Series[] = [
  { key: "raised", group: "guidance", title: "Raised guidance", note: "Releases that raise guidance for at least one key metric and lower none", value: (q) => q.guidance.raised },
  { key: "lowered", group: "guidance", title: "Lowered guidance", note: "Releases that lower guidance for at least one key metric and raise none", value: (q) => q.guidance.lowered },
  // The top level of the results scale, and its two bottom levels.
  { key: "strong", group: "tone", title: "Clearly strong results", note: "Releases that report broad growth or records on the key metrics", value: (q) => shareOf(q, (r) => r.results_strength >= 0.875) },
  { key: "weak", group: "tone", title: "Weak results", note: "Releases whose results read as somewhat or clearly weak", value: (q) => shareOf(q, (r) => r.results_strength < 0.375) },
  { key: "margin_pressure", group: "pressure", title: "Margin pressure", note: "Releases that describe declining or pressured margins", value: (q) => q.flags.margin_pressure },
  { key: "demand_weakness", group: "pressure", title: "Weakening demand", note: "Releases that describe weaker demand, orders or bookings", value: (q) => q.flags.demand_weakness },
  { key: "uncertainty", group: "pressure", title: "Caution", note: "Releases where management voices at least moderate uncertainty", value: (q) => q.flags.uncertainty },
  // Below the two positive levels of the outlook scale.
  { key: "guarded", group: "pressure", title: "Guarded outlook", note: "Releases whose outlook is neutral or negative, or that give none", value: (q) => shareOf(q, (r) => r.outlook_tone < 0.625) },
  ...(summary.meta.has_themes ? Object.keys(summary.meta.theme_questions) : []).map(
    (k): Series => ({
      key: k,
      group: "theme",
      title: THEME_LABEL[k] ?? k,
      note: THEME_NOTE[k] ?? "",
      value: (q) => q.themes[k] ?? 0,
    }),
  ),
];

const points = (d: number) => `${Math.abs(d)} ${Math.abs(d) === 1 ? "pt" : "pts"}`;
// Change in whole percentage points, as the rounded figures on the page show it.
export const ptsChange = (now: number, before: number) => Math.round(now * 100) - Math.round(before * 100);
export const deltaText = (now: number, before: number, against: string) => {
  const d = ptsChange(now, before);
  return d === 0 ? `same as ${against}` : `${d > 0 ? "+" : "−"}${points(d)} vs ${against}`;
};

// What is unusual about the last full quarter: records since the dataset starts and the
// largest moves against the same quarter a year before.
export function highlights(max = 5): string[] {
  const full = summary.quarters.filter((q) => !q.partial);
  const prev = yearBefore(lastFull);
  const since = full[0].quarter.slice(0, 4);
  const found = SERIES.map((s) => {
    const now = s.value(lastFull);
    const others = full.filter((q) => q !== lastFull).map(s.value);
    const record = now > Math.max(...others) ? "highest" : now < Math.min(...others) ? "lowest" : null;
    const d = prev ? ptsChange(now, s.value(prev)) : 0;
    return { s, now, record, d };
  })
    .filter((x) => x.record || Math.abs(x.d) >= 5)
    .sort((a, b) => Number(!!b.record) - Number(!!a.record) || Math.abs(b.d) - Math.abs(a.d));
  return found.slice(0, max).map(({ s, now, record, d }) => {
    const change = prev && d !== 0 ? `${d > 0 ? "up" : "down"} ${points(d)} from ${quarterLabel(prev.quarter)}` : "";
    if (record) return `${s.title}: ${pct(now)} of releases, the ${record} of any quarter since ${since}${change ? `, ${change}` : ""}.`;
    return `${s.title}: ${pct(now)} of releases, ${change}.`;
  });
}
