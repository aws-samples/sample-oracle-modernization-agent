"use client";

import { useState } from "react";
import useSWR from "swr";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const fetcher = (url: string) => fetch(url).then(r => r.json());

const STEPS = [
  { name: "analyze", label: "Source Analysis", required: true },
  { name: "transform", label: "SQL Transform", required: true },
  { name: "review", label: "Multi-Perspective Review", required: false },
  { name: "validate", label: "Equivalence Validation", required: false },
  { name: "merge", label: "Mapper Merge", required: true },
  { name: "test", label: "DB Execution Test", required: true },
];

export default function ControlPage() {
  const [launching, setLaunching] = useState<string | null>(null);

  const { data: runStatus, mutate } = useSWR("/api/pipeline/run", fetcher, {
    refreshInterval: 3000,
  });

  const running = runStatus?.running;
  const isRunning = running?.alive === true;

  const handleRun = async (step: string) => {
    setLaunching(step);
    try {
      const res = await fetch(`/api/pipeline/run?step=${step}`, { method: "POST" });
      const data = await res.json();
      if (data.error) {
        alert(data.error);
      }
      mutate();
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setLaunching(null);
    }
  };

  const elapsed = running?.startedAt
    ? Math.round((Date.now() - new Date(running.startedAt).getTime()) / 1000)
    : 0;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Pipeline Control</h2>

      {isRunning && (
        <Card className="border-blue-500/50 bg-blue-500/10">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-blue-500 animate-pulse" />
              <span className="font-medium">Running: {running.step}</span>
              <Badge variant="secondary">PID {running.pid}</Badge>
              <span className="text-sm text-muted-foreground">{elapsed}s elapsed</span>
            </div>
            <div className="text-xs text-muted-foreground mt-1 font-mono">{running.command}</div>
          </CardContent>
        </Card>
      )}

      {running && !running.alive && (
        <Card className="border-green-500/50 bg-green-500/10">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full bg-green-500" />
              <span className="font-medium">Completed: {running.step}</span>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-3">
        {STEPS.map(step => (
          <Card key={step.name}>
            <CardContent className="flex items-center justify-between py-4">
              <div className="flex items-center gap-3">
                <span className="font-medium">{step.label}</span>
                <Badge variant={step.required ? "default" : "secondary"}>
                  {step.required ? "required" : "optional"}
                </Badge>
                {isRunning && running.step === step.name && (
                  <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                )}
              </div>
              <button
                onClick={() => handleRun(step.name)}
                disabled={isRunning || launching !== null}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm disabled:opacity-50 hover:bg-primary/90"
              >
                {launching === step.name ? "Starting..." :
                 isRunning && running.step === step.name ? "Running..." : "Run"}
              </button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>Run All</CardTitle></CardHeader>
        <CardContent>
          <button
            onClick={() => handleRun("all")}
            disabled={isRunning || launching !== null}
            className="px-6 py-3 bg-green-600 text-white rounded-md disabled:opacity-50 hover:bg-green-700"
          >
            {isRunning ? "Pipeline Running..." : "Run Full Pipeline"}
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
