import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatScore } from "../utils/format";

// Fixed order, so a criterion keeps its colour everywhere it appears.
export const CRITERIA = [
  { key: "correctness", label: "Correctness", token: "--series-1" },
  { key: "clarity", label: "Clarity", token: "--series-2" },
  { key: "depth", label: "Depth", token: "--series-3" },
];

function useChartColors() {
  return useMemo(() => {
    const styles = getComputedStyle(document.documentElement);
    const read = (name) => styles.getPropertyValue(name).trim();
    return {
      series: CRITERIA.map((criterion) => ({ ...criterion, color: read(criterion.token) })),
      grid: read("--border-subtle"),
      axis: read("--border"),
      text: read("--text-3"),
      surface: read("--bg-surface"),
      reduced: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    };
  }, []);
}

function ChartTooltip({ active, payload, label, series }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip-title">Question {label.replace("Q", "")}</p>
      {series.map((item) => (
        <p key={item.key} className="chart-tooltip-row">
          <span className="legend-swatch" style={{ background: item.color }} aria-hidden="true" />
          <span>{item.label}</span>
          <strong>{formatScore(row[item.key])}</strong>
        </p>
      ))}
    </div>
  );
}

/** Each answered question's three scores. Scores run 1 to 5, and the bars start from 0. */
export default function ScoresChart({ turns }) {
  const colors = useChartColors();
  const [asTable, setAsTable] = useState(false);
  const data = turns.map((turn) => ({
    name: `Q${turn.question_number}`,
    correctness: turn.correctness,
    clarity: turn.clarity,
    depth: turn.depth,
  }));

  return (
    <div className="scores-chart">
      <div className="chart-head">
        <ul className="legend" aria-label="Legend">
          {colors.series.map((item) => (
            <li key={item.key}>
              <span className="legend-swatch" style={{ background: item.color }} aria-hidden="true" />
              {item.label}
            </li>
          ))}
        </ul>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAsTable((value) => !value)} aria-pressed={asTable}>
          {asTable ? "View as chart" : "View as table"}
        </button>
      </div>

      {asTable ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Question</th>
                {CRITERIA.map((item) => <th key={item.key} scope="col">{item.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr key={row.name}>
                  <th scope="row">{row.name}</th>
                  {CRITERIA.map((item) => <td key={item.key}>{formatScore(row[item.key])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div role="img" aria-label="Bar chart of correctness, clarity and depth scores for each question. A table view is available." style={{ height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} barGap={2} barCategoryGap="26%" margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={colors.grid} />
              <XAxis dataKey="name" tickLine={false} axisLine={{ stroke: colors.axis }} tick={{ fill: colors.text, fontSize: 12 }} />
              <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} tickLine={false} axisLine={false} width={36} tick={{ fill: colors.text, fontSize: 12 }} />
              <Tooltip cursor={{ fill: "rgb(255 255 255 / 0.04)" }} content={<ChartTooltip series={colors.series} />} />
              {colors.series.map((item) => (
                <Bar
                  key={item.key}
                  dataKey={item.key}
                  fill={item.color}
                  stroke={colors.surface}
                  strokeWidth={2}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={16}
                  isAnimationActive={!colors.reduced}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
