import { Orbit } from "./Orbit.jsx";
import { Report } from "./Report.jsx";
import { Lanes } from "./Lanes.jsx";
import { Thread } from "./Thread.jsx";
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
          Portfolio reporting is one of the hardest parts of running a fund: companies don't always report back.
          Physical companies can't hide what they build. Their contracts, filings, hiring and the ground itself are
          public record. Ground Truth reads that record to answer three questions.
        </p>
        <ol class="questions">
          <li><a href="#portfolio">Are our companies building what they said?</a></li>
          <li><a href="#lanes">Where does each one stand against its competitors?</a></li>
          <li><a href="#check">Does a new company walk into a giant?</a></li>
        </ol>
        <nav>
          <a href="#evidence">Evidence it works</a>
          <a href="#method">How it works</a>
        </nav>
      </header>

      <Thread laneMap={laneMap} />

      <section id="portfolio">
        <h2>1. Our companies</h2>
        <p class="sub">
          Reporting without asking: what each physical portfolio company did in the last 90 days, read off the public
          record.
        </p>
        <Report laneMap={laneMap} />
        <h3 id="orbit" class="part">From orbit</h3>
        <p class="sub">
          Monthly satellite frames of the sites they're building, with every public filing on the same timeline. The
          docket often says what comes next.
        </p>
        <Orbit />
        <h3 id="watch" class="part">Everything on the record</h3>
        <Watch />
      </section>

      <section id="lanes">
        <h2>2. Their lanes</h2>
        <p class="sub">
          Each lane of Anti Fund's thesis, ranked by what companies have physically built: federal contracts, factory
          hiring, licenses, fleets and sites. Not valuation. The growth fund sees who's executing; the seed fund sees
          where not to pick a fight.
        </p>
        <Lanes data={laneMap} />
      </section>

      <section id="check">
        <h2>3. The next company</h2>
        <p class="sub">
          Drop any company into the lanes above. The Check reads its website, places it in a lane, and says whether it
          would fight that lane's giants, sell to them, or have the space to itself, citing the record for every claim.
          When the map doesn't cover a market, it says so.
        </p>
        <Check laneMap={laneMap} />
        <h3 id="found" class="part">Where new companies show up first</h3>
        <p class="sub">
          New letters of intent to the NRC and new aircraft makers registering with the FAA: companies at formation,
          before most investors know them. Each one can go straight through the Check.
        </p>
        <Sourcing laneMap={laneMap} />
      </section>

      <section id="evidence">
        <h2>Evidence it works</h2>
        <p class="sub">
          The whole pipeline, run on every US hard-tech company that raised a pre-seed, seed or Series A round since
          January 2025: 912 companies from a PitchBook export. Only totals are shown here.
        </p>
        <Evidence />
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
