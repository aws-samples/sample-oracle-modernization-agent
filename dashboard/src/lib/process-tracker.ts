import { execSync } from 'child_process';

interface RunningProcess {
  pid: number;
  step: string;
  startedAt: string;
  command: string;
}

let _running: RunningProcess | null = null;

export function setRunning(proc: RunningProcess | null) {
  _running = proc;
}

export function getRunning(): (RunningProcess & { alive: boolean }) | null {
  if (!_running) return null;
  const alive = isAlive(_running.pid);
  if (!alive) {
    const result = { ..._running, alive: false };
    _running = null;
    return result;
  }
  return { ..._running, alive: true };
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
