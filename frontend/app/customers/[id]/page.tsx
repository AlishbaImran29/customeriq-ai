import { Suspense } from "react";
import Link from "next/link";
import { ArrowLeft, UserX } from "lucide-react";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { ChurnReasons } from "@/components/churn-reasons";
import { CustomerTools } from "@/components/customer-tools";
import { Money } from "@/components/money";
import { NotAvailableCell } from "@/components/not-available";
import { Badge, riskVariant } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, scoreTone } from "@/components/ui/progress";
import { EmptyState } from "@/components/states";
import { getCustomerDetail } from "@/lib/api/customer-intelligence";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";

export default function CustomerPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <div className="space-y-6">
      <Link href="/segmentation" className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        All customers
      </Link>
      <Suspense fallback={<PageSkeleton cards={4} />}>
        <CustomerContent params={params} />
      </Suspense>
    </div>
  );
}

function Stat({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 text-xl font-semibold tabular-nums text-ink">{children}</p>
      {note ? <p className="mt-1 text-xs text-muted">{note}</p> : null}
    </Card>
  );
}

async function CustomerContent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await load(() => getCustomerDetail(id));
  if (!result.ok) return <DataErrorState error={result.error} />;
  const detail = result.data;
  if (detail === null) {
    return (
      <EmptyState
        icon={UserX}
        title="Customer not found"
        description="There is no customer with this ID in your data. They may have been removed, or the link is wrong."
        action={
          <Link href="/segmentation" className="text-sm font-medium text-accent hover:text-accent">
            Back to all customers
          </Link>
        }
      />
    );
  }
  const { meta, customer, orders, ordersTotal } = detail;
  if (meta.source === "live" && !meta.asOf) return <NoDataState />;
  const live = meta.source === "live";
  const factors = [
    { label: "Purchase frequency", value: customer.healthFactors.purchaseFrequency },
    { label: "Spending behavior", value: customer.healthFactors.spendingBehavior },
    { label: "Engagement", value: customer.healthFactors.engagement },
    { label: "Activity trend", value: customer.healthFactors.activityTrend },
  ];

  return (
    <>
      <DataSourceBanner meta={meta} />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{customer.name}</h1>
          <p className="mt-1 break-words text-sm text-muted">
            {customer.email ? `${customer.email} · ` : ""}ID {customer.id}
            {customer.channel ? ` · ${customer.channel}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {customer.segment ? <Badge variant="info">{customer.segment}</Badge> : <Badge variant="default">Not segmented</Badge>}
          <Badge variant={riskVariant(customer.riskLevel)}>
            {customer.riskLevel}
            {customer.churnProbability !== null ? ` · ${formatPercent(customer.churnProbability, 0)} chance of leaving` : ""}
          </Badge>
        </div>
      </div>

      <section aria-label="Customer figures" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Spent so far"><Money value={customer.currentClv} /></Stat>
        <Stat label="Predicted CLV">
          {customer.predictedClv === null ? <NotAvailableCell /> : <Money value={customer.predictedClv} />}
        </Stat>
        <Stat label="Orders">{formatNumber(ordersTotal)}</Stat>
        <Stat label="Average order">
          {detail.averageOrderValue === null ? "—" : <Money value={detail.averageOrderValue} />}
        </Stat>
        <Stat label="Last purchase" note={customer.daysSinceLastOrder !== undefined ? `${formatNumber(customer.daysSinceLastOrder)} days before the last data day` : undefined}>
          {formatDate(customer.lastPurchase)}
        </Stat>
        <Stat label="First purchase">{detail.firstOrder ? formatDate(detail.firstOrder) : "—"}</Stat>
        <Stat label="Usual gap between orders">
          {detail.averageDaysBetweenOrders === null ? "—" : `${formatNumber(Math.round(detail.averageDaysBetweenOrders))} days`}
        </Stat>
        <Stat label="Health score" note="0–100, from the four factors below">{customer.healthScore}</Stat>
      </section>

      <ChurnReasons reasons={detail.churnReasons ?? []} />

      <CustomerTools customerId={customer.id} />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Why this health score</CardTitle>
            <CardDescription>Each factor is scored 0–100 against the other customers.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {factors.map((factor) => (
              <div key={factor.label}>
                <div className="mb-1.5 flex justify-between gap-2 text-sm">
                  <span className="text-ink-2">{factor.label}</span>
                  <span className="font-medium tabular-nums">{factor.value === null ? "No engagement data" : factor.value}</span>
                </div>
                {factor.value === null ? null : (
                  <Progress value={factor.value} label={factor.label} tone={scoreTone(factor.value)} />
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recommended action</CardTitle>
            <CardDescription>
              {live && customer.churnProbability === null
                ? "Based on the segment and how long it has been since the last order (rules, not a prediction)."
                : "Based on the segment and risk level."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-ink">{customer.recommendedAction}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Order history</CardTitle>
          <CardDescription>
            {orders.length === 0
              ? "The order list is not available in demo mode."
              : orders.length < ordersTotal
                ? `The latest ${formatNumber(orders.length)} of ${formatNumber(ordersTotal)} orders, newest first.`
                : "Every order, newest first."}
          </CardDescription>
        </CardHeader>
        {orders.length > 0 ? (
          <CardContent>
            <div className="max-h-96 overflow-auto rounded-xl border border-line/60">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Orders placed by {customer.name}</caption>
                <thead className="sticky top-0 bg-surface-2 text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Date</th>
                    <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                    <th scope="col" className="px-3 py-2 font-medium">Category</th>
                    <th scope="col" className="px-3 py-2 font-medium">Channel</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order, index) => (
                    <tr key={`${order.orderDate}-${index}`} className="border-t border-line/60">
                      <td className="whitespace-nowrap px-3 py-2 text-ink-2">{formatDate(order.orderDate)}</td>
                      <td className="px-3 py-2 text-right tabular-nums"><Money value={order.value} /></td>
                      <td className="px-3 py-2 text-ink-2">{order.category ?? <span className="text-faint">—</span>}</td>
                      <td className="px-3 py-2 text-ink-2">{order.channel ?? <span className="text-faint">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        ) : null}
      </Card>
    </>
  );
}
