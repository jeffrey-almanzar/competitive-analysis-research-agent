// A scope reticle: concentric arcs with a lit target, the "instrument" mark.
export default function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="24" y2="24">
          <stop offset="0" stopColor="#5ee6f0" />
          <stop offset="1" stopColor="#9b8cff" />
        </linearGradient>
      </defs>
      <circle cx="12" cy="12" r="10.25" stroke="url(#logo-g)" strokeWidth="1.5" strokeDasharray="48 16" />
      <circle cx="12" cy="12" r="5.75" stroke="url(#logo-g)" strokeWidth="1.5" opacity="0.7" />
      <circle cx="12" cy="12" r="1.9" fill="#5ee6f0" />
    </svg>
  );
}
