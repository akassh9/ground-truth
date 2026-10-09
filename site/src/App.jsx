import { Orbit } from "./Orbit.jsx";
import { LaneMap } from "./LaneMap.jsx";
import { Check } from "./Check.jsx";
import { Evidence } from "./Evidence.jsx";
import { Watch } from "./Watch.jsx";
import { Sourcing } from "./Sourcing.jsx";
import { useData } from "./data.js";

export function App() {
  const laneMap = useData("lane_map.json");
  return (
    <main>
      <header class="hero">
        <p class="kicker">Ground Truth · built for Anti Fund</p>
        <h1>What physical companies leave behind.</h1>
        <p class="lede">
          Software leaves traces in code and web traffic. Companies that build factories, ships and reactors
          leave them in federal contracts, FAA registrations, NRC dockets, hiring, and the ground itself, seen
          from orbit. Ground Truth reads that record for Anti Fund's portfolio and the giants around it, and
          checks every new company against who's already there.
        </p>
        <nav>
          <a href="#orbit">From orbit</a>
          <a href="#lanes">Where the giants are</a>
          <a href="#check">The Check</a>
          <a href="#evidence">Evidence it works</a>
          <a href="#found">Found in the record</a>
          <a href="#watch">Portfolio watch</a>
          <a href="#method">How it works</a>
        </nav>
      </header>

      <section id="orbit">
        <h2>From orbit</h2>
        <p class="sub">
          Monthly satellite frames of the sites Anti Fund's companies are building, with every public filing on
          the same timeline. The docket often says what comes next.
        </p>
        <Orbit />
      </section>

      <section id="lanes">
        <h2>Where the giants are</h2>
        <p class="sub">
          Every lane in Anti Fund's thesis and how entrenched each company in it is, scored from public records
          only. The growth fund sees who is executing; the seed fund sees where not to pick a fight.
        </p>
        <LaneMap data={laneMap} />
      </section>

      <section id="check">
        <h2>The Check</h2>
        <p class="sub">
          Name any company. The Check reads its website, places it in a lane, and says whether it would fight an
          entrenched giant, sell to one, or have the space to itself, citing evidence for every claim. When the
          map doesn't cover a market, it says so.
        </p>
        <Check laneMap={laneMap} />
      </section>

      <section id="evidence">
        <h2>Evidence it works</h2>
        <p class="sub">
          The whole pipeline, run on every US hard-tech company that raised a pre-seed, seed or Series A round since
          January 2025: 912 companies from a PitchBook export. Only totals are shown here.
        </p>
        <Evidence />
      </section>

      <section id="found">
        <h2>Found in the public record</h2>
        <p class="sub">
          Companies at formation, before most investors know them: new letters of intent to the NRC, and new
          aircraft makers registering airframes with the FAA. Each one can go straight through the Check.
        </p>
        <Sourcing laneMap={laneMap} />
      </section>

      <section id="watch">
        <h2>Portfolio watch</h2>
        <p class="sub">The latest public signals from Anti Fund's physical portfolio.</p>
        <Watch />
      </section>

      <section id="method" class="method">
        <h2>How it works</h2>
        <Method />
      </section>
    </main>
  );
}

function Method() {
  return (
    <div class="columns">
      <div>
        <h3>Sources</h3>
        <ul>
          <li>Federal contracts, grants and subcontracts: USAspending.gov, matched by unique entity ID.</li>
          <li>Aircraft registrations, reservations and makers: the FAA's daily registry file.</li>
          <li>Nuclear licensing: the NRC's ADAMS public search.</li>
          <li>Hiring: companies' own public job boards.</li>
          <li>Imagery: Copernicus Sentinel-2 (modified) and USDA NAIP aerial photography.</li>
        </ul>
      </div>
      <div>
        <h3>Entrenchment score</h3>
        <ul>
          <li>Federal awards since 2020: up to 5 points ($1B or more).</li>
          <li>On a federal contract vehicle: 1.</li>
          <li>Factory-floor hiring: up to 3.</li>
          <li>FAA-registered fleet: up to 2.</li>
          <li>NRC: a license or construction permit held 3, an application 2, an active docket 1.</li>
          <li>A verified physical site: 2.</li>
        </ul>
        <p class="muted">Out of 16. 7 or more is entrenched; 4 to 6 is building. It measures what's on the ground and in
          the record, not valuation.</p>
      </div>
      <div>
        <h3>Checks on the checker</h3>
        <ul>
          <li>Every evidence id the Check cites must exist in the lane map.</li>
          <li>Company matches use federal IDs and docket numbers, never names alone; rejected look-alikes are kept on file.</li>
          <li>Website text is treated as untrusted data.</li>
          <li>Only public records appear here.</li>
        </ul>
      </div>
    </div>
  );
}
