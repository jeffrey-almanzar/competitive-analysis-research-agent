"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { shortModel } from "@/lib/format";
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
  return STEPS.findIndex((s) => s.key === step); // -1 while queued
}

function elapsed(fromIso: string, now: number): string {
  const s = Math.max(0, Math.floor((now - new Date(fromIso).getTime()) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function ProgressView({ initial }: { initial: Run }) {
  const router = useRouter();
  const [run, setRun] = useState(initial);
  const [pollError, setPollError] = useState(false);
  const [now, setNow] = useState<number | null>(null); // set after mount to avoid hydration mismatch

  useEffect(() => {
    if (run.status === "failed") return;
    setNow(Date.now());
    const clock = setInterval(() => setNow(Date.now()), 1000);
    const poll = setInterval(async () => {
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
    return () => {
      clearInterval(clock);
      clearInterval(poll);
    };
  }, [run.id, run.status, router]);

  const current = stepIndex(run.progress?.step);
  const { completed = 0, total = 0 } = run.progress ?? {};

  return (
    <section className="progress rise" aria-live="polite">
      <p className="eyebrow">Research in progress</p>
      <h1>{run.idea}</h1>

      <div className="progress__status">
        <span className="chip">
          <span className={`dot dot--${run.status}`} /> {run.status}
        </span>
        {run.model && <span className="chip">{shortModel(run.model)}</span>}
        {run.status !== "failed" && now !== null && <span className="chip">{elapsed(run.started_at ?? run.created_at, now)} elapsed</span>}
      </div>

      {run.status === "failed" ? (
        <>
          <p className="form-error" role="alert">
            Research stopped: {run.error ?? "unknown error"}
          </p>
          <p style={{ marginTop: "1.5rem" }}>
            <Link className="button" href="/">
              Start new research <span className="button__arrow">→</span>
            </Link>
          </p>
        </>
      ) : (
        <>
          <ol className="pipeline panel">
            {STEPS.map((step, i) => {
              const state = i < current ? "done" : i === current ? "active" : "todo";
              return (
                <li
                  key={step.key}
                  className={`node node--${state}`}
                  aria-current={state === "active" ? "step" : undefined}
                >
                  <span className="node__mark">{state === "done" ? "✓" : i + 1}</span>
                  <div className="node__label">
                    {step.label}
                    {step.key === "researching" && total > 0 && (
                      <>
                        <span className="mono faint">
                          {" "}
                          {completed}/{total}
                        </span>
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
          <p className="form-note">
            {run.status === "queued" ? "Waiting for a worker to pick this up." : run.progress?.message}
          </p>
          {pollError && <p className="form-error">Lost contact with the research API. Retrying…</p>}
        </>
      )}
    </section>
  );
}
