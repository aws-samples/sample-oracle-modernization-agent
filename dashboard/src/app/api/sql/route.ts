import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: NextRequest) {
  try {
    const db = getDb();
    if (!db) {
      return NextResponse.json({ total: 0, limit: 100, offset: 0, data: [] });
    }
    const { searchParams } = new URL(request.url);

    const step = searchParams.get('step');
    const status = searchParams.get('status');
    const search = searchParams.get('search');
    const limit = parseInt(searchParams.get('limit') || '100');
    const offset = parseInt(searchParams.get('offset') || '0');

    let where = '1=1';
    const params: unknown[] = [];

    if (step) {
      where += ' AND current_step = ?';
      params.push(step);
    }
    if (status) {
      where += ' AND test_result = ?';
      params.push(status);
    }
    if (search) {
      where += ' AND (sql_id LIKE ? OR mapper_file LIKE ?)';
      params.push(`%${search}%`, `%${search}%`);
    }

    const countRow = db.prepare(
      `SELECT COUNT(*) as count FROM transform_target_list WHERE ${where}`
    ).get(...params) as { count: number };

    const rows = db.prepare(
      `SELECT id, mapper_file, sql_id, sql_type, current_step,
              transformed, reviewed, validated, tested,
              test_result, test_notes, updated_at
       FROM transform_target_list
       WHERE ${where}
       ORDER BY mapper_file, sql_id
       LIMIT ? OFFSET ?`
    ).all(...params, limit, offset);

    return NextResponse.json({
      total: countRow.count,
      limit,
      offset,
      data: rows,
    });
  } catch (error) {
    if (String(error).includes('no such table')) {
      return NextResponse.json({ total: 0, limit: 100, offset: 0, data: [] });
    }
    return NextResponse.json(
      { error: String(error) },
      { status: 500 }
    );
  }
}
