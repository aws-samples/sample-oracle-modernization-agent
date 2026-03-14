"""OMA Environment Setup - Interactive setup for oma_control.db"""
import getpass
import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import OUTPUT_DIR, DB_PATH

# Keys that contain sensitive values — masked in output, entered via getpass
_SENSITIVE_KEYS = {'ORACLE_SVC_PASSWORD', 'PGPASSWORD', 'MYSQL_PASSWORD'}


def init_db():
    """Create DB and all tables from models.py if not exists.

    Uses SQLAlchemy Base.metadata.create_all() to ensure the full schema
    is created upfront, including history tables, indexes, and all columns on
    transform_target_list. Existing tables are not modified (IF NOT EXISTS).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from sqlalchemy import create_engine
    from core.models import Base

    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    engine.dispose()


def get_property(key: str):
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM properties WHERE key = ?", (key,))
        row = cursor.fetchone()
    return row[0] if row else None


def set_property(key: str, value: str, description: str = ""):
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        conn.execute("""
            INSERT INTO properties (key, value, description) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        """, (key, value, description, value))
        conn.commit()


def ask(prompt: str, current: str = None) -> str:
    if current:
        user_input = input(f"  {prompt} [{current}]: ").strip()
        return user_input if user_input else current
    else:
        while True:
            user_input = input(f"  {prompt}: ").strip()
            if user_input:
                return user_input
            print("    ⚠️  값을 입력해주세요.")


def ask_password(prompt: str, current: str = None) -> str:
    """Prompt for password input without echoing to terminal."""
    if current:
        user_input = getpass.getpass(f"  {prompt} [****]: ").strip()
        return user_input if user_input else current
    else:
        while True:
            user_input = getpass.getpass(f"  {prompt}: ").strip()
            if user_input:
                return user_input
            print("    ⚠️  값을 입력해주세요.")


def _setup_pg_connection():
    """PostgreSQL Target DB 접속 정보 설정."""
    print("\n📋 PostgreSQL 접속 정보 (Target DB)\n")

    pg_host = ask("PGHOST", get_property('PGHOST'))
    pg_port = ask("PGPORT", get_property('PGPORT') or '5432')
    pg_database = ask("PGDATABASE", get_property('PGDATABASE'))
    pg_user = ask("PGUSER", get_property('PGUSER'))
    pg_password = ask_password("PGPASSWORD", get_property('PGPASSWORD'))

    set_property('PGHOST', pg_host, 'PostgreSQL host')
    set_property('PGPORT', pg_port, 'PostgreSQL port')
    set_property('PGDATABASE', pg_database, 'PostgreSQL database')
    set_property('PGUSER', pg_user, 'PostgreSQL user')
    set_property('PGPASSWORD', pg_password, 'PostgreSQL password')

    # Parameter Store 저장
    print("\n📡 AWS Parameter Store 저장 (PostgreSQL)...", flush=True)
    try:
        import boto3
        ssm = boto3.client('ssm', region_name='us-east-1')
        ssm_prefix = "/oma/target_postgres/"
        params = {
            'host': pg_host, 'port': pg_port, 'database': pg_database,
            'username': pg_user, 'password': pg_password
        }
        for key, value in params.items():
            param_type = 'SecureString' if key == 'password' else 'String'
            ssm.put_parameter(Name=f"{ssm_prefix}{key}", Value=value, Type=param_type, Overwrite=True)
        print(f"  ✅ Parameter Store 저장 완료 ({ssm_prefix}*)")
    except Exception as e:
        print(f"  ⚠️  Parameter Store 저장 실패: {e}")
        print("  → 환경변수로 직접 설정하거나 나중에 다시 시도하세요.")

    # 접속 테스트
    print("\n🔌 PostgreSQL 접속 테스트...", flush=True)
    try:
        import subprocess
        env = {**os.environ, 'PGHOST': pg_host, 'PGPORT': pg_port,
               'PGDATABASE': pg_database, 'PGUSER': pg_user, 'PGPASSWORD': pg_password}
        result = subprocess.run(
            ['psql', '-c', 'SELECT 1'],
            capture_output=True, text=True, timeout=10, env=env
        )
        if result.returncode == 0:
            print("  ✅ 접속 성공!")
        else:
            print(f"  ❌ 접속 실패: {result.stderr.strip()}")
    except FileNotFoundError:
        print("  ⚠️  psql 미설치 - 접속 테스트 스킵")
    except Exception as e:
        print(f"  ⚠️  접속 테스트 실패: {e}")


def _setup_mysql_connection():
    """MySQL Target DB 접속 정보 설정."""
    print("\n📋 MySQL 접속 정보 (Target DB)\n")

    mysql_host = ask("MYSQL_HOST", get_property('MYSQL_HOST'))
    mysql_port = ask("MYSQL_PORT", get_property('MYSQL_PORT') or '3306')
    mysql_database = ask("MYSQL_DATABASE", get_property('MYSQL_DATABASE'))
    mysql_user = ask("MYSQL_USER", get_property('MYSQL_USER'))
    mysql_password = ask_password("MYSQL_PASSWORD", get_property('MYSQL_PASSWORD'))

    set_property('MYSQL_HOST', mysql_host, 'MySQL host')
    set_property('MYSQL_PORT', mysql_port, 'MySQL port')
    set_property('MYSQL_DATABASE', mysql_database, 'MySQL database')
    set_property('MYSQL_USER', mysql_user, 'MySQL user')
    set_property('MYSQL_PASSWORD', mysql_password, 'MySQL password')

    # Parameter Store 저장
    print("\n📡 AWS Parameter Store 저장 (MySQL)...", flush=True)
    try:
        import boto3
        ssm = boto3.client('ssm', region_name='us-east-1')
        ssm_prefix = "/oma/target_mysql/"
        params = {
            'host': mysql_host, 'port': mysql_port, 'database': mysql_database,
            'username': mysql_user, 'password': mysql_password
        }
        for key, value in params.items():
            param_type = 'SecureString' if key == 'password' else 'String'
            ssm.put_parameter(Name=f"{ssm_prefix}{key}", Value=value, Type=param_type, Overwrite=True)
        print(f"  ✅ Parameter Store 저장 완료 ({ssm_prefix}*)")
    except Exception as e:
        print(f"  ⚠️  Parameter Store 저장 실패: {e}")
        print("  → 환경변수로 직접 설정하거나 나중에 다시 시도하세요.")

    # 접속 테스트
    print("\n🔌 MySQL 접속 테스트...", flush=True)
    try:
        import subprocess
        cmd = ['mysql', '-h', mysql_host, '-P', mysql_port, '-u', mysql_user, '-e', 'SELECT 1']
        env = {**os.environ}
        if mysql_password:
            env['MYSQL_PWD'] = mysql_password
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
        if result.returncode == 0:
            print("  ✅ 접속 성공!")
        else:
            print(f"  ❌ 접속 실패: {result.stderr.strip()}")
    except FileNotFoundError:
        print("  ⚠️  mysql 미설치 - 접속 테스트 스킵")
    except Exception as e:
        print(f"  ⚠️  접속 테스트 실패: {e}")


def run():
    print("🔧 OMA Environment Setup\n")

    # 1. OUTPUT_DIR 안내 + DB 생성
    print(f"  📁 작업 디렉토리: {OUTPUT_DIR}")
    print(f"     (변경: export OMA_OUTPUT_DIR=/path/to/dir)\n")

    is_new = not DB_PATH.exists()
    init_db()
    if is_new:
        print(f"  ✅ DB 생성: {DB_PATH}")
    else:
        print(f"  ✅ DB 확인: {DB_PATH}")
    print()

    # 2. 설정값 입력
    print("📋 프로젝트 설정\n")

    java_source = ask(
        "JAVA_SOURCE_FOLDER (Java 소스 경로)",
        get_property('JAVA_SOURCE_FOLDER')
    )
    # 경로 유효성 확인
    if not Path(java_source).exists():
        print(f"    ⚠️  경로가 존재하지 않습니다: {java_source}")
        confirm = input("    계속 진행할까요? (y/n): ").strip().lower()
        if confirm != 'y':
            print("    취소됨.")
            return

    source_dbms = ask(
        "SOURCE_DBMS_TYPE (oracle/mysql/mssql)",
        get_property('SOURCE_DBMS_TYPE') or 'oracle'
    )

    target_dbms = ask(
        "TARGET_DBMS_TYPE (postgresql/mysql)",
        get_property('TARGET_DBMS_TYPE') or 'postgresql'
    )

    # 3. 저장
    print()
    set_property('JAVA_SOURCE_FOLDER', java_source, 'Java source code root path')
    set_property('SOURCE_DBMS_TYPE', source_dbms, 'Source database type')
    set_property('TARGET_DBMS_TYPE', target_dbms, 'Target database type')

    # 모델 설정
    from utils.project_paths import DEFAULT_MODEL_ID, DEFAULT_LITE_MODEL_ID
    current_model = get_property('OMA_MODEL_ID') or DEFAULT_MODEL_ID
    print(f"\n  💡 추천 모델: {DEFAULT_MODEL_ID}")
    model_id = ask("OMA_MODEL_ID (Bedrock model ID)", current_model)
    set_property('OMA_MODEL_ID', model_id, 'Bedrock model ID for all agents')

    current_lite = get_property('OMA_LITE_MODEL_ID') or DEFAULT_LITE_MODEL_ID
    print(f"  💡 추천 경량 모델: {DEFAULT_LITE_MODEL_ID}")
    lite_model_id = ask("OMA_LITE_MODEL_ID (경량 판단용 — Facilitator 등)", current_lite)
    set_property('OMA_LITE_MODEL_ID', lite_model_id, 'Lite Bedrock model ID for facilitator/summary')

    # 4. DB 접속 정보 입력 여부 확인
    print("\n" + "="*70)
    print("ℹ️  데이터베이스 접속 정보 설정")
    print("="*70)
    print("  SQL 변환(Transform)과 검증(Validate)은 DB 없이도 수행 가능합니다.")
    print(f"  테스트(Test) 단계에서만 Target DB ({target_dbms.upper()}) 접속이 필요합니다.")
    print("="*70)

    setup_db = input("\n  DB 접속 정보를 지금 설정하시겠습니까? (y/n) [n]: ").strip().lower()

    if setup_db != 'y':
        print("\n  ⏭️  DB 접속 정보 설정을 건너뜁니다.")
        print("  → 나중에 run_setup.py를 다시 실행하여 설정할 수 있습니다.")
        print("\n✅ 기본 설정 완료")
        print(f"📁 DB: {DB_PATH}")
        print("🚀 이제 run_source_analyzer.py를 실행하세요.")
        return

    # 5. Oracle 접속 정보 (Source DB)
    print("\n📋 Oracle 접속 정보 (Source DB)\n")

    ora_host = ask("ORACLE_HOST", get_property('ORACLE_HOST'))
    ora_port = ask("ORACLE_PORT", get_property('ORACLE_PORT') or '1521')
    ora_service = ask("ORACLE_SERVICE_NAME", get_property('ORACLE_SERVICE_NAME'))
    ora_user = ask("ORACLE_SVC_USER", get_property('ORACLE_SVC_USER'))
    ora_password = ask_password("ORACLE_SVC_PASSWORD", get_property('ORACLE_SVC_PASSWORD'))

    set_property('ORACLE_HOST', ora_host, 'Oracle host')
    set_property('ORACLE_PORT', ora_port, 'Oracle port')
    set_property('ORACLE_SERVICE_NAME', ora_service, 'Oracle service name')
    set_property('ORACLE_SVC_USER', ora_user, 'Oracle user')
    set_property('ORACLE_SVC_PASSWORD', ora_password, 'Oracle password')

    print("\n📡 AWS Parameter Store 저장 (Oracle)...", flush=True)
    try:
        import boto3
        ssm = boto3.client('ssm', region_name='us-east-1')
        ssm_prefix = "/oma/source_oracle/"
        params = {
            'host': ora_host, 'port': ora_port, 'service_name': ora_service,
            'username': ora_user, 'password': ora_password
        }
        for key, value in params.items():
            param_type = 'SecureString' if key == 'password' else 'String'
            ssm.put_parameter(
                Name=f"{ssm_prefix}{key}", Value=value,
                Type=param_type, Overwrite=True
            )
        print(f"  ✅ Parameter Store 저장 완료 ({ssm_prefix}*)")
    except Exception as e:
        print(f"  ⚠️  Parameter Store 저장 실패: {e}")

    # 6. Target DB 접속 정보 (TARGET_DBMS_TYPE에 따라 분기)
    if target_dbms == 'mysql':
        _setup_mysql_connection()
    else:
        _setup_pg_connection()

    # 9. 확인 (비밀번호 마스킹)
    print("✅ 설정 완료:\n")
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM properties ORDER BY key")
        for key, value in cursor.fetchall():
            if key in _SENSITIVE_KEYS:
                print(f"  {key} = ****")
            else:
                print(f"  {key} = {value}")

    print(f"\n📁 DB: {DB_PATH}")
    print("🚀 이제 run_source_analyzer.py를 실행하세요.")


def run_defaults(java_source_folder: str):
    """Non-interactive setup with default values (for example/CI)."""
    print("🔧 OMA Environment Setup (non-interactive)\n")

    print(f"  📁 작업 디렉토리: {OUTPUT_DIR}")
    init_db()
    print(f"  ✅ DB: {DB_PATH}")

    if not Path(java_source_folder).exists():
        print(f"  ❌ 경로 없음: {java_source_folder}")
        sys.exit(1)

    set_property('JAVA_SOURCE_FOLDER', java_source_folder, 'Java source code root path')
    set_property('SOURCE_DBMS_TYPE', 'oracle', 'Source database type')
    set_property('TARGET_DBMS_TYPE', 'postgresql', 'Target database type')

    from utils.project_paths import DEFAULT_MODEL_ID, DEFAULT_LITE_MODEL_ID
    set_property('OMA_MODEL_ID', DEFAULT_MODEL_ID, 'Bedrock model ID for all agents')
    set_property('OMA_LITE_MODEL_ID', DEFAULT_LITE_MODEL_ID, 'Lite Bedrock model ID')

    print(f"  ✅ Source: {java_source_folder}")
    print(f"  ✅ Model: {DEFAULT_MODEL_ID}")
    print(f"  ⏭️  DB 접속 정보: 건너뜀 (Test 단계 제외 모두 수행 가능)")
    print("\n✅ 설정 완료")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--defaults', metavar='JAVA_SOURCE_FOLDER',
                        help='Non-interactive setup with defaults')
    args = parser.parse_args()

    if args.defaults:
        run_defaults(args.defaults)
    else:
        run()
