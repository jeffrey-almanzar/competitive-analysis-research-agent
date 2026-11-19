import Link from "next/link";
import ResearchForm from "@/components/ResearchForm";
import { getModels, listRuns } from "@/lib/api";
import { formatDate, shortModel } from "@/lib/format";
import type { ModelList, Run } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: Run[] = [];
  let modelList: ModelList | null = null;
  let apiDown = false;
  try {
    [runs, modelList] = await Promise.all([listRuns().then((r) => r ?? []), getModels()]);
  } catch {
    apiDown = true;
  }

  return (
    <>
      <section className="hero rise">
        <p className="eyebrow">Competitive intelligence</p>
        <h1>
          Who are you <em>up against?</em>
        </h1>
        <p>
          Describe what you want to build. The agent finds your competitors, reads their sites, pricing and reviews,
          and checks every claim against the page it came from.
        </p>
      </section>

      <div className="rise rise-2">
        <ResearchForm modelList={modelList} />
      </div>

      <section className="log rise rise-3" aria-labelledby="log-heading">
        <div className="log__head">
          <h2 id="log-heading">Recent reports</h2>
          {runs.length > 0 && <span className="mono faint">{runs.length} shown</span>}
        </div>
        {apiDown ? (
          <p className="form-error">
            Can&apos;t reach the research API. Start it with <code className="mono">docker compose up -d</code>.
          </p>
        ) : runs.length === 0 ? (
          <p className="muted">No reports yet. Describe an idea above to run your first one.</p>
        ) : (
          <ul>
            {runs.map((run) => (
              <li key={run.id}>
                <Link href={`/reports/${run.id}`} className="panel">
                  <span className={`dot dot--${run.status}`} aria-label={run.status} />
                  <span className="log__idea">{run.idea}</span>
                  <span className="mono faint">
                    {run.model ? `${shortModel(run.model)} · ` : ""}
                    {formatDate(run.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
