import { useEffect, useRef, useState } from "preact/hooks";

let MAX = 16; // highest possible entrenchment score; lane_map.json carries the real value (gt/lanes.py)
const PAD = 16;
const STEP = 16; // vertical offset between companies with the same score

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    // measure now (observers don't fire in background tabs), then follow resizes
    setWidth(Math.round(ref.current.getBoundingClientRect().width));
    const ro = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

const STATUS = { owned: "● A giant is entrenched", contested: "◐ Someone is building", open: "○ Nobody entrenched on the record" };

export function LaneMap({ data }) {
  const [tip, setTip] = useState(null);
  const [open, setOpen] = useState(null);
  if (data === undefined) return <p class="muted">Loading the lane map…</p>;
  if (!data) return <p class="muted">The lane map is being built.</p>;
  MAX = data.max_score || MAX;
  return (
    <div class="lanemap card">
      <div class="lm-legend">
        <span><i class="key portfolio" />Anti Fund portfolio</span>
        <span><i class="key other" />Everyone else</span>
      </div>
      <Row head={null}><Axis /></Row>
      {data.lanes.map((lane) => (
        <Lane key={lane.slug} lane={lane} open={open === lane.slug} setTip={setTip}
              onToggle={() => setOpen(open === lane.slug ? null : lane.slug)} />
      ))}
      {tip && <Tip tip={tip} />}
    </div>
  );
}

function Row({ head, children }) {
  return <div class="lane-row"><div class="lane-head">{head}</div><div class="lane-plot">{children}</div></div>;
}

function Axis() {
  const [ref, width] = useWidth();
  const x = (s) => PAD + (s / MAX) * (width - 2 * PAD);
  const roomy = x(7) - x(4) >= 60; // on a phone the tier words collide; the numbers still mark the tiers
  return (
    <div ref={ref} class="axis-wrap">
      {width > 0 && (
        <svg width={width} height="34" aria-hidden="true">
          {[[0, "0"], [4, roomy ? "Building" : "4"], [7, roomy ? "Entrenched" : "7"], [MAX, String(MAX)]].map(([s, label]) => (
            <g key={s}>
              <line class="tick" x1={x(s)} x2={x(s)} y1="22" y2="34" />
              <text class="tick-label" x={x(s)} y="14" text-anchor={s === 0 ? "start" : s === MAX ? "end" : "middle"}>{label}</text>
            </g>
          ))}
        </svg>
      )}
    </div>
  );
}

function place(companies) {
  const byScore = new Map();
  for (const c of companies) byScore.set(c.score, [...(byScore.get(c.score) || []), c]);
  const out = [];
  for (const group of byScore.values()) {
    group.sort((a, b) => b.portfolio - a.portfolio);
    group.forEach((c, k) => out.push({ c, slot: k === 0 ? 0 : (k % 2 ? -1 : 1) * Math.ceil(k / 2) }));
  }
  return out;
}

function Lane({ lane, open, onToggle, setTip }) {
  const [ref, width] = useWidth();
  const placed = place(lane.companies);
  const reach = Math.max(0, ...placed.map((p) => Math.abs(p.slot)));
  const height = 28 + reach * 2 * STEP;
  const mid = height / 2;
  const x = (s) => PAD + (s / MAX) * (width - 2 * PAD);
  // label Anti Fund's companies and the most entrenched outsider, on whichever side has room; a label that
  // would cover another dot or label is dropped (the tooltip and the evidence table still carry it)
  const top = lane.companies.find((c) => !c.portfolio);
  const labelW = (name) => name.length * 6.6 + 4;
  const spans = [];
  const labeled = [];
  for (const p of [...placed].sort((a, b) => b.c.portfolio - a.c.portfolio)) {
    if (!p.c.portfolio && p.c !== top) continue;
    const px = x(p.c.score), w = labelW(p.c.name);
    const dots = placed.filter((q) => q !== p && q.slot === p.slot).map((q) => x(q.c.score));
    const free = (x0, x1) => x0 >= 0 && x1 <= width && !dots.some((d) => d > x0 - 7 && d < x1 + 7)
      && !spans.some((sp) => sp.slot === p.slot && sp.x0 < x1 && x0 < sp.x1);
    const side = free(px + 10, px + 10 + w) ? "right" : free(px - 10 - w, px - 10) ? "left" : null;
    if (!side) continue;
    const [x0, x1] = side === "right" ? [px + 10, px + 10 + w] : [px - 10 - w, px - 10];
    spans.push({ slot: p.slot, x0, x1 });
    labeled.push({ ...p, px, side });
  }
  const head = (
    <>
      <h3>{lane.name}</h3>
      <p class="lane-meta">{STATUS[lane.status]}</p>
      <p class="lane-meta muted">{lane.anti_fund_has.length ? `Anti Fund: ${lane.anti_fund_has.join(", ")}` : "No Anti Fund company yet"}</p>
      <button type="button" class="link" aria-expanded={open} onClick={onToggle}>{open ? "Hide evidence" : "Show evidence"}</button>
    </>
  );
  return (
    <div class="lane">
      <Row head={head}>
        <div ref={ref} class="strip-wrap">
          {width > 0 && (
            <svg width={width} height={height} role="img"
                 aria-label={`${lane.name}: ${lane.companies.map((c) => `${c.name} ${c.score}`).join(", ")}`}>
              {[4, 7].map((s) => <line key={s} class="grid" x1={x(s)} x2={x(s)} y1="0" y2={height} />)}
              {placed.map((p) => {
                const cx = x(p.c.score), cy = mid + p.slot * STEP;
                const show = (e) => setTip({ c: p.c, rect: e.currentTarget.getBoundingClientRect() });
                return (
                  <g key={p.c.slug} class={`co ${p.c.portfolio ? "portfolio" : "other"}`} tabIndex="0" role="button"
                     aria-label={`${p.c.name}, score ${p.c.score}, ${p.c.tier}${p.c.portfolio ? ", Anti Fund portfolio" : ""}`}
                     onMouseEnter={show} onFocus={show} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}
                     onClick={onToggle} onKeyDown={(e) => e.key === "Enter" && onToggle()}>
                    <circle class="hit" cx={cx} cy={cy} r="12" />
                    <circle class="dot" cx={cx} cy={cy} r="5" />
                  </g>
                );
              })}
              {labeled.map((p) => (
                <text key={`l-${p.c.slug}`} class="dot-label" x={p.px + (p.side === "right" ? 10 : -10)} y={mid + p.slot * STEP + 4}
                      text-anchor={p.side === "right" ? "start" : "end"}>{p.c.name}</text>
              ))}
            </svg>
          )}
        </div>
      </Row>
      {open && <Evidence lane={lane} />}
    </div>
  );
}

function Tip({ tip }) {
  const { c, rect } = tip;
  return (
    <div class="tip fixed" style={{ left: `${rect.left + rect.width / 2}px`, top: `${rect.top - 8}px` }}>
      <strong>{c.name}</strong>
      <span>{c.portfolio ? "Anti Fund portfolio · " : ""}score {c.score}, {c.tier}</span>
      {c.facts.slice(0, 3).map((f) => <span key={f.id} class="fact">{f.text}</span>)}
    </div>
  );
}

function Evidence({ lane }) {
  return (
    <table class="evidence">
      <thead>
        <tr><th>Company</th><th>Tier</th><th class="num">Score</th><th>Public evidence</th></tr>
      </thead>
      <tbody>
        {lane.companies.map((c) => (
          <tr key={c.slug}>
            <td>{c.name}{c.portfolio && <span class="tag">Anti Fund</span>}</td>
            <td>{c.tier}</td>
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
