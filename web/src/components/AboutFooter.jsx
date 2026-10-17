// The about section at the bottom of every page: who built the tool, where it lives, what it borrows.

const TEAM = [
  ['Daniel Distor', 'dd745', 'DanielDistor'],
  ['Divyanshu Kekatpure', 'dmk323', 'DivyanshuKekatpure'],
  ['Duc Bui', 'dmb488', 'dmb488-ops'],
  ['Jonathan Ma', 'jjm498', 'jonathanjma'],
]
const LIVE = 'https://connect.systems-apps.com/content/60eb66a4-d370-4e6b-81e6-ae992820bd4e/'
const REPO = 'https://github.com/DanielDistor/classhackathon'

const Link = ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>

export default function AboutFooter() {
  return (
    <footer className="about-footer">
      <h4>About</h4>
      <p>
        <b>Team Flight Control</b> · Cornell Six Sigma Hackathon, October 2026. A quality-control tool for a drone
        delivery fleet's maintenance technician: which drones can fly, and which parts to replace before they fail.
      </p>
      <div className="team">
        {TEAM.map(([name, netid, gh]) => (
          <div key={netid} className="person">
            <b>{name}</b>
            <span>{netid}</span>
            <Link href={`https://github.com/${gh}`}>github.com/{gh}</Link>
          </div>
        ))}
      </div>
      <ul className="about-list">
        <li><b>Live app</b>: <Link href={LIVE}>Posit Connect</Link> · <b>Code</b>: <Link href={REPO}>github.com/DanielDistor/classhackathon</Link></li>
        <li><b>Methods</b>: Nelson / Western Electric rules, EWMA chart, Weibull life with censoring, Kaplan-Meier,
          age-replacement cost model (Barlow &amp; Proschan).</li>
        <li><b>Built with</b>: FastAPI, React, Vite, pandas, NumPy, SciPy, lifelines; written with help from Claude Code.</li>
        <li><b>Data</b>: simulated test fleets, not a real company's records.</li>
      </ul>
    </footer>
  )
}
