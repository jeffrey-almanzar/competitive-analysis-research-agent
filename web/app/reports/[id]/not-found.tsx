import Link from "next/link";

export default function NotFound() {
  return (
    <section className="progress">
      <h1>No report with this link</h1>
      <p className="muted">It may have been deleted, or the link is incomplete.</p>
      <Link className="button" href="/">
        Start new research
      </Link>
    </section>
  );
}
