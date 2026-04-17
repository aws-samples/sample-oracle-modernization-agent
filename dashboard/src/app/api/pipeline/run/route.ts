import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

const SRC_DIR = path.resolve(process.cwd(), '..', 'src');

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

  const cmd = STEP_COMMANDS[step];
  if (!cmd) {
    return NextResponse.json({ error: `Unknown step: ${step}` }, { status: 400 });
  }

  try {
    const proc = spawn('python3', cmd, {
      cwd: SRC_DIR,
      env: { ...process.env, PYTHONPATH: SRC_DIR },
      detached: true,
      stdio: 'ignore',
    });
    proc.unref();

    return NextResponse.json({
      status: 'started',
      step,
      pid: proc.pid,
      command: `python3 ${cmd.join(' ')}`,
    });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
