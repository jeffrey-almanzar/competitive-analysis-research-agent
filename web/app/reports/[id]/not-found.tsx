import Link from "next/link";

export default function NotFound() {
  return (
    <section className="progress rise">
      <p className="eyebrow">404</p>
      <h1>No report at this link</h1>
      <p className="muted" style={{ marginTop: "1rem" }}>
        It may have been deleted, or the link is incomplete.
      </p>
      <p style={{ marginTop: "1.5rem" }}>
        <Link className="button" href="/">
          Start new research <span className="button__arrow">→</span>
        </Link>
      </p>
    </section>
  );
}
