import { useState } from "preact/hooks";

// Each lane of Anti Fund's thesis, ranked by entrenchment (gt/lanes.py): Anti Fund's companies against their
// competitors, scored on what each has physically built. Emphasis form: portfolio in the accent, everyone else gray.

const DEFAULT_LANE = "nuclear-fuel-and-enrichment";
const STATUS = { owned: "A giant is entrenched", contested: "Someone is building", open: "Nobody entrenched on the record" };

const versus = (c, rival) =>
  c.score > rival.score ? `ahead of ${rival.name} at ${rival.score}`
    : c.score === rival.score ? `level with ${rival.name}` : `behind ${rival.name} at ${rival.score}`;

export function Lanes({ data }) {
  const [slug, setSlug] = useState(DEFAULT_LANE);
  const [tip, setTip] = useState(null);
  const [evidence, setEvidence] = useState(false);
  if (data === undefined) return <p class="muted">Loading the lanes…</p>;
  if (!data) return <p class="muted">The lane map is being built.</p>;
  const max = data.max_score || 16;
  const lane = data.lanes.find((l) => l.slug === slug) || data.lanes[0];
  const rival = lane.companies.find((c) => !c.portfolio); // the strongest company Anti Fund doesn't own
  const mine = lane.companies.filter((c) => c.portfolio);
  const pick = (s) => { setSlug(s); setEvidence(false); setTip(null); };
  return (
    <div class="lanes">
      <div class="filters" role="group" aria-label="Lanes">
        {data.lanes.map((l) => (
          <button type="button" key={l.slug} class="chip" aria-pressed={l.slug === lane.slug} onClick={() => pick(l.slug)}>
            {l.anti_fund_has.length > 0 && <i class="key portfolio" title="Anti Fund has a company here" />}{l.name}
          </button>
        ))}
      </div>
      <div class="card lane-card">
        <h3>{lane.name}</h3>
        <p class="muted lane-desc">{STATUS[lane.status]}. {lane.description}</p>
        {mine.length ? (
          <ul class="health">
            {mine.map((c) => (
              <li key={c.slug}><strong>{c.name}</strong> is {c.tier}, {c.score} of {max}{rival ? `, ${versus(c, rival)}` : ""}.</li>
            ))}
          </ul>
        ) : <p class="health muted">No Anti Fund company in this lane yet.</p>}
        <table class="ranking">
          <caption class="sr-only">{lane.name}, ranked by entrenchment score out of {max}</caption>
          <thead class="sr-only"><tr><th scope="col">Company</th><th scope="col">Score</th></tr></thead>
          <tbody>
            {lane.companies.map((c) => {
              const show = (e) => setTip({ c, rect: e.currentTarget.querySelector(".bar-track").getBoundingClientRect() });
              const earned = Object.entries(c.points || {}).map(([k, v]) => `${k} ${v}`).join(" · ");
              return (
                <tr key={c.slug} class={c.portfolio ? "mine" : ""} tabIndex="0" onMouseEnter={show} onFocus={show}
                    onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
                  <th scope="row">
                    {c.name}{c.portfolio && <span class="tag">Anti Fund</span>}
                    <span class="earned">{earned || "nothing on the record yet"}</span>
                  </th>
                  <td>
                    <span class="bar-track">
                      <span class="bar" style={{ width: `${(c.score / max) * 100}%` }} />
                      {[4, 7].map((t) => <span key={t} class="tier-line" style={{ left: `${(t / max) * 100}%` }} />)}
                      <span class="bar-value" style={{ left: `${(c.score / max) * 100}%` }}>{c.score}</span>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p class="note">Score out of {max}. Lines mark building (4) and entrenched (7); $1B+ in federal awards is entrenched on its own.</p>
        <button type="button" class="link" aria-expanded={evidence} onClick={() => setEvidence(!evidence)}>
          {evidence ? "Hide the evidence" : "Show the evidence"}
        </button>
        {evidence && <Evidence lane={lane} />}
      </div>
      {tip && (
        <div class="tip fixed" style={{ left: `${tip.rect.left + tip.rect.width / 2}px`, top: `${tip.rect.top - 8}px` }}>
          <strong>{tip.c.name}</strong>
          <span>{tip.c.portfolio ? "Anti Fund portfolio · " : ""}{tip.c.tier}, score {tip.c.score}</span>
          {tip.c.facts.slice(0, 3).map((f) => <span key={f.id} class="fact">{f.text}</span>)}
        </div>
      )}
    </div>
  );
}

function Evidence({ lane }) {
  return (
    <table class="evidence">
      <thead>
        <tr><th>Company</th><th class="num">Score</th><th>Public evidence</th></tr>
      </thead>
      <tbody>
        {lane.companies.map((c) => (
          <tr key={c.slug}>
            <td>{c.name}{c.portfolio && <span class="tag">Anti Fund</span>}</td>
            <td class="num">{c.score}</td>
            <td>
              {c.facts.length ? (
                <ul>{c.facts.map((f) => <li key={f.id}>{f.url ? <a href={f.url} target="_blank" rel="noopener noreferrer">{f.text}</a> : f.text}</li>)}</ul>
              ) : <span class="muted">No public-record footprint found yet.</span>}
              {c.why && <p class="muted why">{c.why}</p>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
