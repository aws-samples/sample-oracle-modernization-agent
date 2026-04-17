import fs from 'fs';
import path from 'path';
import readline from 'readline';

const LOGS_DIR = process.env.OMA_LOGS_DIR
  || path.resolve(process.cwd(), '..', 'output', 'logs');

export interface LogEvent {
  ts: string;
  step: string;
  event: string;
  mapper?: string;
  sql_id?: string;
  status?: string;
  duration_ms?: number;
  fail_category?: string;
  sql_state?: string;
  error_code?: number;
  error?: string;
  parameters?: Record<string, string>;
  parameter_source?: string;
  fix_version?: string;
  notes?: string;
  phase?: number;
  [key: string]: unknown;
}

export function getLogsDir(): string {
  return LOGS_DIR;
}

export function listRuns(step: string): string[] {
  const stepDir = path.join(LOGS_DIR, step);
  if (!fs.existsSync(stepDir)) return [];
  return fs.readdirSync(stepDir)
    .filter(d => fs.statSync(path.join(stepDir, d)).isDirectory())
    .sort()
    .reverse();
}

export function parseEventsFile(filePath: string): LogEvent[] {
  if (!fs.existsSync(filePath)) return [];
  const content = fs.readFileSync(filePath, 'utf-8');
  return content
    .split('\n')
    .filter(line => line.trim())
    .map(line => {
      try { return JSON.parse(line) as LogEvent; }
      catch { return null; }
    })
    .filter((e): e is LogEvent => e !== null);
}

export function getLatestRunEvents(step: string): LogEvent[] {
  const runs = listRuns(step);
  if (runs.length === 0) return [];
  const eventsPath = path.join(LOGS_DIR, step, runs[0], 'events.jsonl');
  return parseEventsFile(eventsPath);
}

export function getSqlJourney(mapper: string, sqlId: string): LogEvent[] {
  const events: LogEvent[] = [];
  const stepsDir = LOGS_DIR;
  if (!fs.existsSync(stepsDir)) return events;

  for (const step of fs.readdirSync(stepsDir)) {
    const stepPath = path.join(stepsDir, step);
    if (!fs.statSync(stepPath).isDirectory()) continue;

    const runs = listRuns(step);
    for (const run of runs) {
      const eventsPath = path.join(stepPath, run, 'events.jsonl');
      const runEvents = parseEventsFile(eventsPath);
      for (const e of runEvents) {
        if (e.mapper === mapper && e.sql_id === sqlId) {
          events.push(e);
        }
      }
    }
  }

  return events.sort((a, b) => a.ts.localeCompare(b.ts));
}

export function listFixHistory(mapperStem: string, sqlId: string): string[] {
  const fixDir = path.join(LOGS_DIR, 'fix_history');
  if (!fs.existsSync(fixDir)) return [];
  const prefix = `${mapperStem}_${sqlId}_v`;
  return fs.readdirSync(fixDir)
    .filter(f => f.startsWith(prefix))
    .sort();
}

export function readFixHistory(filename: string): string {
  const filePath = path.join(LOGS_DIR, 'fix_history', filename);
  if (!fs.existsSync(filePath)) return '';
  return fs.readFileSync(filePath, 'utf-8');
}
