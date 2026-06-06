"use client";

import { cn } from "@/lib/utils";

/**
 * Tiny inline SVG sparkline — used for the donor response_rate trend.
 *
 * Values are normalized into the [0..1] range by default (sensible for
 * response_rate which is already in that range). Pass `domain` to override.
 */
export function Sparkline({
  values,
  width = 140,
  height = 36,
  stroke = "currentColor",
  fill = "none",
  className,
  domain = [0, 1],
  showArea = true,
  testid = "sparkline",
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
  className?: string;
  domain?: [number, number];
  showArea?: boolean;
  testid?: string;
}) {
  if (values.length === 0) {
    return (
      <svg
        width={width}
        height={height}
        data-testid={testid}
        data-empty="true"
        className={cn("text-white/40", className)}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="No data"
      />
    );
  }

  const [lo, hi] = domain;
  const span = Math.max(hi - lo, 1e-6);
  const xStep = values.length > 1 ? width / (values.length - 1) : width / 2;
  const y = (v: number) => {
    const clamped = Math.max(lo, Math.min(hi, v));
    return height - ((clamped - lo) / span) * height;
  };

  const points = values.map((v, i) => [i * xStep, y(v)] as const);
  const pathD = points
    .map(([x, ypx], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${ypx.toFixed(2)}`)
    .join(" ");

  const areaD = showArea
    ? `${pathD} L${(values.length - 1) * xStep},${height} L0,${height} Z`
    : null;

  // Mark last point so the eye lands on the current value
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg
      width={width}
      height={height}
      data-testid={testid}
      data-points={values.length}
      className={cn(className)}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Sparkline of ${values.length} points`}
    >
      {areaD ? (
        <path
          d={areaD}
          fill={stroke}
          fillOpacity={0.12}
          stroke="none"
        />
      ) : null}
      <path
        d={pathD}
        stroke={stroke}
        strokeWidth={1.5}
        fill={fill}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={2.2} fill={stroke} />
    </svg>
  );
}
