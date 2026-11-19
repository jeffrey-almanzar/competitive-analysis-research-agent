"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatUsd } from "@/lib/format";
import type { ModelList } from "@/lib/types";

const COMPETITOR_OPTIONS = [3, 4, 5, 6, 8, 10];

export default function ResearchForm({ modelList }: { modelList: ModelList | null }) {
  const router = useRouter();
  const models = modelList?.models ?? [];
  const [idea, setIdea] = useState("");
  const [count, setCount] = useState(6);
  // The API's default is the cheapest model.
  const [modelId, setModelId] = useState(modelList?.default ?? models[0]?.id ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const model = models.find((m) => m.id === modelId);
  const cheapestId = models.length
    ? models.reduce((a, b) => (b.est_cost_per_competitor < a.est_cost_per_competitor ? b : a)).id
    : undefined;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (idea.trim().length < 10) {
      setError("Describe the idea in at least a short sentence (10 characters or more).");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idea: idea.trim(), max_competitors: count, model: modelId }),
      });
      if (!res.ok) throw new Error(`The research API returned ${res.status}.`);
      const run = await res.json();
      router.push(`/reports/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? `Research didn't start. ${err.message}` : "Research didn't start.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      <div className="panel console">
        <div className="console__bar">
          <span className="eyebrow">New research</span>
          <span className="mono faint">~1–2 min</span>
        </div>
        <div className="console__body">
          <label className="prompt" htmlFor="idea">
            &gt; What do you want to build?
          </label>
          <textarea
            id="idea"
            name="idea"
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            placeholder="Online booking and payments software for independent barbershops"
            maxLength={2000}
            required
          />
        </div>

        <div className="console__controls">
          <div className="field">
            <label htmlFor="model">Model</label>
            <div className="select">
              <select
                id="model"
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                disabled={!models.length}
                aria-describedby="model-hint"
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                    {m.id === cheapestId ? " (lowest cost)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="field field--narrow">
            <label htmlFor="count">Competitors</label>
            <div className="select">
              <select id="count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
                {COMPETITOR_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button className="button console__submit" type="submit" disabled={submitting || !models.length}>
            {submitting ? "Starting research…" : "Research competitors"}
            {!submitting && <span className="button__arrow">→</span>}
          </button>
        </div>

        {model && (
          <div className="model-hint" id="model-hint" aria-live="polite">
            <p className="model-hint__capability">{model.capability}</p>
            <dl className="model-hint__stats">
              <div>
                <dt>Est. cost</dt>
                <dd className="model-hint__cost">
                  {formatUsd(model.est_cost_per_competitor * count)}
                  <span> for {count} competitors</span>
                </dd>
              </div>
              <div>
                <dt>Token price</dt>
                <dd>
                  {formatUsd(model.input_per_mtok)} in · {formatUsd(model.output_per_mtok)} out
                  <span> per million</span>
                </dd>
              </div>
              <div>
                <dt>Estimate basis</dt>
                <dd>{model.cost_measured ? "Measured on real reports" : "Scaled from measured Opus runs"}</dd>
              </div>
            </dl>
          </div>
        )}
      </div>
      {!models.length && (
        <p className="form-error">Model list unavailable. Check that the research API is running.</p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
