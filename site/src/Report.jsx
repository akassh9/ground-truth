import { useData, money, day } from "./data.js";

// Portfolio reporting without asking: what each physical portfolio company did in the last 90 days, read off
// the public record. The window ends at the newest signal, so the page stays honest when the data is a few days old.

const WINDOW_DAYS = 90;
const FEDERAL = new Set(["federal_contract", "federal_grant", "federal_subaward"]);
const SNAPSHOT = new Set(["hiring_snapshot", "hiring_production", "faa_fleet", "faa_manufacturer"]);
const n = (x) => x.toLocaleString("en-US");

function report(company, signals, since) {
  const recent = signals.filter((s) => !SNAPSHOT.has(s.kind) && day(s.date) >= since);
  const awards = recent.filter((s) => FEDERAL.has(s.kind));
  const parts = [];
  if (awards.length) parts.push(`${money(awards.reduce((t, s) => t + (s.amount || 0), 0))} in ${awards.length} federal award${awards.length > 1 ? "s" : ""}`);
  const vehicles = recent.filter((s) => s.kind === "federal_idv").length;
  if (vehicles) parts.push(`${vehicles} new contract vehicle${vehicles > 1 ? "s" : ""}`);
  const nrc = recent.filter((s) => s.source === "nrc").length;
  if (nrc) parts.push(`${nrc} NRC filing${nrc > 1 ? "s" : ""}`);
  const tails = recent.filter((s) => s.kind === "faa_reservations").reduce((t, s) => t + (s.count || 0), 0);
  if (tails) parts.push(`${n(tails)} FAA tail numbers reserved`);
  const hiring = signals.find((s) => s.kind === "hiring_snapshot");
  const factory = signals.find((s) => s.kind === "hiring_production");
  if (hiring) parts.push(`${n(hiring.open_roles)} open roles${factory ? `, ${n(factory.factory_roles)} on the factory floor` : ""}`);
  const latest = signals.filter((s) => !SNAPSHOT.has(s.kind)).sort((a, b) => b.date.localeCompare(a.date))[0];
  return { ...company, parts, latest, active: recent.length };
}

export function Report({ laneMap }) {
  const signals = useData("signals.json");
  if (laneMap === undefined || signals === undefined) return <p class="muted">Loading the portfolio…</p>;
  if (!laneMap || !signals) return <p class="muted">The portfolio report isn't built yet.</p>;
  const newest = Math.max(...signals.map((s) => day(s.date)));
  const since = newest - WINDOW_DAYS * 864e5;
  const companies = new Map();
  for (const lane of laneMap.lanes) {
    for (const c of lane.companies.filter((x) => x.portfolio)) {
      const seen = companies.get(c.slug) || { ...c, lanes: [] };
      seen.lanes.push(lane.name);
      companies.set(c.slug, seen);
    }
  }
  const rows = [...companies.values()].map((c) => report(c, signals.filter((s) => s.company_slug === c.slug), since));
  const loud = rows.filter((r) => r.parts.length || r.latest).sort((a, b) => b.active - a.active || b.score - a.score);
  const quiet = rows.filter((r) => !r.parts.length && !r.latest);
  return (
    <>
      <ul class="report">
        {loud.map((r) => (
          <li key={r.slug} class="card">
            <p class="report-head"><strong>{r.name}</strong><span class="tag">{r.tier}, {r.score} of {laneMap.max_score}</span></p>
            <p class="muted report-lanes">{r.lanes.join(" · ")}</p>
            <p>{r.parts.length ? r.parts.join(" · ") : `Nothing new on the record in ${WINDOW_DAYS} days.`}</p>
            {r.latest && (
              <p class="report-latest">
                <span class="date">{r.latest.date}</span>{" "}
                <a href={r.latest.evidence_url} target="_blank" rel="noopener noreferrer">{r.latest.headline}</a>
              </p>
            )}
          </li>
        ))}
      </ul>
      {quiet.length > 0 && (
        <p class="note">
          Quiet on the public record: {quiet.map((r) => r.name).join(", ")}. No contracts, filings or job boards to read yet,
          which is itself worth knowing.
        </p>
      )}
      <p class="note">The last {WINDOW_DAYS} days, to {new Date(newest).toISOString().slice(0, 10)}.</p>
    </>
  );
}
