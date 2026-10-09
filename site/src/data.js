import { useEffect, useState } from "preact/hooks";

const cache = new Map();

export function load(name) {
  if (!cache.has(name)) {
    cache.set(name, fetch(`/data/${name}`).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  }
  return cache.get(name);
}

/** The parsed JSON file from /data, or undefined while it loads (null if it's missing). */
export function useData(name) {
  const [data, setData] = useState(undefined);
  useEffect(() => {
    let live = true;
    load(name).then((d) => live && setData(d));
    return () => (live = false);
  }, [name]);
  return data;
}

export const day = (s) => new Date(`${s.length === 7 ? `${s}-15` : s.slice(0, 10)}T00:00:00Z`);

export function money(x) {
  for (const [size, unit] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]]) {
    if (x >= size) return `$${(x / size).toFixed(1).replace(/\.0$/, "")}${unit}`;
  }
  return `$${Math.round(x).toLocaleString()}`;
}

export const SOURCE_NAMES = {
  usaspending: "Federal awards",
  nrc: "NRC docket",
  faa: "FAA registry",
  jobs: "Job board",
  news: "Public report",
};

/** Fund policy, applied in code to every model's verdict: head-on with a portfolio company is a pass. */
export function fundCall(v) {
  return v.portfolio_conflicts?.length ? "pass" : v.call;
}
