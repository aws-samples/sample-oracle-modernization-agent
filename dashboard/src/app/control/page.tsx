"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const STEPS = [
  { name: "analyze", label: "Source Analysis", required: true },
  { name: "transform", label: "SQL Transform", required: true },
  { name: "review", label: "Multi-Perspective Review", required: false },
  { name: "validate", label: "Equivalence Validation", required: false },
  { name: "merge", label: "Mapper Merge", required: true },
  { name: "test", label: "DB Execution Test", required: true },
];

export default function ControlPage() {
  const [running, setRunning] = useState<string | null>(null);

  const handleRun = async (step: string) => {
    setRunning(step);
    try {
      const res = await fetch(`/api/pipeline/run/${step}`, { method: "POST" });
      const data = await res.json();
      alert(`Started: ${step} (pid: ${data.pid || "N/A"})`);
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Pipeline Control</h2>

      <div className="grid grid-cols-1 gap-3">
        {STEPS.map(step => (
          <Card key={step.name}>
            <CardContent className="flex items-center justify-between py-4">
              <div className="flex items-center gap-3">
                <span className="font-medium">{step.label}</span>
                <Badge variant={step.required ? "default" : "secondary"}>
                  {step.required ? "required" : "optional"}
                </Badge>
              </div>
              <button
                onClick={() => handleRun(step.name)}
                disabled={running !== null}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm disabled:opacity-50 hover:bg-primary/90"
              >
                {running === step.name ? "Running..." : "Run"}
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
            disabled={running !== null}
            className="px-6 py-3 bg-green-600 text-white rounded-md disabled:opacity-50 hover:bg-green-700"
          >
            {running === "all" ? "Running Full Pipeline..." : "Run Full Pipeline"}
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
