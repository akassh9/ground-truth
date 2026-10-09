import { useState } from "preact/hooks";
import { useData, SOURCE_NAMES } from "./data.js";

// standing facts dated "today"; the feed below is for dated events
const SNAPSHOT = new Set(["hiring_snapshot", "hiring_production", "faa_fleet", "faa_manufacturer"]);

export function Watch() {
  const signals = useData("signals.json");
  const [company, setCompany] = useState("all");
  if (signals === undefined) return <p class="muted">Loading signals…</p>;
  if (!signals) return <p class="muted">No signals yet.</p>;
  const mine = signals.filter((s) => s.portfolio && (company === "all" || s.company === company));
  const companies = [...new Set(signals.filter((s) => s.portfolio).map((s) => s.company))].sort();
  const now = mine.filter((s) => SNAPSHOT.has(s.kind));
  const events = mine.filter((s) => !SNAPSHOT.has(s.kind)).slice(0, 40);
  return (
    <div class="watch">
      <div class="filters" role="group" aria-label="Filter by company">
        {["all", ...companies].map((c) => (
          <button type="button" key={c} class="chip" aria-pressed={company === c} onClick={() => setCompany(c)}>
            {c === "all" ? "All companies" : c}
          </button>
        ))}
      </div>
      {company !== "all" && now.length > 0 && (
        <div class="card now-card">
          <h3>Right now</h3>
          <ul>{now.map((s) => <li key={s.id}><a href={s.evidence_url} target="_blank" rel="noopener noreferrer">{s.headline}</a></li>)}</ul>
        </div>
      )}
      <ul class="feed">
        {events.map((s) => (
          <li key={s.id} class="card">
            <p class="feed-meta"><span class="date">{s.date}</span> · {s.company} · {SOURCE_NAMES[s.source] || s.source}</p>
            <p class="feed-head"><a href={s.evidence_url} target="_blank" rel="noopener noreferrer">{s.headline}</a></p>
            {s.detail && <p class="muted">{s.detail}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
