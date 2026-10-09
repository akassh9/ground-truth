import { useMemo, useState } from "preact/hooks";
import { useData, fundCall } from "./data.js";

const CALL = { pass: "Pass", look: "Take a look", priority: "Priority" };
const POSITION = {
  head_on_with_entrenched: "Head-on with an entrenched giant",
  head_on_with_building: "Head-on with a company still building",
  complement: "Sells to or buys from the giants",
  white_space: "Open space",
  off_map: "Off our map: we don't track the established players in this market",
};
const RELATION = { head_on: "Head-on", supplier_to_them: "Supplies them", customer_of_them: "Buys from them", adjacent: "Adjacent" };

export function useEvidence(laneMap) {
  return useMemo(() => {
    const index = new Map();
    for (const lane of laneMap?.lanes || []) {
      for (const c of lane.companies) for (const f of c.facts) index.set(f.id, { ...f, company: c.name });
    }
    return index;
  }, [laneMap]);
}

export function Check({ laneMap }) {
  const examples = useData("checks.json");
  const [form, setForm] = useState({ name: "", url: "", about: "", passcode: "" });
  const [state, setState] = useState({ status: "idle" });
  const evidence = useEvidence(laneMap);
  const set = (k) => (e) => {
    const value = e.currentTarget.value;
    setForm((f) => ({ ...f, [k]: value })); // functional update: fast typing or autofill can't drop a field
  };

  async function submit(e) {
    e.preventDefault();
    setState({ status: "running" });
    try {
      const r = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const body = await r.json().catch(() => ({}));
      setState(r.ok ? { status: "done", result: body } : { status: "error", error: body.error || "The check failed." });
    } catch {
      setState({ status: "error", error: "Couldn't reach the Check. Try again." });
    }
  }

  return (
    <div class="check">
      <form class="card check-form" onSubmit={submit}>
        <label>Company<input value={form.name} onInput={set("name")} maxLength={120} required placeholder="e.g. a seed-stage drone maker" /></label>
        <label>Website<input value={form.url} onInput={set("url")} maxLength={300} type="url" placeholder="https://" /></label>
        <label>Description <span class="muted">(optional; use it if the site is thin)</span>
          <textarea value={form.about} onInput={set("about")} maxLength={4000} rows={3} />
        </label>
        <label>Passcode <span class="muted">(from the email)</span>
          <input value={form.passcode} onInput={set("passcode")} autocomplete="off" />
        </label>
        <button type="submit" disabled={state.status === "running"}>
          {state.status === "running" ? "Checking… (about 20 seconds)" : "Run the Check"}
        </button>
        {state.status === "error" && <p class="error" role="alert">{state.error}</p>}
      </form>

      {examples?.length > 0 && (
        <div class="examples">
          <span class="muted">Examples:</span>
          {examples.map((ex) => (
            <button type="button" class="chip" key={ex.name} onClick={() => setState({ status: "done", result: ex })}>{ex.name}</button>
          ))}
        </div>
      )}

      <div aria-live="polite">
        {state.status === "done" && <Verdict result={state.result} evidence={evidence} />}
      </div>
    </div>
  );
}

export function Verdict({ result, evidence }) {
  const v = result.verdict;
  return (
    <article class="card verdict">
      <header>
        <h3>{result.name}</h3>
        <p class={`call call-${fundCall(v)}`}>
          {CALL[fundCall(v)]}{v.portfolio_conflicts.length ? `: conflicts with ${v.portfolio_conflicts.join(", ")}` : ""}
        </p>
      </header>
      <p class="position">{POSITION[v.position]}</p>
      <p>{v.reasoning}</p>
      <dl>
        <dt>What it builds</dt><dd>{v.what_it_builds}</dd>
        <dt>Who pays</dt><dd>{v.buyers}</dd>
        {v.wedge && (<><dt>Wedge</dt><dd>{v.wedge}</dd></>)}
        {v.portfolio_conflicts.length > 0 && (<><dt>Portfolio conflict</dt><dd>{v.portfolio_conflicts.join(", ")}</dd></>)}
      </dl>
      {v.overlaps.length > 0 && (
        <>
          <h4>Who it runs into</h4>
          <ul class="overlaps">
            {v.overlaps.map((o) => (
              <li key={o.company}>
                <p><strong>{o.company}</strong>{o.portfolio && <span class="tag">Anti Fund</span>} · {RELATION[o.relationship]}</p>
                <p>{o.why}</p>
                <p class="cites">
                  {o.evidence_ids.map((id) => {
                    const f = evidence.get(id.replace(/^\[|\]$/g, ""));
                    return f?.url
                      ? <a key={id} href={f.url} target="_blank" rel="noopener noreferrer" title={f.text}>{shortSource(id)}</a>
                      : <span key={id} class="muted">{shortSource(id)}</span>;
                  })}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
      {v.open_questions.length > 0 && (
        <>
          <h4>Ask the founders</h4>
          <ul>{v.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
        </>
      )}
    </article>
  );
}

function shortSource(id) {
  const kind = id.split(":")[0];
  return { usaspending: "federal award", "usaspending-sub": "subcontract", nrc: "NRC filing", jobs: "job board",
           "jobs-production": "factory hiring", "jobs-site": "site hiring", "faa-fleet": "FAA fleet", "faa-rsv": "FAA reservations",
           "faa-reg": "FAA registrations", "faa-maker": "FAA maker", site: "site" }[kind] || kind;
}
