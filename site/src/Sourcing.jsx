import { useState } from "preact/hooks";
import { useData, fundCall } from "./data.js";
import { Verdict, useEvidence } from "./Check.jsx";

const CALL = { pass: "Pass", look: "Take a look", priority: "Priority" };

export function Sourcing({ laneMap }) {
  const [shown, setShown] = useState(null);
  const evidence = useEvidence(laneMap);
  const found = useData("sourcing.json");
  const checks = useData("checks.json");
  if (found === undefined) return <p class="muted">Loading…</p>;
  if (!found) return <p class="muted">Sourcing hasn't run yet.</p>;
  // NRC and FAA spell names their own way ("Firestorm Labs Inc", "Laser Isotope Separation Technologie"),
  // so match on a normalized core of the name or any alias
  const core = (n) => n.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\b(inc|llc|corp|co|ltd)\b/g, "").trim().split(/\s+/).slice(0, 2).join(" ");
  const verdicts = new Map();
  for (const c of checks || []) for (const n of [c.name, ...(c.aliases || [])]) verdicts.set(core(n), c);
  const find = (name) => verdicts.get(core(name)) || verdicts.get(core(name).split(" ")[0]);
  for (const c of checks || []) verdicts.set(core(c.name).split(" ")[0], verdicts.get(core(c.name).split(" ")[0]) || c);
  const rows = [...found.nrc, ...found.faa];
  return (
    <>
    <table class="evidence sourcing">
      <thead>
        <tr><th>First seen</th><th>Company</th><th>What the record shows</th><th>The Check</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const v = find(r.company);
          return (
            <tr key={r.company + r.date}>
              <td class="date">{r.date}</td>
              <td>{r.company}<span class="tag">{r.source === "nrc" ? "NRC" : "FAA"}</span></td>
              <td><a href={r.evidence_url} target="_blank" rel="noopener noreferrer">{r.what}</a></td>
              <td>{v ? <button type="button" class="link" onClick={() => setShown(v)}>{CALL[fundCall(v.verdict)]}</button> : <span class="muted">not run</span>}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
    {shown && <Verdict result={shown} evidence={evidence} />}
    </>
  );
}
