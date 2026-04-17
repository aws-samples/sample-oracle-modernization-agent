"use client";

import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const fetcher = (url: string) => fetch(url).then(r => r.json());

export default function AnalysisPage() {
  const { data } = useSWR("/api/sql?status=FAIL&limit=500", fetcher, { refreshInterval: 10000 });

  const failures = data?.data || [];
  const categories: Record<string, typeof failures> = {};
  for (const f of failures) {
    const notes = String(f.test_notes || "");
    let cat = "other";
    if (notes.match(/invalid input|operator does not exist|type mismatch/i)) cat = "parameter";
    else if (notes.match(/syntax error|unexpected/i)) cat = "sql_syntax";
    else if (notes.match(/does not exist|unknown column|relation/i)) cat = "schema";
    else if (notes.match(/class|connection|timeout|java/i)) cat = "infra";
    categories[cat] = categories[cat] || [];
    categories[cat].push(f);
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">FAIL Analysis</h2>

      <div className="grid grid-cols-4 gap-4">
        {Object.entries(categories).sort((a, b) => b[1].length - a[1].length).map(([cat, items]) => (
          <Card key={cat}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{cat}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{items.length}</div>
            </CardContent>
          </Card>
        ))}
        {failures.length === 0 && (
          <Card>
            <CardContent className="pt-6">
              <div className="text-muted-foreground">No failures found</div>
            </CardContent>
          </Card>
        )}
      </div>

      {Object.entries(categories).map(([cat, items]) => (
        <Card key={cat}>
          <CardHeader><CardTitle>{cat} ({items.length})</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {items.slice(0, 20).map((f: Record<string, unknown>) => (
                <div key={`${f.mapper_file}-${f.sql_id}`} className="flex items-center gap-3 text-sm">
                  <Badge variant="destructive" className="text-xs">FAIL</Badge>
                  <span className="font-mono">{String(f.mapper_file)}:{String(f.sql_id)}</span>
                  <span className="text-muted-foreground truncate flex-1">{String(f.test_notes || "").slice(0, 100)}</span>
                </div>
              ))}
              {items.length > 20 && <div className="text-sm text-muted-foreground">... and {items.length - 20} more</div>}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
