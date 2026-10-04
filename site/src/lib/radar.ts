// Data and helpers. The site reads the dataset straight from radar/ at the repository root.
import releasesFile from "../../../radar/releases.json";
import summaryFile from "../../../radar/summary.json";
import { FLAGS, SCALES, THRESHOLD, says, type GuidanceClass, type Peers, type Release, type ScaleKey } from "./reading";

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
// Everything the company page says about a release: its history, the previous release and
// what other companies' latest releases look like.
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

const benchmark = (set: Release[], label: string): Peers => ({
  label,
  n: set.length,
  median: Object.fromEntries(SCALES.map((s) => [s.key, median(set.map((r) => r[s.key]))])) as Record<ScaleKey, number>,
  share: Object.fromEntries(FLAGS.map((f) => [f.key, set.filter((r) => says(r, f.key)).length / set.length])),
});

// The latest release of every other company in the sector, or of every other company when the
// sector is too small for a median to mean anything.
export function peersOf(company: Company): Peers {
  const others = summary.companies.filter((c) => c.ticker !== company.ticker);
  const sector = others.filter((c) => c.sector === company.sector);
  const useSector = sector.length + 1 >= SMALL_SECTOR;
  return benchmark(
    (useSector ? sector : others).map((c) => latestOf(c.ticker)),
    useSector ? `${company.sector} peers` : "all other companies",
  );
}

// What a company outside the study is set against: the latest release of every study company.
export const studyBenchmark = benchmark(
  summary.companies.map((c) => latestOf(c.ticker)),
  `the ${summary.companies.length} S&P 100 companies of the study`,
);
