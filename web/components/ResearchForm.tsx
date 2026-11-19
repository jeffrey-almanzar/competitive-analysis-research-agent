"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const COMPETITOR_OPTIONS = [3, 4, 5, 6, 8];

export default function ResearchForm() {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [count, setCount] = useState(6);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        body: JSON.stringify({ idea: idea.trim(), max_competitors: count }),
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
    <form className="research-form" onSubmit={onSubmit}>
      <label htmlFor="idea">What do you want to build?</label>
      <textarea
        id="idea"
        name="idea"
        value={idea}
        onChange={(e) => setIdea(e.target.value)}
        placeholder="e.g. Online booking and payments software for independent barbershops"
        maxLength={2000}
        required
      />
      <div className="research-form__row">
        <label htmlFor="count" className="muted" style={{ margin: 0, fontWeight: 400 }}>
          Competitors to research
        </label>
        <select id="count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
          {COMPETITOR_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "Starting research…" : "Research competitors"}
        </button>
      </div>
      <p className="form-note muted">Takes 1–2 minutes. Each report uses about $1 of API credit.</p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
