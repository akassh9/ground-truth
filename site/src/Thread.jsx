import { useData } from "./data.js";

// One lane followed through all three questions, so the page reads as one story: watch a portfolio company,
// rank it in its lane, then check two newcomers against that lane. Numbers and verdicts come from the data.

const LANE = "nuclear-fuel-and-enrichment";
const MINE = "general-matter";
const NEWCOMERS = ["LIS Technologies", "FluxPoint Energy"]; // both found through their letters to the NRC

const and = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}` : xs[0]);

function says(name, v) {
  const rel = (r) => v.overlaps.filter((o) => o.relationship === r).map((o) => o.company);
  if (v.position.startsWith("head_on")) {
    return `${name} would go head-on with ${rel("head_on")[0]}${v.portfolio_conflicts.length ? ", a portfolio company: a pass" : ""}.`;
  }
  if (v.position === "complement") return `${name} would sell to ${and(rel("supplier_to_them").slice(0, 2))}: worth a look.`;
  return `${name} has ${v.position === "white_space" ? "the space to itself" : "competitors the map doesn't track yet"}.`;
}

export function Thread({ laneMap }) {
  const checks = useData("checks.json");
  const lane = laneMap?.lanes.find((l) => l.slug === LANE);
  const mine = lane?.companies.find((c) => c.slug === MINE);
  const rival = lane?.companies.find((c) => !c.portfolio);
  const verdicts = NEWCOMERS.map((n) => [n, checks?.find((c) => c.name === n)?.verdict]);
  if (!mine || !rival || verdicts.some(([, v]) => !v)) return null;
  const standing = mine.score === rival.score ? `level with ${rival.name}` : mine.score > rival.score ? `ahead of ${rival.name}` : `behind ${rival.name}`;
  return (
    <section class="thread" aria-label="One lane, start to finish">
      <p class="kicker">One lane, start to finish: nuclear fuel</p>
      <ol class="thread-steps">
        <li class="card">
          <span class="step">1 · Watch</span>
          <p>{mine.name} is clearing ground in Paducah and filing its way to an NRC license.</p>
          <a href="#orbit-general-matter-paducah">See it from orbit</a>
        </li>
        <li class="card">
          <span class="step">2 · Rank</span>
          <p>In its lane it scores {mine.score} of {laneMap.max_score}, {standing}.</p>
          <a href="#lanes">See the lane</a>
        </li>
        <li class="card">
          <span class="step">3 · Check</span>
          <p>Two newcomers wrote to the NRC this spring. {verdicts.map(([n, v]) => says(n, v)).join(" ")}</p>
          <a href="#check">See both checks</a>
        </li>
      </ol>
    </section>
  );
}
