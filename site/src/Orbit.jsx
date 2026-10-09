import { useEffect, useMemo, useState } from "preact/hooks";
import { useData, day, SOURCE_NAMES } from "./data.js";

export function Orbit() {
  const sites = useData("sites.json");
  const [active, setActive] = useState(0);
  if (sites === undefined) return <p class="muted">Loading frames…</p>;
  if (!sites || !sites.length) return <p class="muted">Satellite frames are being prepared.</p>;
  return (
    <div class="orbit">
      <div class="filters" role="tablist" aria-label="Sites">
        {sites.map((s, i) => (
          <button type="button" key={s.slug} class="chip" role="tab" aria-selected={i === active} aria-pressed={i === active}
                  onClick={() => setActive(i)}>{s.label.split(",")[0]}</button>
        ))}
      </div>
      <Site key={sites[active].slug} site={sites[active]} />
    </div>
  );
}

function Site({ site }) {
  const frames = site.frames;
  const [i, setI] = useState(frames.length - 1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    frames.forEach((f) => (new Image().src = f.file)); // preload so playback doesn't stutter
  }, [frames]);
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setI((j) => (j + 1) % frames.length), 420);
    return () => clearInterval(t);
  }, [playing, frames.length]);

  const frame = frames[i];
  const asOf = (frame.date || frame.label).slice(0, 10);
  const shown = site.filings.filter((f) => f.date <= asOf).slice(-6).reverse();
  const after = site.filings.filter((f) => f.date > asOf).slice(-4).reverse();
  const credit = frame.kind === "aerial" ? "USDA NAIP aerial photography (public domain)" : frame.credit || "Contains modified Copernicus Sentinel data";

  return (
    <figure class="site card">
      <div class="site-view">
        <div>
          <div class="frame">
            <img src={frame.file} alt={`${site.label}, ${frame.kind === "aerial" ? "aerial photo" : "satellite image"}, ${frame.label}`} />
            <span class="stamp">{frame.kind === "aerial" ? `Before: aerial photo, ${frame.label}` : frame.label}</span>
          </div>
          <div class="controls">
            <button type="button" onClick={() => setPlaying(!playing)}>{playing ? "Pause" : "Play"}</button>
            <input type="range" min="0" max={frames.length - 1} value={i} aria-label="Choose a month"
                   onInput={(e) => { setPlaying(false); setI(+e.currentTarget.value); }} />
          </div>
          <Timeline frames={frames} filings={site.filings} current={i} onPick={(j) => { setPlaying(false); setI(j); }} />
          <p class="credit">{credit}</p>
        </div>
        <figcaption>
          <h3>{site.label}</h3>
          <p class="muted">On the record by {frame.label}:</p>
          {shown.length ? (
            <ul class="filings">
              {shown.map((f) => (
                <li key={f.evidence_url + f.date + f.headline}>
                  <span class="date">{f.date}</span>
                  <a href={f.evidence_url} target="_blank" rel="noopener noreferrer">{f.headline}</a>
                  <span class="source">{SOURCE_NAMES[f.source] || f.source}</span>
                </li>
              ))}
            </ul>
          ) : <p class="muted">Nothing on the record yet at this point.</p>}
          {i === frames.length - 1 && after.length > 0 && (
            <div class="after">
              <p class="muted">Filed since this image, so watch for it next:</p>
              <ul class="filings">
                {after.map((f) => (
                  <li key={f.evidence_url + f.date + f.headline}>
                    <span class="date">{f.date}</span>
                    <a href={f.evidence_url} target="_blank" rel="noopener noreferrer">{f.headline}</a>
                    <span class="source">{SOURCE_NAMES[f.source] || f.source}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </figcaption>
      </div>
    </figure>
  );
}

const W = 600, H = 64, PAD = 14, AXIS_Y = 30;

function Timeline({ frames, filings, current, onPick }) {
  const [tip, setTip] = useState(null);
  const sat = frames.filter((f) => f.kind !== "aerial");
  const start = day(sat[0]?.date || sat[0]?.label || frames[0].label);
  const end = day(sat[sat.length - 1]?.date || sat[sat.length - 1]?.label);
  const x = (d) => PAD + ((day(d) - start) / Math.max(1, end - start)) * (W - 2 * PAD);
  const years = useMemo(() => {
    const out = [];
    for (let y = start.getUTCFullYear(); y <= end.getUTCFullYear(); y++) {
      if (day(`${y}-01-01`) >= start && day(`${y}-01-01`) <= end) out.push(y);
    }
    return out;
  }, [start.getTime(), end.getTime()]);
  const inRange = filings.filter((f) => day(f.date) >= start && day(f.date) <= end);
  const cur = frames[current];
  const curX = cur.kind === "aerial" ? null : x(cur.date || cur.label);

  return (
    <div class="timeline" onMouseLeave={() => setTip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Filings and milestones over time">
        <line class="axis" x1={PAD} x2={W - PAD} y1={AXIS_Y} y2={AXIS_Y} />
        {years.map((y) => (
          <g key={y}>
            <line class="tick" x1={x(`${y}-01-01`)} x2={x(`${y}-01-01`)} y1={AXIS_Y - 6} y2={AXIS_Y + 6} />
            <text class="tick-label" x={x(`${y}-01-01`)} y={AXIS_Y + 24} text-anchor="middle">{y}</text>
          </g>
        ))}
        {sat.map((f) => (
          <rect key={f.file} class="frame-hit" x={x(f.date || f.label) - 6} y={AXIS_Y - 14} width="12" height="28"
                onClick={() => onPick(frames.indexOf(f))} />
        ))}
        {curX !== null && <line class="now" x1={curX} x2={curX} y1={6} y2={AXIS_Y + 10} />}
        {inRange.map((f, k) => (
          <g key={k} class={`filing ${f.source === "news" ? "milestone" : ""}`} tabIndex="0" role="button"
             aria-label={`${f.date}: ${f.headline}`}
             onMouseEnter={() => setTip({ f, x: x(f.date) })} onFocus={() => setTip({ f, x: x(f.date) })}
             onBlur={() => setTip(null)}>
            <circle class="hit" cx={x(f.date)} cy={AXIS_Y} r="12" />
            <circle class="dot" cx={x(f.date)} cy={AXIS_Y} r="4.5" />
          </g>
        ))}
      </svg>
      {tip && (
        <div class="tip" style={{ left: `${(tip.x / W) * 100}%` }}>
          <strong>{tip.f.headline}</strong>
          <span>{tip.f.date} · {SOURCE_NAMES[tip.f.source] || tip.f.source}</span>
        </div>
      )}
    </div>
  );
}
