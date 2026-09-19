/** A ring showing `value` out of `max`. The number is the primary reading; the ring is the shape of it. */
export default function ScoreRing({ value, max = 5, size = 132, label }) {
  const stroke = Math.max(8, Math.round(size / 14));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = Math.max(0, Math.min(1, value / max));

  return (
    <div className="score-ring" style={{ width: size, height: size }} role="img" aria-label={`${label ?? "Score"}: ${value} out of ${max}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--bg-hover)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * fraction} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="score-ring-arc"
        />
      </svg>
      <div className="score-ring-value">
        <span className="score-ring-number" style={{ fontSize: size * 0.34 }}>{value}</span>
        <span className="score-ring-max">/ {max}</span>
      </div>
    </div>
  );
}
