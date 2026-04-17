import Database from 'better-sqlite3';
import path from 'path';

const DB_PATH = process.env.OMA_DB_PATH
  || path.resolve(process.cwd(), '..', 'output', 'oma_control.db');

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!_db) {
    _db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
    _db.pragma('journal_mode = WAL');
  }
  return _db;
}

export interface SqlRow {
  id: number;
  mapper_file: string;
  sql_id: string;
  sql_type: string;
  current_step: string;
  transformed: string;
  reviewed: string;
  validated: string;
  tested: string;
  test_result: string | null;
  test_notes: string | null;
  review_result: string | null;
  validation_result: string | null;
  transform_count: number | null;
  updated_at: string;
}
