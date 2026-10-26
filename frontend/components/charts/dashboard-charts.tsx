"use client";

import {
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
  RevenueAtRiskPoint,
  RevenuePoint,
  RiskBucket,
  RiskLevel,
  SegmentSummary,
} from "@/lib/types";
import { formatMoney } from "@/lib/currency";
import { formatNumber } from "@/lib/utils";

const formatCurrency = (value: number) => formatMoney(value);
const formatCompactCurrency = (value: number) => formatMoney(value, true);

// Validated categorical slot (see dataviz palette): series 1.
const SERIES_1 = "#2563eb";
const GRID = "#e2e8f0";
const AXIS_TICK = { fontSize: 12, fill: "#5b6b82" };
const LEGEND_STYLE = { fontSize: 12, color: "#334155" };

const riskColors: Record<RiskLevel, string> = {
  Low: "#16a34a",
  Medium: "#d97706",
  High: "#ea580c",
  Critical: "#dc2626",
};

const tooltipStyle = {
  borderRadius: 12,
  border: "1px solid #cbd5e1",
  backgroundColor: "#ffffff",
  color: "#1e293b",
  fontSize: 12,
  boxShadow: "0 4px 12px rgb(15 23 42 / 0.12)",
};

function currencyTooltip(value: unknown) {
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

export function RevenueTrendChart({ data }: { data: RevenuePoint[] }) {
  return (
    <ChartFrame label="Monthly revenue" height={300}>
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
        <Line
          dataKey="actual"
          name="Actual revenue"
          stroke={SERIES_1}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
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
          stroke="#ffffff"
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
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
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
  const rows = data.map((s) => ({ name: s.name.replace(" Customers", ""), current: s.avgClv }));
  return (
    <ChartFrame label="Average lifetime value to date, by segment" height={300}>
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
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
        <Legend wrapperStyle={LEGEND_STYLE} />
        <Bar dataKey="current" name="Average CLV to date" fill={SERIES_1} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function RevenueAtRiskChart({ data }: { data: RevenueAtRiskPoint[] }) {
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
        <Tooltip contentStyle={tooltipStyle} formatter={currencyTooltip} cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
        <Bar dataKey="atRisk" name="Revenue at risk" fill={SERIES_1} radius={[4, 4, 0, 0]} />
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
        <Tooltip contentStyle={tooltipStyle} formatter={numberTooltip} cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
        <Bar dataKey="customers" name="Customers" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={entry.level} fill={riskColors[entry.level]} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}
