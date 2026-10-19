import { Suspense } from "react";
import { CircleAlert, OctagonAlert, Package, PackageX } from "lucide-react";
import { CourierUpload } from "@/components/courier-upload";
import { DataErrorState, DataSourceBanner, NoDataState, PageSkeleton, load } from "@/components/data-state";
import { KpiCard } from "@/components/kpi-card";
import { OrderRiskBoard } from "@/components/order-risk-board";
import { OrderRiskModelNote, OrderRiskUnavailable } from "@/components/order-risk-model-note";
import { PageHeader } from "@/components/page-header";
import { SavingsCalculator } from "@/components/savings-calculator";
import { EmptyState } from "@/components/states";
import { T } from "@/components/t";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getOrderRisk } from "@/lib/api/customer-intelligence";
import { formatNumber } from "@/lib/utils";

export default function OrderRiskPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Order Risk"
        description="Which recent orders are likely to be refused or returned, why, and what to do before shipping."
      />
      <Suspense fallback={<PageSkeleton cards={3} />}>
        <OrderRiskContent />
      </Suspense>
    </div>
  );
}

async function OrderRiskContent() {
  const result = await load(getOrderRisk);
  if (!result.ok) return <DataErrorState error={result.error} />;
  const data = result.data;
  if (data.meta.source === "demo") {
    return (
      <EmptyState
        icon={PackageX}
        title="Order Risk needs your own orders"
        description="There is no sample data for this page, because made-up risk numbers would be misleading. Connect the backend and import your orders to see it."
      />
    );
  }
  if (!data.meta.asOf) return <NoDataState />;
  const available = data.model.status === "available";

  return (
    <>
      <DataSourceBanner meta={data.meta} />
      {available ? <OrderRiskModelNote model={data.model} /> : <OrderRiskUnavailable model={data.model} />}

      {available ? (
        <>
          <section aria-label="Order risk summary" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <KpiCard
              label="High risk orders"
              value={formatNumber(data.levelCounts.High)}
              delta={null}
              note={`Last ${data.windowDays} days of data`}
              icon={OctagonAlert}
            />
            <KpiCard
              label="Medium risk orders"
              value={formatNumber(data.levelCounts.Medium)}
              delta={null}
              note={`Last ${data.windowDays} days of data`}
              icon={CircleAlert}
            />
            <KpiCard
              label="Orders checked"
              value={formatNumber(data.windowOrders)}
              delta={null}
              note={`Last ${data.windowDays} days of data`}
              icon={Package}
            />
          </section>

          <Card>
            <CardHeader>
              <CardTitle><T>Recent orders</T></CardTitle>
              <CardDescription>
                <T>The orders that need action come first. The percentage is the model&apos;s estimate, not a fact.</T>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <OrderRiskBoard data={data} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle><T>Savings estimate</T></CardTitle>
              <CardDescription>
                <T>What flagging these orders could have saved, worked out on past orders the model had not seen.</T>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <SavingsCalculator high={data.savingsHigh} mediumHigh={data.savingsMediumHigh} />
            </CardContent>
          </Card>
        </>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle><T>Courier results</T></CardTitle>
          <CardDescription>
            <T>Real delivered and returned results make the model more accurate than cancelled orders alone.</T>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CourierUpload />
        </CardContent>
      </Card>
    </>
  );
}
