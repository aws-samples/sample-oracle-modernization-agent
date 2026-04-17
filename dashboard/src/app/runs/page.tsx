"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function RunsPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Run History</h2>
      <Card>
        <CardHeader><CardTitle>Recent Runs</CardTitle></CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Run history will be populated after pipeline executions with JSON logging enabled.
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            Each run creates a timestamped directory under output/logs/ with events.jsonl + summary.md.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
