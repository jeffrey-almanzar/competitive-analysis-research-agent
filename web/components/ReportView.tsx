import { formatDate, hostOf, pathOf, percent } from "@/lib/format";
import type { Claim, ClaimCategory, Competitor, MarketGap, PricePlan, Report } from "@/lib/types";

const CATEGORY_ORDER: ClaimCategory[] = [
  "product",
  "target_customer",
  "positioning",
  "feature",
  "strength",
  "weakness",
  "customer_praise",
  "customer_complaint",
  "other",
];

const CATEGORY_LABELS: Record<ClaimCategory, string> = {
  product: "Product",
  target_customer: "Who it's for",
  positioning: "Positioning",
  feature: "Features",
  strength: "Strengths",
  weakness: "Weaknesses",
  customer_praise: "What customers praise",
  customer_complaint: "What customers complain about",
  other: "Other",
};

const claimAnchor = (id: string) => `claim-${id}`;

export default function ReportView({ runId, report }: { runId: string; report: Report }) {
  const { stats } = report;
  const flaggedClaims = stats.claims_total - stats.claims_verified;
  const verifiedPct = percent(stats.claims_verified, stats.claims_total);

  // Gap evidence points at claims (c1-3) or prices (c1-p2) by id.
  const evidence = new Map<string, { competitor: string; text: string }>();
  for (const c of report.competitors) {
    for (const cl of c.claims) evidence.set(cl.id, { competitor: c.name, text: cl.text });
    for (const p of c.pricing) evidence.set(p.id, { competitor: c.name, text: `${p.plan_name}: ${p.price}` });
  }

  const supportedGaps = report.gaps.filter((g) => g.supported);
  const unsupportedGaps = report.gaps.filter((g) => !g.supported);

  return (
    <article>
      <header className="report-head">
        <p className="mono muted">Competitive analysis</p>
        <h1>{report.idea}</h1>
        <div className="report-meta mono muted">
          <span>{formatDate(report.generated_at)}</span>
          <span>{report.competitors.length} competitors</span>
          <span>{report.model}</span>
          <a href={`/api/research/${runId}/report.md`} download>
            Download Markdown
          </a>
        </div>
      </header>

      <div className="source-check">
        <div
          className="source-check__bar"
          role="img"
          aria-label={`${stats.claims_verified} of ${stats.claims_total} claims verified`}
        >
          <span className="source-check__verified" style={{ width: `${verifiedPct}%` }} />
          <span className="source-check__flagged" style={{ width: `${100 - verifiedPct}%` }} />
        </div>
        <p>
          <strong>
            {stats.claims_verified} of {stats.claims_total} claims
          </strong>{" "}
          and {stats.prices_verified} of {stats.prices_total} prices were found word for word on the page they cite.
          {flaggedClaims > 0
            ? ` The other ${flaggedClaims} are marked as unconfirmed.`
            : " Click any claim to see its quote."}
        </p>
      </div>

      {report.gaps.length > 0 && (
        <section className="section" aria-labelledby="gaps-heading">
          <h2 id="gaps-heading">Where competitors fall short</h2>
          <div className="gaps">
            {supportedGaps.map((gap) => (
              <GapCard key={gap.title} gap={gap} evidence={evidence} />
            ))}
            {unsupportedGaps.map((gap) => (
              <GapCard key={gap.title} gap={gap} evidence={evidence} />
            ))}
          </div>
        </section>
      )}

      <section className="section" aria-labelledby="competitors-heading">
        <h2 id="competitors-heading">Competitors</h2>
        {report.competitors.map((c) => (
          <CompetitorSection key={c.rank} competitor={c} />
        ))}
      </section>

      {report.errors.length > 0 && (
        <section className="section errors" aria-labelledby="errors-heading">
          <h2 id="errors-heading">Gaps in this research</h2>
          <ul>
            {report.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

const EVIDENCE_SHOWN = 3;

type Evidence = { id: string; competitor: string; text: string };

function EvidenceList({ items }: { items: Evidence[] }) {
  return (
    <ul>
      {items.map((e) => (
        <li key={e.id}>
          <a href={`#${claimAnchor(e.id)}`}>
            <span className="muted">{e.competitor}</span> {e.text}
          </a>
        </li>
      ))}
    </ul>
  );
}

function GapCard({ gap, evidence }: { gap: MarketGap; evidence: Map<string, { competitor: string; text: string }> }) {
  const items: Evidence[] = gap.evidence_ids.flatMap((id) => {
    const e = evidence.get(id);
    return e ? [{ id, ...e }] : [];
  });
  return (
    <div className={`gap${gap.supported ? "" : " gap--flagged"}`}>
      <h3>{gap.title}</h3>
      {!gap.supported && <p className="flag-note mono">Unconfirmed: no verified evidence</p>}
      <p>{gap.description}</p>
      <p className="gap__standout">
        <strong>How to stand out.</strong> {gap.how_to_stand_out}
      </p>
      {items.length > 0 && (
        <div className="gap__evidence">
          <p className="mono muted">Evidence · {items.length}</p>
          <EvidenceList items={items.slice(0, EVIDENCE_SHOWN)} />
          {items.length > EVIDENCE_SHOWN && (
            <details>
              <summary className="mono muted">Show {items.length - EVIDENCE_SHOWN} more</summary>
              <EvidenceList items={items.slice(EVIDENCE_SHOWN)} />
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function CompetitorSection({ competitor: c }: { competitor: Competitor }) {
  const verifiedPrices = c.pricing.filter((p) => p.verified);
  const flaggedPrices = c.pricing.filter((p) => !p.verified);
  const flaggedClaims = c.claims.filter((cl) => !cl.verified);
  const reviewCount = c.sources.filter((s) => s.kind === "review").length;

  return (
    <section className="competitor" aria-labelledby={`competitor-${c.rank}`}>
      <div className="competitor__head">
        <h3 id={`competitor-${c.rank}`}>{c.name}</h3>
        <a className="mono muted" href={c.homepage_url} target="_blank" rel="noreferrer">
          {hostOf(c.homepage_url)} ↗
        </a>
      </div>
      <p className="competitor__why">{c.why_competitor}</p>

      <h4 className="subhead">Pricing</h4>
      {verifiedPrices.length > 0 ? (
        <table className="pricing">
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Price</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {verifiedPrices.map((p) => (
              <tr key={p.id} id={claimAnchor(p.id)}>
                <td>{p.plan_name}</td>
                <td>{p.price}</td>
                <td className="mono">
                  <a href={p.source_url} target="_blank" rel="noreferrer" title={p.quote}>
                    {pathOf(p.source_url)}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No pricing could be confirmed on the pages read.</p>
      )}

      {CATEGORY_ORDER.map((cat) => {
        const claims = c.claims.filter((cl) => cl.category === cat && cl.verified);
        if (claims.length === 0) return null;
        return (
          <div key={cat}>
            <h4 className="subhead">{CATEGORY_LABELS[cat]}</h4>
            <ul className="claims">
              {claims.map((cl) => (
                <ClaimItem key={cl.id} item={cl} text={cl.text} />
              ))}
            </ul>
          </div>
        );
      })}

      {(flaggedClaims.length > 0 || flaggedPrices.length > 0) && (
        <div className="flagged-block">
          <h4 className="subhead">Unconfirmed — don&apos;t rely on these</h4>
          <ul className="claims">
            {flaggedPrices.map((p) => (
              <ClaimItem key={p.id} item={p} text={`${p.plan_name}: ${p.price}`} />
            ))}
            {flaggedClaims.map((cl) => (
              <ClaimItem key={cl.id} item={cl} text={cl.text} />
            ))}
          </ul>
        </div>
      )}

      <p className="mono muted" style={{ marginTop: "1rem" }}>
        Read {c.sources.length} pages ({reviewCount} reviews)
      </p>
    </section>
  );
}

function ClaimItem({ item, text }: { item: Claim | PricePlan; text: string }) {
  return (
    <li id={claimAnchor(item.id)} className={`claim${item.verified ? "" : " claim--flagged"}`}>
      <details>
        <summary>
          {text}
          <span className="source-chip">{hostOf(item.source_url)}</span>
        </summary>
        <div className="clipping">
          <blockquote>{item.quote}</blockquote>
          <div className="clipping__source">
            <a href={item.source_url} target="_blank" rel="noreferrer">
              {pathOf(item.source_url)} ↗
            </a>
            <span className={item.verified ? "" : "flag-note"}>
              {item.verified ? "Quote found on this page" : capitalize(item.note)}
            </span>
          </div>
        </div>
      </details>
    </li>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
