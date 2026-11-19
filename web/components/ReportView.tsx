import type { CSSProperties } from "react";
import { formatDate, hostOf, pathOf, percent, shortModel } from "@/lib/format";
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

// Claims about what customers say go in the side column; facts about the product in the main one.
const SIDE_CATEGORIES = new Set<ClaimCategory>(["customer_praise", "customer_complaint", "weakness"]);

const EVIDENCE_SHOWN = 3;
const STRIP_SWEEP_MS = 900; // total time for the verification strip to light up

const claimAnchor = (id: string) => `claim-${id}`;

type Evidence = { id: string; competitor: string; text: string };

export default function ReportView({ runId, report }: { runId: string; report: Report }) {
  const { stats } = report;
  const flaggedClaims = stats.claims_total - stats.claims_verified;

  const evidence = new Map<string, Evidence>();
  for (const c of report.competitors) {
    for (const cl of c.claims) evidence.set(cl.id, { id: cl.id, competitor: c.name, text: cl.text });
    for (const p of c.pricing) evidence.set(p.id, { id: p.id, competitor: c.name, text: `${p.plan_name}: ${p.price}` });
  }

  // Strongest first (the order the analysis returns), unconfirmed gaps last.
  const gaps = [...report.gaps.filter((g) => g.supported), ...report.gaps.filter((g) => !g.supported)];

  return (
    <article>
      <header className="report-head rise">
        <p className="eyebrow">Competitive analysis</p>
        <h1>{report.idea}</h1>
        <div className="report-meta">
          <span className="chip">{formatDate(report.generated_at)}</span>
          <span className="chip">{report.competitors.length} competitors</span>
          <span className="chip">{shortModel(report.model)}</span>
          <a className="chip" href={`/api/research/${runId}/report.md`} download>
            ↓ Markdown
          </a>
        </div>
      </header>

      <VerificationPanel report={report} flaggedClaims={flaggedClaims} />

      {gaps.length > 0 && (
        <section className="section" aria-labelledby="gaps-heading">
          <div className="section__head">
            <h2 id="gaps-heading">Where competitors fall short</h2>
            <span className="mono faint">ranked by strength of evidence</span>
          </div>
          <div className="gaps">
            {gaps.map((gap, i) => (
              <GapCard key={gap.title} gap={gap} rank={i + 1} evidence={evidence} />
            ))}
          </div>
        </section>
      )}

      <section className="section" aria-labelledby="competitors-heading">
        <div className="section__head">
          <h2 id="competitors-heading">Competitors</h2>
          <span className="mono faint">click a claim to see its source quote</span>
        </div>
        <div className="competitors">
          {report.competitors.map((c) => (
            <CompetitorPanel key={c.rank} competitor={c} />
          ))}
        </div>
      </section>

      {report.errors.length > 0 && (
        <section className="section errors" aria-labelledby="errors-heading">
          <div className="section__head">
            <h2 id="errors-heading">Gaps in this research</h2>
          </div>
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

function VerificationPanel({ report, flaggedClaims }: { report: Report; flaggedClaims: number }) {
  const { stats } = report;
  // One segment per claim and price, in report order: the report's evidence, at a glance.
  const items = report.competitors.flatMap((c) => [...c.pricing, ...c.claims]);
  const step = items.length ? STRIP_SWEEP_MS / items.length : 0;

  return (
    <section className="panel verification rise rise-2" aria-labelledby="verification-heading">
      <h2 id="verification-heading" className="eyebrow" style={{ fontFamily: "var(--font-mono)", fontWeight: 400 }}>
        Source check
      </h2>
      <div className="verification__readouts">
        <div className="readout readout--primary">
          <div className="readout__value">
            {percent(stats.claims_verified, stats.claims_total)}
            <small>%</small>
          </div>
          <div className="readout__label">
            {stats.claims_verified} of {stats.claims_total} claims verified
          </div>
        </div>
        <div className="readout">
          <div className="readout__value">
            {stats.prices_verified}
            <small>/{stats.prices_total}</small>
          </div>
          <div className="readout__label">prices confirmed</div>
        </div>
        <div className="readout">
          <div className="readout__value">{stats.gaps_supported}</div>
          <div className="readout__label">evidence-backed gaps</div>
        </div>
      </div>
      <div
        className="strip"
        role="img"
        aria-label={`${stats.claims_verified + stats.prices_verified} of ${items.length} claims and prices verified`}
      >
        {items.map((item, i) => (
          <span
            key={item.id}
            className={`strip__seg${item.verified ? "" : " strip__seg--flagged"}`}
            style={{ animationDelay: `${Math.round(i * step)}ms` } as CSSProperties}
          />
        ))}
      </div>
      <div className="strip-legend">
        <span>
          <span className="legend-key" />
          Quote found word for word on the cited page
        </span>
        <span>
          <span className="legend-key legend-key--flagged" />
          Unconfirmed{flaggedClaims + (stats.prices_total - stats.prices_verified) > 0 ? "" : " (none)"}
        </span>
      </div>
    </section>
  );
}

function EvidenceList({ items }: { items: Evidence[] }) {
  return (
    <ul>
      {items.map((e) => (
        <li key={e.id}>
          <a href={`#${claimAnchor(e.id)}`}>
            <span className="faint">{e.competitor} · </span>
            {e.text}
          </a>
        </li>
      ))}
    </ul>
  );
}

function GapCard({ gap, rank, evidence }: { gap: MarketGap; rank: number; evidence: Map<string, Evidence> }) {
  const items = gap.evidence_ids.flatMap((id) => {
    const e = evidence.get(id);
    return e ? [e] : [];
  });
  return (
    <div className={`panel gap${gap.supported ? "" : " gap--flagged"}`}>
      <span className="gap__rank">
        {gap.supported ? `Gap ${String(rank).padStart(2, "0")}` : "Unconfirmed: no verified evidence"}
      </span>
      <h3>{gap.title}</h3>
      <p>{gap.description}</p>
      <p className="gap__standout">
        <strong>How to stand out</strong>
        {gap.how_to_stand_out}
      </p>
      {items.length > 0 && (
        <div className="gap__evidence">
          <p className="mono faint">Evidence · {items.length}</p>
          <EvidenceList items={items.slice(0, EVIDENCE_SHOWN)} />
          {items.length > EVIDENCE_SHOWN && (
            <details>
              <summary>Show {items.length - EVIDENCE_SHOWN} more</summary>
              <EvidenceList items={items.slice(EVIDENCE_SHOWN)} />
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function ClaimGroups({ claims, categories }: { claims: Claim[]; categories: ClaimCategory[] }) {
  return (
    <>
      {categories.map((cat) => {
        const group = claims.filter((cl) => cl.category === cat && cl.verified);
        if (group.length === 0) return null;
        return (
          <div key={cat}>
            <h4 className="subhead">{CATEGORY_LABELS[cat]}</h4>
            <ul className="claims">
              {group.map((cl) => (
                <ClaimItem key={cl.id} item={cl} text={cl.text} />
              ))}
            </ul>
          </div>
        );
      })}
    </>
  );
}

function CompetitorPanel({ competitor: c }: { competitor: Competitor }) {
  const verifiedPrices = c.pricing.filter((p) => p.verified);
  const flaggedPrices = c.pricing.filter((p) => !p.verified);
  const flaggedClaims = c.claims.filter((cl) => !cl.verified);
  const reviewCount = c.sources.filter((s) => s.kind === "review").length;
  const mainCats = CATEGORY_ORDER.filter((cat) => !SIDE_CATEGORIES.has(cat));
  const sideCats = CATEGORY_ORDER.filter((cat) => SIDE_CATEGORIES.has(cat));

  return (
    <section className="panel competitor" aria-labelledby={`competitor-${c.rank}`}>
      <div className="competitor__head">
        <span className="competitor__rank">#{String(c.rank).padStart(2, "0")}</span>
        <h3 id={`competitor-${c.rank}`}>{c.name}</h3>
        <a className="chip" href={c.homepage_url} target="_blank" rel="noreferrer">
          {hostOf(c.homepage_url)} ↗
        </a>
      </div>
      <p className="competitor__why">{c.why_competitor}</p>

      <div className="competitor__grid">
        <div>
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
                    <td className="price">{p.price}</td>
                    <td>
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
          <ClaimGroups claims={c.claims} categories={mainCats} />
        </div>
        <div>
          <ClaimGroups claims={c.claims} categories={sideCats} />
          {(flaggedClaims.length > 0 || flaggedPrices.length > 0) && (
            <div className="flagged-block">
              <h4 className="subhead">Unconfirmed: don&apos;t rely on these</h4>
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
        </div>
      </div>

      <p className="competitor__foot mono faint">
        {c.sources.length} pages read · {reviewCount} review {reviewCount === 1 ? "page" : "pages"}
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
            <span className={item.verified ? "verified-note" : "flag-note"}>
              {item.verified ? "✓ Quote found on this page" : capitalize(item.note)}
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
