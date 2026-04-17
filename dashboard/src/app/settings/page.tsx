"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Settings</h2>

      <Card>
        <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Config editor for oma-config.yaml will be implemented here.
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            Manages: project settings, database connection, pipeline options.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
