/** The curated reading list, rendered under "Places to save".

 * A directory, not a record: it opens with <details> so thirteen sites do not
 * bury the cards above it, and every link leaves the app's own window the way a
 * place's own site link does - straight to the real browser. No rate, price or
 * return is shown as fact; the only figures are the fixed hypothetical walk,
 * which says out loud that it is not a prediction. */
import type { GuideEntry } from "./investmentGuide";
import {
  EXAMPLE_NOTE,
  EXAMPLE_OUTCOMES,
  EXAMPLE_STAKE,
  GUIDE_ENTRIES,
  STARTING_ORDER,
} from "./investmentGuide";

function GuideItem({ entry }: { entry: GuideEntry }) {
  return (
    <details className="guide-item" data-testid="guide-item">
      <summary>
        <strong>{entry.name}</strong>{" "}
        <span className="badge">{entry.category}</span>
        {entry.tags.map((t) => (
          <span className="guide-tag" key={t}>
            {t}
          </span>
        ))}{" "}
        <a
          className="site-link"
          href={entry.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open site
        </a>
      </summary>

      <p className="guide-summary">{entry.summary}</p>

      <p className="field-hint guide-heading">Getting started</p>
      <ol className="guide-list">
        {entry.steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>

      <p className="field-hint guide-heading">How you use it</p>
      <ul className="guide-list">
        {entry.use.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>

      {entry.benefit && <p className="guide-benefit">{entry.benefit}</p>}

      <p className="guide-caution">
        <strong>How you can lose money:</strong> {entry.caution}
      </p>
    </details>
  );
}

export function InvestmentGuidePanel() {
  return (
    <div className="card investment-guide">
      <h2>Investment and betting websites — Kenya and America</h2>
      <p className="muted">
        A reading list of where to learn, practise, research and - if you choose
        - put money to work. LifeSmart is not connected to any of these sites. It
        cannot check a fee, confirm that a platform still accepts Kenyan
        residents, or tell whether a provider is honest, so nothing below is a
        recommendation. Verify every provider independently before you send it
        money.
      </p>

      {GUIDE_ENTRIES.map((entry) => (
        <GuideItem entry={entry} key={entry.url} />
      ))}

      <div className="guide-example">
        <p className="field-hint guide-heading">
          Example: what can happen to {EXAMPLE_STAKE}?
        </p>
        <table className="guide-table">
          <thead>
            <tr>
              <th>Market movement</th>
              <th>Value after movement</th>
              <th>Profit or loss</th>
            </tr>
          </thead>
          <tbody>
            {EXAMPLE_OUTCOMES.map((row) => (
              <tr key={row.movement}>
                <td>{row.movement}</td>
                <td>{row.value_after}</td>
                <td className={row.direction === "gain" ? "gain" : "loss"}>
                  {row.change}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{EXAMPLE_NOTE}</p>
      </div>

      <p className="guide-order">{STARTING_ORDER}</p>
    </div>
  );
}
