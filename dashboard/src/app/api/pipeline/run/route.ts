import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';
import { setRunning, getRunning } from '@/lib/process-tracker';

const PROJECT_DIR = path.resolve(process.cwd(), '..');
const SRC_DIR = path.join(PROJECT_DIR, 'src');
const VENV_PYTHON = path.join(PROJECT_DIR, '.venv', 'bin', 'python3');

const STEP_COMMANDS: Record<string, string[]> = {
  analyze: ['run_source_analyzer.py'],
  transform: ['run_sql_transform.py', '--workers', '8'],
  review: ['run_sql_review.py', '--workers', '4', '--max-rounds', '3'],
  validate: ['run_sql_validate.py', '--workers', '6'],
  merge: ['run_sql_merge.py'],
  test: ['run_sql_test.py', '--workers', '6'],
  all: ['run_pipeline.py'],
};

export async function POST(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const step = searchParams.get('step') || 'all';

  const current = getRunning();
  if (current?.alive) {
    return NextResponse.json({
      error: `Step "${current.step}" is already running (pid: ${current.pid})`,
      running: current,
    }, { status: 409 });
  }

  const cmd = STEP_COMMANDS[step];
  if (!cmd) {
    return NextResponse.json({ error: `Unknown step: ${step}` }, { status: 400 });
  }

  try {
    const proc = spawn(VENV_PYTHON, cmd, {
      cwd: SRC_DIR,
      env: { ...process.env, PYTHONPATH: SRC_DIR, VIRTUAL_ENV: path.join(PROJECT_DIR, '.venv') },
      detached: true,
      stdio: 'ignore',
    });
    proc.unref();

    const info = {
      pid: proc.pid!,
      step,
      startedAt: new Date().toISOString(),
      command: `python3 ${cmd.join(' ')}`,
    };
    setRunning(info);

    return NextResponse.json({ status: 'started', ...info });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}

export async function GET() {
  const current = getRunning();
  return NextResponse.json({ running: current });
}
