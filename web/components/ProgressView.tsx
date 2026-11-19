"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ProgressStep, Run } from "@/lib/types";

const POLL_MS = 2500;

// The agent's steps, in the order the graph runs them.
const STEPS: { key: ProgressStep; label: string }[] = [
  { key: "planning", label: "Plan search queries" },
  { key: "finding_competitors", label: "Find competitors" },
  { key: "researching", label: "Read sites, pricing and reviews" },
  { key: "verifying", label: "Check every quote against its page" },
  { key: "analyzing_gaps", label: "Find market gaps" },
];

function stepIndex(step: ProgressStep | undefined): number {
  if (step === "done") return STEPS.length;
  const i = STEPS.findIndex((s) => s.key === step);
  return i; // -1 while queued
}

export default function ProgressView({ initial }: { initial: Run }) {
  const router = useRouter();
  const [run, setRun] = useState(initial);
  const [pollError, setPollError] = useState(false);

  useEffect(() => {
    if (run.status === "failed") return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/research/${run.id}`, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const next: Run = await res.json();
        setPollError(false);
        setRun(next);
        if (next.status === "succeeded") router.refresh();
      } catch {
        setPollError(true);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [run.id, run.status, router]);

  const current = stepIndex(run.progress?.step);
  const { completed = 0, total = 0 } = run.progress ?? {};

  return (
    <section className="progress" aria-live="polite">
      <p className="mono muted">Researching</p>
      <h1>{run.idea}</h1>

      {run.status === "failed" ? (
        <>
          <p className="form-error" role="alert">
            Research stopped: {run.error ?? "unknown error"}
          </p>
          <Link className="button" href="/">
            Start new research
          </Link>
        </>
      ) : (
        <>
          <p className="muted">
            {run.status === "queued" ? "Waiting for a worker to pick this up." : run.progress?.message}
          </p>
          <ol className="steps">
            {STEPS.map((step, i) => {
              const state = i < current ? "done" : i === current ? "active" : "todo";
              return (
                <li key={step.key} className={`step step--${state}`} aria-current={state === "active" ? "step" : undefined}>
                  <div>
                    {step.label}
                    {step.key === "researching" && total > 0 && (
                      <>
                        <span className="mono muted"> {completed}/{total}</span>
                        <div className="ticks" aria-hidden="true">
                          {Array.from({ length: total }, (_, n) => (
                            <span key={n} className={`tick${n < completed ? " tick--done" : ""}`} />
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {pollError && <p className="form-error">Lost contact with the research API. Retrying…</p>}
        </>
      )}
    </section>
  );
}
