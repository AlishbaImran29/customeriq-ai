"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  HealthBucket,
  RevenueAtRiskPoint,
  RevenuePoint,
  RiskBucket,
  RiskLevel,
  SegmentSummary,
} from "@/lib/types";
import { formatMoney, getCurrencyState, useCurrency } from "@/lib/currency";
import { formatNumber } from "@/lib/utils";

// Read the current choice at call time; each currency chart calls useCurrency() so it redraws on change.
const formatCurrency = (value: number) => formatMoney(getCurrencyState(), value);
const formatCompactCurrency = (value: number) => formatMoney(getCurrencyState(), value, true);

// Validated categorical slots (see dataviz palette): series 1 and 2.
const SERIES_1 = "#22d3ee";
const SERIES_2 = "#a78bfa";
const GRID = "#263449";
const AXIS_TICK = { fontSize: 12, fill: "#94a3b8" };
const LEGEND_STYLE = { fontSize: 12, color: "#cbd5e1" };

const riskColors: Record<RiskLevel, string> = {
  Low: "#34d399",
  Medium: "#fbbf24",
  High: "#fb923c",
  Critical: "#fb7185",
};

const tooltipStyle = {
  borderRadius: 12,
  border: "1px solid #34465f",
  backgroundColor: "#162238",
  color: "#f1f5f9",
  fontSize: 12,
  boxShadow: "0 8px 24px rgb(0 0 0 / 0.5)",
};

function currencyTooltip(value: unknown) {
  if (Array.isArray(value)) {
    return `${formatCurrency(Number(value[0]))} – ${formatCurrency(Number(value[1]))}`;
  }
  return formatCurrency(Number(value));
}

function numberTooltip(value: unknown) {
  return formatNumber(Number(value));
}

/** Wraps a chart with an accessible name; the surrounding page offers a table view. */
function ChartFrame({
  label,
  height,
  children,
}: {
  label: string;
  height: number;
  children: React.ReactElement;
}) {
  return (
    <div role="img" aria-label={label} style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  );
}

export function RevenueForecastChart({ data }: { data: RevenuePoint[] }) {
  useCurrency();
  // Forecast series are only drawn when the data contains a forecast.
  const hasForecast = data.some((p) => p.forecast !== undefined);
  return (
    <ChartFrame
      label={hasForecast ? "Monthly revenue with a three-month forecast and confidence range" : "Monthly revenue"}
      height={300}
    >
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="month" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(value: number) => formatCompactCurrency(value)}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} />
        <Legend iconType="plainline" wrapperStyle={LEGEND_STYLE} />
        {hasForecast ? (
        <Area
          dataKey="range"
          name="Forecast range"
          stroke="none"
          fill={SERIES_2}
          fillOpacity={0.15}
          legendType="square"
          activeDot={false}
          connectNulls
          isAnimationActive={false}
        />
        ) : null}
        <Line
          dataKey="actual"
          name="Actual revenue"
          stroke={SERIES_1}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
        {hasForecast ? (
          <Line
            dataKey="forecast"
            name="Forecast"
            stroke={SERIES_2}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            connectNulls
            activeDot={{ r: 4 }}
          />
        ) : null}
      </ComposedChart>
    </ChartFrame>
  );
}

export function SegmentDonutChart({ data }: { data: SegmentSummary[] }) {
  return (
    <ChartFrame label="Share of customers by segment" height={280}>
      <PieChart>
        <Pie
          data={data}
          dataKey="customers"
          nameKey="name"
          innerRadius={62}
          outerRadius={96}
          paddingAngle={2}
          stroke="#111c2f"
          strokeWidth={2}
        >
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} formatter={numberTooltip} />
        <Legend iconType="circle" wrapperStyle={LEGEND_STYLE} />
      </PieChart>
    </ChartFrame>
  );
}

export function SegmentRevenueBars({ data }: { data: SegmentSummary[] }) {
  useCurrency();
  return (
    <ChartFrame label="Revenue by customer segment" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis
          type="number"
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: number) => formatCompactCurrency(value)}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={130}
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Bar dataKey="revenue" name="Revenue" radius={[0, 4, 4, 0]} barSize={22}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

export function ClvBySegmentChart({ data }: { data: SegmentSummary[] }) {
  useCurrency();
  const rows = data.map((s) => ({
    name: s.name.replace(" Customers", ""),
    current: s.avgClv,
    predicted: s.avgPredictedClv,
  }));
  // Predicted CLV is only drawn when a model has produced it.
  const hasPredicted = data.some((s) => s.avgPredictedClv !== null);
  return (
    <ChartFrame
      label={hasPredicted ? "Average current versus predicted CLV by segment" : "Average current CLV by segment"}
      height={300}
    >
      <BarChart data={rows} barGap={2} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="name" tick={AXIS_TICK} tickLine={false} axisLine={false} interval={0} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(value: number) => formatCompactCurrency(value)}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Legend wrapperStyle={LEGEND_STYLE} />
        <Bar dataKey="current" name="Current CLV" fill={SERIES_1} radius={[4, 4, 0, 0]} />
        {hasPredicted ? (
          <Bar dataKey="predicted" name="Predicted CLV" fill={SERIES_2} radius={[4, 4, 0, 0]} />
        ) : null}
      </BarChart>
    </ChartFrame>
  );
}

export function RevenueAtRiskChart({ data }: { data: RevenueAtRiskPoint[] }) {
  useCurrency();
  return (
    <ChartFrame label="Monthly revenue at risk" height={300}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="month" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={56}
          tickFormatter={(value: number) => formatCompactCurrency(value)}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Bar dataKey="atRisk" name="Revenue at risk" fill={SERIES_1} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function HealthDistributionChart({ data }: { data: HealthBucket[] }) {
  return (
    <ChartFrame label="Number of customers in each health score band" height={280}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={48}
          tickFormatter={(value: number) => formatNumber(value)}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={numberTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Bar dataKey="customers" name="Customers" fill={SERIES_1} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function RiskDistributionChart({ data }: { data: RiskBucket[] }) {
  return (
    <ChartFrame label="Number of customers at each churn risk level" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="level" tick={AXIS_TICK} tickLine={false} axisLine={false} />
        <YAxis
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          width={48}
          tickFormatter={(value: number) => formatNumber(value)}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={numberTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Bar dataKey="customers" name="Customers" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.level} fill={riskColors[entry.level]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/** Revenue of each sales channel as horizontal bars. The page also shows the same numbers as a table. */
export function ChannelRevenueChart({ data }: { data: { label: string; revenue: number }[] }) {
  useCurrency();
  return (
    <ChartFrame label="Revenue of each sales channel" height={Math.max(180, data.length * 44 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis
          type="number"
          tick={AXIS_TICK}
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: number) => formatCompactCurrency(value)}
        />
        <YAxis type="category" dataKey="label" tick={AXIS_TICK} tickLine={false} axisLine={false} width={88} />
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(34, 211, 238, 0.08)" }} />
        <Bar dataKey="revenue" name="Revenue" fill={SERIES_1} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ChartFrame>
  );
}
