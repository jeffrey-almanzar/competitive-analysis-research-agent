import Link from "next/link";
import ResearchForm from "@/components/ResearchForm";
import { listRuns } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Run } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  let runs: Run[] = [];
  let apiDown = false;
  try {
    runs = (await listRuns()) ?? [];
  } catch {
    apiDown = true;
  }

  return (
    <>
      <section className="intro">
        <h1>Who are you up against?</h1>
        <p>
          Describe what you want to build. The agent finds your competitors, reads their sites, pricing and
          reviews, and checks every claim against the page it came from.
        </p>
      </section>

      <ResearchForm />

      <section className="recent" aria-labelledby="recent-heading">
        <h2 id="recent-heading">Recent reports</h2>
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
                <Link href={`/reports/${run.id}`}>
                  <span className="recent__idea">{run.idea}</span>
                  <span className={`status status--${run.status}`}>{run.status}</span>
                  <span className="mono muted">{formatDate(run.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
