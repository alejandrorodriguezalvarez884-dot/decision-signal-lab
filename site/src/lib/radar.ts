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
