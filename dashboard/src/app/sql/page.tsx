"use client";

import { useState } from "react";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const fetcher = (url: string) => fetch(url).then(r => r.json());

const STATUS_COLORS: Record<string, string> = {
  PASS: "bg-green-500/20 text-green-400",
  FIXED: "bg-green-500/20 text-green-400",
  FAIL: "bg-red-500/20 text-red-400",
  SKIP: "bg-yellow-500/20 text-yellow-400",
};

export default function SqlExplorerPage() {
  const [search, setSearch] = useState("");
  const [stepFilter, setStepFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (stepFilter) params.set("step", stepFilter);
  if (statusFilter) params.set("status", statusFilter);
  params.set("limit", "200");

  const { data, isLoading } = useSWR(`/api/sql?${params}`, fetcher, { refreshInterval: 5000 });

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">SQL Explorer</h2>

      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search SQL ID or mapper..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="px-3 py-2 rounded-md border bg-background text-sm w-64"
        />
        <select value={stepFilter} onChange={e => setStepFilter(e.target.value)}
                className="px-3 py-2 rounded-md border bg-background text-sm">
          <option value="">All Steps</option>
          {["pending","transform","review","validate","merge","test","completed"].map(s =>
            <option key={s} value={s}>{s}</option>
          )}
        </select>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                className="px-3 py-2 rounded-md border bg-background text-sm">
          <option value="">All Status</option>
          {["PASS","FAIL","SKIP","FIXED"].map(s =>
            <option key={s} value={s}>{s}</option>
          )}
        </select>
        {data && <span className="text-sm text-muted-foreground self-center">{data.total} results</span>}
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 text-muted-foreground">Loading...</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Mapper</TableHead>
                  <TableHead>SQL ID</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Step</TableHead>
                  <TableHead>Test Result</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.data?.map((row: Record<string, unknown>) => (
                  <TableRow key={`${row.mapper_file}-${row.sql_id}`} className="cursor-pointer hover:bg-muted/50">
                    <TableCell className="font-mono text-xs">{String(row.mapper_file)}</TableCell>
                    <TableCell className="font-mono text-sm font-medium">{String(row.sql_id)}</TableCell>
                    <TableCell><Badge variant="outline">{String(row.sql_type)}</Badge></TableCell>
                    <TableCell><Badge variant="secondary">{String(row.current_step)}</Badge></TableCell>
                    <TableCell>
                      {row.test_result ? (
                        <Badge className={STATUS_COLORS[String(row.test_result)] || ""}>
                          {String(row.test_result)}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                      {row.test_notes ? String(row.test_notes).slice(0, 80) : ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
