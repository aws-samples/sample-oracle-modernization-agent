"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const fetcher = (url: string) => fetch(url).then(r => r.json());

const STEP_ORDER = ["pending", "transform", "review", "validate", "merge", "test", "completed"];
const STEP_COLORS: Record<string, string> = {
  pending: "bg-gray-500",
  transform: "bg-blue-500",
  review: "bg-yellow-500",
  validate: "bg-orange-500",
  merge: "bg-purple-500",
  test: "bg-red-500",
  completed: "bg-green-500",
};

export default function OverviewPage() {
  const { data, error, isLoading } = useSWR("/api/pipeline/status", fetcher, {
    refreshInterval: 5000,
  });

  if (isLoading) return <div className="text-muted-foreground">Loading...</div>;
  if (error) return <div className="text-destructive">Error: {error.message}</div>;
  if (!data) return null;

  const { steps, totals } = data;
  const stepMap = new Map(steps.map((s: { current_step: string; count: number }) => [s.current_step, s.count]));

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Pipeline Overview</h2>

      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Total SQL</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold">{totals.total}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Pass Rate</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-green-500">{totals.passRate}%</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Failed</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-red-500">{totals.failed}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Skipped</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-bold text-yellow-500">{totals.skipped}</div></CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Pipeline Progress</CardTitle></CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end h-40">
            {STEP_ORDER.map(step => {
              const count = (stepMap.get(step) || 0) as number;
              const pct = totals.total > 0 ? (count / totals.total) * 100 : 0;
              return (
                <div key={step} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-xs text-muted-foreground">{count}</span>
                  <div
                    className={`w-full rounded-t ${STEP_COLORS[step] || "bg-gray-400"}`}
                    style={{ height: `${Math.max(pct, 2)}%` }}
                  />
                  <span className="text-xs truncate w-full text-center">{step}</span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Step Counts</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {STEP_ORDER.map(step => {
              const count = (stepMap.get(step) || 0) as number;
              if (count === 0) return null;
              return (
                <Badge key={step} variant="secondary" className="text-sm">
                  {step}: {count}
                </Badge>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
