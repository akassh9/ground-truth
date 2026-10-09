import { useState } from "preact/hooks";
import { useData } from "./data.js";

// the Check's positions, in reading order; the first is the one the Check exists to catch
const ROWS = [
  ["head_on_with_entrenched", "Head-on with an entrenched giant", "Same kind of product, same buyers, as a company with a large public footprint."],
  ["head_on_with_building", "Head-on with a company still building", "Same kind of product, same buyers, as a company that is still scaling."],
  ["complement", "Sells to the giants", "Its likely customers are companies on the map."],
  ["white_space", "Open space", "The map covers this market, and nobody on it sells this yet."],
  ["off_map", "Off our map", "Established companies sell this, but the map doesn't track them yet."],
];
const MODELS = [
  ["jev", "Jev (TypeSafe jev-1.13.0)", "First pass: lane, rival and position, with probabilities"],
  ["haiku", "Claude Haiku 5.5", "The Check: a cited verdict"],
  ["opus", "Claude Opus 5.5", "Second opinion on the hand-labeled companies"],
];

const usd = (x) => `$${x.toFixed(2)}`;
const count = (x) => x.toLocaleString("en-US");

// Two parts of section 3: Trust (is the Check right?) and Findings (what it concluded across 912 seed deals).
function useEvidence() {
  const e = useData("evidence.json");
  const status = e === undefined ? <p class="muted">Loading…</p> : !e ? <p class="muted">The evaluation hasn't been exported yet.</p> : null;
  return [e, status];
}

export function Trust() {
  const [e, status] = useEvidence();
  if (status) return status;
  const cited = e.citations.haiku.total + e.citations.opus.total;
  const invented = e.citations.haiku.invented + e.citations.opus.invented;
  const truncated = e.citations.haiku.truncated + e.citations.opus.truncated;
  const { jev, haiku } = e.cost;
  return (
    <div class="evidence-section">
      <div class="tiles">
        <Tile label="Invented citations" value={count(invented)}
              note={`of ${count(cited)} cited, each checked against the record in code${truncated ? `; ${truncated} cut short` : ""}`} />
        <Tile label="Jev and Haiku agree" value={`${Math.round(e.fights_a_giant.rate * 100)}%`}
              note={`on whether a company fights a giant (${count(e.fights_a_giant.n)} companies)`} />
        <Tile label={`Cost for all ${count(e.companies)}`} value={usd(jev.usd + haiku.usd)}
              note={`Jev ${usd(jev.usd)}, Haiku ${usd(haiku.usd)}`} />
        <Tile label="Refusals" value={count(e.refused_by_haiku)}
              note={e.refused_by_haiku ? `of ${count(e.companies)}; Opus answered ${e.refused_by_haiku === 1 ? "it" : "them"}` : `of ${count(e.companies)}`} />
      </div>
      {e.labels && <Labels labels={e.labels} />}
      <h4>The models</h4>
      <table class="evidence">
        <thead>
          <tr><th>Model</th><th class="num">Companies</th><th class="num">Cost</th><th class="num">Median time</th></tr>
        </thead>
        <tbody>
          {MODELS.map(([k, name, job]) => (
            <tr key={k}>
              <td>{name}<span class="job">{job}</span></td><td class="num">{count(e.cost[k].companies)}</td>
              <td class="num">{usd(e.cost[k].usd)}</td>
              <td class="num">{e.cost[k].median_seconds ? `${Math.round(e.cost[k].median_seconds)} s` : "under 1 s"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Findings() {
  const [e, status] = useEvidence();
  if (status) return status;
  const p = e.positions;
  const busy = Math.round(((p.head_on_with_entrenched + p.head_on_with_building + p.complement) / e.in_lanes) * 100);
  return (
    <div class="evidence-section">
      <p class="sub">
        Only {count(p.white_space)} of the {count(e.in_lanes)} companies in Anti Fund's lanes have the space to themselves.
        {" "}{busy}% fight a giant or sell to one.
      </p>
      <Positions e={e} />
    </div>
  );
}

function Tile({ label, value, note }) {
  return (
    <div class="card tile">
      <p class="tile-label">{label}</p>
      <p class="tile-value">{value}</p>
      <p class="tile-note">{note}</p>
    </div>
  );
}

function Positions({ e }) {
  const [tip, setTip] = useState(null);
  const max = Math.max(...ROWS.map(([k]) => e.positions[k]));
  return (
    <>
      <table class="bars">
        <caption>Where the {count(e.in_lanes)} companies in Anti Fund's lanes sit</caption>
        <thead class="sr-only"><tr><th>Position</th><th>Companies</th></tr></thead>
        <tbody>
          {ROWS.map(([k, label, means], i) => {
            const n = e.positions[k];
            const show = (ev) => setTip({ label, means, n, rect: ev.currentTarget.querySelector(".bar").getBoundingClientRect() });
            return (
              <tr key={k} class={i === 0 ? "lead" : ""} tabIndex="0" onMouseEnter={show} onFocus={show}
                  onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
                <th scope="row">{label}</th>
                <td>
                  <span class="bar-cell">
                    <span class="bar" style={{ width: `calc((100% - 48px) * ${n / max})` }} aria-hidden="true" />
                    <span class="bar-value">{count(n)}</span>
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {tip && (
        <div class="tip fixed" style={{ left: `${tip.rect.right}px`, top: `${tip.rect.top - 6}px` }}>
          <strong>{tip.label}</strong>
          <span>{count(tip.n)} of {count(e.in_lanes)} ({Math.round((tip.n / e.in_lanes) * 100)}%)</span>
          <span class="fact">{tip.means}</span>
        </div>
      )}
      <p class="note">
        {count(e.companies - e.in_lanes)} more fall outside Anti Fund's lanes. {count(e.portfolio_conflicts)} would go
        head-on with a portfolio company.
      </p>
    </>
  );
}

function Labels({ labels }) {
  const row = (x) => `${x.agree} of ${x.n}`;
  return (
    <>
      <h4>Checked against my own calls</h4>
      <p class="sub">
        Before seeing any model output, I labeled {labels.labeled} of these companies by hand as head-on, supplier
        or open.
      </p>
      <table class="evidence">
        <thead>
          <tr><th>Model</th><th class="num">Said head-on, I agreed</th><th class="num">Said open or outside our lanes, I agreed</th></tr>
        </thead>
        <tbody>
          {MODELS.map(([k, name]) => (
            <tr key={k}><td>{name}</td><td class="num">{row(labels[k].head_on)}</td><td class="num">{row(labels[k].open)}</td></tr>
          ))}
        </tbody>
      </table>
      <p class="sub">
        The head-on calls held up. "Open" didn't: I could usually name a competitor the map doesn't track. So the
        Check now says when a market is off our map instead of calling it open. I didn't tune the models on these
        companies; they'd stop being a fair test.
      </p>
    </>
  );
}
