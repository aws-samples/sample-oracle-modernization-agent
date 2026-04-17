import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const db = getDb();
    if (!db) {
      return NextResponse.json({
        steps: [],
        totals: { total: 0, passed: 0, failed: 0, skipped: 0, passRate: 0 },
        message: 'No database found. Run the pipeline first to generate data.',
      });
    }

    const stepCounts = db.prepare(`
      SELECT current_step, COUNT(*) as count
      FROM transform_target_list
      GROUP BY current_step
    `).all() as { current_step: string; count: number }[];

    const totals = db.prepare(`
      SELECT
        COUNT(*) as total,
        SUM(CASE WHEN test_result='PASS' OR test_result='FIXED' THEN 1 ELSE 0 END) as passed,
        SUM(CASE WHEN test_result='FAIL' THEN 1 ELSE 0 END) as failed,
        SUM(CASE WHEN test_result='SKIP' THEN 1 ELSE 0 END) as skipped,
        SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as transformed,
        SUM(CASE WHEN reviewed='Y' THEN 1 ELSE 0 END) as reviewed,
        SUM(CASE WHEN validated='Y' THEN 1 ELSE 0 END) as validated,
        SUM(CASE WHEN tested='Y' THEN 1 ELSE 0 END) as tested
      FROM transform_target_list
    `).get() as Record<string, number>;

    const passRate = totals.total > 0
      ? Math.round((totals.passed / totals.total) * 100)
      : 0;

    return NextResponse.json({
      steps: stepCounts,
      totals: { ...totals, passRate },
    });
  } catch (error) {
    if (String(error).includes('no such table')) {
      return NextResponse.json({
        steps: [],
        totals: { total: 0, passed: 0, failed: 0, skipped: 0, passRate: 0 },
        message: 'Pipeline not started yet. Run analyze first.',
      });
    }
    return NextResponse.json(
      { error: String(error) },
      { status: 500 }
    );
  }
}
