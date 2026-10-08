// What a reading means and how to put it in words. No data in here, so the browser can load
// this module for the on-demand analysis without downloading the whole dataset.

export const REPO_URL = "https://github.com/alejandrorodriguezalvarez884-dot/decision-signal-lab";
export const AUTHOR_URL = "https://alejandrorodriguez.dev";

// Inside Market Hub the radar is one of the portal's sections: its header is the portal's, and an
// analysis links to the same company's price page and numbers.
const site = (v: string | undefined, fallback: string) => (v ?? fallback).replace(/\/$/, "");
export const HUB_URL = site(import.meta.env.PUBLIC_HUB_URL, "https://themarkethub.app");
export const FUNDAMENTALS_URL = site(import.meta.env.PUBLIC_FUNDAMENTALS_URL, "https://fundamentals.themarkethub.app");
export const PLAYGROUND_URL = site(import.meta.env.PUBLIC_PLAYGROUND_URL, "https://playground.themarkethub.app");
export const hubQuoteUrl = (ticker: string) => `${HUB_URL}/quote/?t=${encodeURIComponent(ticker)}`;
export const fundamentalsUrl = (ticker: string) => `${FUNDAMENTALS_URL}/stock/?t=${encodeURIComponent(ticker)}`;

// Internal links carry the base path the site is published under.
const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");
export const link = (path: string) => `${BASE}${path}`;

// A reading counts as "yes" from this probability up. Same value as RADAR_THEME_THRESHOLD in
// the pipeline; radar.ts checks they agree.
export const THRESHOLD = 0.5;

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

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const slug = (ticker: string) => ticker.toLowerCase();
export const companyUrl = (ticker: string) => link(`/company/${slug(ticker)}/`);

// SEC lists many names in capitals.
export const tidyName = (name: string) =>
  name === name.toUpperCase() ? name.toLowerCase().replace(/(^|[\s\-/&.(])([a-z])/g, (_, p, c) => p + c.toUpperCase()) : name;

const dateFmt = new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
export const fmtDate = (iso: string) => dateFmt.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`));

// Scores come on a 0..1 scale; these are the model's own answer scales, in words.
const level = (labels: string[]) => (x: number) => labels[Math.round(x * (labels.length - 1))];
export const strengthWord = level(["Clearly weak", "Somewhat weak", "Mixed", "Somewhat strong", "Clearly strong"]);
export const outlookWord = level(["Very negative", "Negative", "Neutral", "Positive", "Very positive"]);
export const cautionWord = level(["None", "A little", "Moderate", "A lot"]);

// `more` and `less` finish "…than in 80% of those releases".
export const SCALES = [
  { key: "results_strength", label: "Results", low: "weak", high: "strong", word: strengthWord,
    more: "Results read stronger", less: "Results read weaker" },
  { key: "outlook_tone", label: "Outlook", low: "negative", high: "positive", word: outlookWord,
    more: "The outlook reads more positive", less: "The outlook reads more negative" },
  { key: "uncertainty", label: "Caution", low: "none", high: "a lot", word: cautionWord,
    more: "Management voices more caution", less: "Management voices less caution" },
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
export const says = (r: Release, key: string) => (flagValue(r, key) ?? 0) >= THRESHOLD;

export type Peers = {
  label: string; // who the comparison is with
  n: number;
  median: Record<ScaleKey, number>;
  values: Record<ScaleKey, number[]>; // every company's reading, lowest first
  share: Record<string, number>; // share of them whose latest release says each flag
};

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
    else out.push(`${s.label}: ${a}, ${now[s.key] > prev[s.key] ? "up" : "down"} from ${b}.`);
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

const CAUTION_PHRASE = ["no caution voiced", "a little caution", "moderate caution", "a lot of caution"];

// One sentence that sums a release up.
export function headline(r: Release): string {
  const caution = CAUTION_PHRASE[Math.round(r.uncertainty * (CAUTION_PHRASE.length - 1))];
  const said = FLAGS.filter((f) => says(r, f.key)).map((f) => f.phrase);
  const list = said.length > 1 ? `${said.slice(0, -1).join(", ")} and ${said.at(-1)}` : said[0];
  return (
    `${GUIDANCE_NOW[r.guidance]}. Results read as ${strengthWord(r.results_strength).toLowerCase()} and the outlook as ` +
    `${outlookWord(r.outlook_tone).toLowerCase()}, with ${caution}.` +
    (said.length ? ` The release ${list}.` : "")
  );
}

// What is unusual about a release: how sure the model is, where the release sits among the
// latest releases of the peers and which of its answers are rare or close calls. The sentences
// are read under a line that names the peers, so they say "those releases".
const FAR = 0.8; // further out than this share of the other companies
const RARE = 0.25; // a flag this few of them raise
export function standouts(now: Release, peers: Peers): string[] {
  const out: string[] = [];
  const [top, second] = GUIDANCE_ORDER.map((c) => ({ c, p: now.guidance_p[c] })).sort((a, b) => b.p - a.p);
  out.push(
    top.p >= 0.75
      ? `The model is confident about guidance: “${GUIDANCE_LABEL[top.c].toLowerCase()}” at ${pct(top.p)}.`
      : `Guidance is a close call: “${GUIDANCE_LABEL[top.c].toLowerCase()}” at ${pct(top.p)}, ` +
          `“${GUIDANCE_LABEL[second.c].toLowerCase()}” at ${pct(second.p)}.`,
  );

  const middle: string[] = [];
  for (const s of SCALES) {
    const all = peers.values[s.key];
    const below = all.filter((v) => v < now[s.key]).length / all.length;
    const above = all.filter((v) => v > now[s.key]).length / all.length;
    if (below >= FAR) out.push(`${s.more} than in ${pct(below)} of those releases.`);
    else if (above >= FAR) out.push(`${s.less} than in ${pct(above)} of those releases.`);
    else middle.push(s.label.toLowerCase());
  }
  if (middle.length === SCALES.length) out.push("Results, outlook and caution all sit within the usual range of those releases.");

  for (const f of FLAGS) {
    const p = flagValue(now, f.key);
    if (p === undefined) continue;
    if (p >= THRESHOLD && peers.share[f.key] < RARE)
      out.push(`It ${f.phrase}; only ${pct(peers.share[f.key])} of those companies do.`);
    else if (Math.abs(p - THRESHOLD) < 0.15) out.push(`${f.label} is a close call: the model puts it at ${pct(p)}.`);
  }
  return out;
}
