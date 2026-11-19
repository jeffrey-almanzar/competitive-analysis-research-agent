export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function pathOf(url: string): string {
  try {
    const u = new URL(url);
    const path = u.pathname === "/" ? "" : u.pathname;
    return `${u.hostname.replace(/^www\./, "")}${path}`;
  } catch {
    return url;
  }
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function percent(n: number, total: number): number {
  return total ? Math.round((100 * n) / total) : 0;
}

// "claude-sonnet-5-5" -> "Sonnet 5.5" for compact labels.
export function shortModel(id: string | null | undefined): string {
  if (!id) return "";
  const m = id.match(/^claude-([a-z]+)-(\d+)-(\d+)$/);
  return m ? `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}` : id;
}

export function formatUsd(n: number): string {
  if (n > 0 && n < 0.01) return "under $0.01";
  return `$${n.toFixed(2)}`;
}
