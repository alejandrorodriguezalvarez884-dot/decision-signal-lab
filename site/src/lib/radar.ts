// Data and helpers. The site reads the dataset straight from radar/ at the repository root.
import releasesFile from "../../../radar/releases.json";
import summaryFile from "../../../radar/summary.json";

export const REPO_URL = "https://github.com/alejandrorodriguezalvarez884-dot/decision-signal-lab";
export const AUTHOR_URL = "https://alejandrorodriguez.dev";

// Internal links carry the base path the site is published under.
const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
export const link = (path: string) => `${BASE}${path}`;

export type GuidanceClass = "raised" | "lowered" | "mixed" | "reaffirmed" | "new_period" | "withdrawn" | "none";

export type Release = {
  id: string;
  ticker: string;
  date: string;
  quarter: string;
  url: string;
  guidance: GuidanceClass;
  guidance_p: Record<GuidanceClass, number>;
  results_strength: number;
  outlook_tone: number;
  uncertainty: number;
  demand_weakness: number;
  margin_pressure: number;
  themes: Record<string, number>;
};

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

export const GUIDANCE_LABEL: Record<GuidanceClass, string> = {
  raised: "Raised",
  lowered: "Lowered",
  mixed: "Mixed",
  reaffirmed: "Reaffirmed",
  new_period: "New period",
  withdrawn: "Withdrawn",
  none: "No guidance",
};
export const GUIDANCE_ORDER = Object.keys(GUIDANCE_LABEL) as GuidanceClass[];

export const THEME_LABEL: Record<string, string> = {
  tariffs: "Tariffs",
  ai: "AI",
  supply_chain: "Supply chain",
  restructuring: "Restructuring",
};

// The same themes inside a sentence ("also says: tariffs, AI").
export const THEME_WORD: Record<string, string> = {
  tariffs: "tariffs",
  ai: "AI",
  supply_chain: "supply chain",
  restructuring: "restructuring",
};

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

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const quarterLabel = (q: string) => `${q.slice(4)} ${q.slice(0, 4)}`;
const MONTHS = ["Jan–Mar", "Apr–Jun", "Jul–Sep", "Oct–Dec"];
export const quarterMonths = (q: string) => MONTHS[Number(q.slice(5)) - 1];
export const slug = (ticker: string) => ticker.toLowerCase();
export const companyUrl = (ticker: string) => link(`/company/${slug(ticker)}/`);

const dateFmt = new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const fmtDate = (iso: string) => dateFmt.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));

// Scores come on a 0..1 scale; these are the model's own answer scales, in words.
const level = (labels: string[]) => (x: number) => labels[Math.round(x * (labels.length - 1))];
export const strengthWord = level(["Clearly weak", "Somewhat weak", "Mixed", "Somewhat strong", "Clearly strong"]);
export const outlookWord = level(["Very negative", "Negative", "Neutral", "Positive", "Very positive"]);
export const cautionWord = level(["None", "A little", "Moderate", "A lot"]);

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

export const SCALES = [
  { key: "results_strength", label: "Results", low: "weak", high: "strong", word: strengthWord },
  { key: "outlook_tone", label: "Outlook", low: "negative", high: "positive", word: outlookWord },
  { key: "uncertainty", label: "Caution", low: "none", high: "a lot", word: cautionWord },
] as const;
export type ScaleKey = (typeof SCALES)[number]["key"];

// Yes/no readings: the two core ones and the themes.
export const FLAGS: { key: string; label: string; phrase: string }[] = [
  { key: "margin_pressure", label: "Margin pressure", phrase: "describes pressured margins" },
  { key: "demand_weakness", label: "Weakening demand", phrase: "describes weakening demand" },
  { key: "tariffs", label: "Tariffs", phrase: "says tariffs affect the business" },
  { key: "ai", label: "AI", phrase: "presents AI as a driver of demand or investment" },
  { key: "supply_chain", label: "Supply chain", phrase: "says supply chain problems hurt results" },
  { key: "restructuring", label: "Restructuring", phrase: "reports job cuts or restructuring" },
];
export const flagValue = (r: Release, key: string): number | undefined =>
  key === "margin_pressure" || key === "demand_weakness" ? r[key] : r.themes[key];
const says = (r: Release, key: string) => (flagValue(r, key) ?? 0) >= summary.meta.theme_threshold;

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

export type Peers = {
  label: string; // who the comparison is with
  n: number;
  median: Record<ScaleKey, number>;
  share: Record<string, number>; // share of peers whose latest release says each flag
};

// The latest release of every other company in the sector, or of every other company when the
// sector is too small for a median to mean anything.
export function peersOf(company: Company): Peers {
  const others = summary.companies.filter((c) => c.ticker !== company.ticker);
  const sector = others.filter((c) => c.sector === company.sector);
  const useSector = sector.length + 1 >= SMALL_SECTOR;
  const set = (useSector ? sector : others).map((c) => latestOf(c.ticker));
  return {
    label: useSector ? `${company.sector} peers` : "all other companies",
    n: set.length,
    median: Object.fromEntries(SCALES.map((s) => [s.key, median(set.map((r) => r[s.key]))])) as Record<ScaleKey, number>,
    share: Object.fromEntries(FLAGS.map((f) => [f.key, set.filter((r) => says(r, f.key)).length / set.length])),
  };
}

const GUIDANCE_NOW: Record<GuidanceClass, string> = {
  raised: "Guidance was raised",
  lowered: "Guidance was lowered",
  mixed: "Guidance was partly raised and partly lowered",
  reaffirmed: "Guidance was reaffirmed",
  new_period: "Guidance was given for a new period",
  withdrawn: "Guidance was withdrawn",
  none: "No guidance was given",
};
const GUIDANCE_BEFORE: Record<GuidanceClass, string> = {
  raised: "it was raised",
  lowered: "it was lowered",
  mixed: "it was partly raised and partly lowered",
  reaffirmed: "it was reaffirmed",
  new_period: "it was given for a new period",
  withdrawn: "it was withdrawn",
  none: "none was given",
};

// Plain sentences on how a release differs from the company's previous one.
export function changesSince(now: Release, prev: Release | undefined): string[] {
  if (!prev) return [`${GUIDANCE_NOW[now.guidance]}. This is the first release on record for the company.`];
  const out: string[] = [];
  out.push(
    now.guidance === prev.guidance
      ? `${GUIDANCE_NOW[now.guidance]}, as in the previous release.`
      : `${GUIDANCE_NOW[now.guidance]}; in the previous release ${GUIDANCE_BEFORE[prev.guidance]}.`,
  );
  const same: string[] = [];
  for (const s of SCALES) {
    const a = s.word(now[s.key]).toLowerCase();
    const b = s.word(prev[s.key]).toLowerCase();
    if (a === b) same.push(s.label.toLowerCase());
    else out.push(`${s.label} ${s.key === "uncertainty" ? "is" : "reads as"} ${a}, ${now[s.key] > prev[s.key] ? "up" : "down"} from ${b}.`);
  }
  if (same.length) {
    const list = same.length > 1 ? `${same.slice(0, -1).join(", ")} and ${same.at(-1)}` : same[0];
    out.push(`${list[0].toUpperCase()}${list.slice(1)} ${same.length > 1 ? "read" : "reads"} the same as last time.`);
  }
  const asked = FLAGS.filter((f) => flagValue(now, f.key) !== undefined && flagValue(prev, f.key) !== undefined);
  const added = asked.filter((f) => says(now, f.key) && !says(prev, f.key)).map((f) => f.phrase);
  const dropped = asked.filter((f) => !says(now, f.key) && says(prev, f.key)).map((f) => f.phrase);
  if (added.length) out.push(`New in this release: it ${added.join("; it ")}.`);
  if (dropped.length) out.push(`No longer the case: it ${dropped.join("; it ")}.`);
  return out;
}
