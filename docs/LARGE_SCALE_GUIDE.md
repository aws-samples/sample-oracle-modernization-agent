# Large-Scale Processing Guide

**대규모 프로젝트 운영 가이드**

OMA로 수백~수천 개 SQL을 처리할 때의 권장 설정과 실행 전략.

---

## 목차

1. [규모별 권장 설정](#규모별-권장-설정)
2. [단계별 실행 전략](#단계별-실행-전략)
3. [Prompt Caching과 비용 최적화](#prompt-caching과-비용-최적화)
4. [중단과 재개](#중단과-재개)
5. [모니터링](#모니터링)
6. [문제 해결](#문제-해결)

---

## 규모별 권장 설정

### Worker 수 결정 기준

Worker 수는 **AWS Bedrock 동시 호출 한도**에 맞춰야 한다. Account/모델별 기본 한도는 보통 2~10이며, Service Quotas에서 확인 가능.

| 규모 | SQL 수 | `--workers` | 이유 |
|------|--------|-------------|------|
| 소규모 | ~50 | 4 | Bedrock 기본 한도 내 안전 운영 |
| 중규모 | 50~300 | 8 (기본값) | 대부분의 Account 한도에서 동작 |
| 대규모 | 300~1000+ | 4~6 | Throttling 방지를 위해 오히려 줄임 |

**대규모에서 worker를 줄이는 이유**: Review 단계에서 각 worker가 내부적으로 Syntax + Equivalence 2개의 병렬 API 호출을 추가로 생성한다. `--workers 8`이면 최대 16개 동시 API 호출이 발생하여 `ThrottlingException`이 날 수 있다.

```bash
# 권장: 대규모 프로젝트
python3 src/run_sql_transform.py --workers 6
python3 src/run_sql_review.py --workers 4    # Review는 내부 병렬 때문에 더 줄임
python3 src/run_sql_validate.py --workers 6
python3 src/run_sql_test.py --workers 6
```

### Bedrock 한도 확인 방법

```bash
aws service-quotas get-service-quota \
  --service-code bedrock \
  --quota-code L-XXXXXXXX \
  --region us-east-1
```

또는 AWS Console > Service Quotas > Amazon Bedrock > `Invoke model calls per minute` 확인.

---

## 단계별 실행 전략

### Orchestrator vs 개별 실행

| 방식 | 사용 시점 | 명령어 |
|------|----------|--------|
| **Orchestrator** | 소~중규모, 처음 실행 | `python3 src/run_orchestrator.py` |
| **개별 단계** | 대규모, 세밀한 제어 필요 | 아래 참조 |

대규모(300+ SQL)에서는 **단계별 개별 실행**을 권장한다:

```bash
# 1. Setup (1회)
python3 src/run_setup.py

# 2. Transform — 가장 오래 걸림, worker 조절 중요
python3 src/run_sql_transform.py --workers 6

# 3. Review — 내부 병렬(Syntax+Equiv) 고려하여 worker 절반
python3 src/run_sql_review.py --workers 4 --max-rounds 3

# 4. Validate
python3 src/run_sql_validate.py --workers 6

# 5. Test — PostgreSQL 접속 필요
python3 src/run_sql_test.py --workers 6

# 6. Merge — 순차, 빠름
python3 src/run_sql_merge.py
```

### 단계별 예상 소요 (300 SQL 기준, workers=6)

| 단계 | 예상 시간 | 병목 |
|------|----------|------|
| Transform | 15~30분 | API 호출 (SQL당 ~5초) |
| Review | 10~20분 | 2x API 호출 (Syntax + Equiv 병렬) |
| Validate | 10~15분 | API 호출 |
| Test Phase 1 | 5~10분 | Java 순차 실행 |
| Test Phase 2 | 실패 수 비례 | Agent 수정 |
| Merge | ~1분 | 순차 파일 I/O |

> 실제 시간은 SQL 복잡도, Bedrock 응답 시간, 네트워크에 따라 크게 달라진다.

---

## Prompt Caching과 비용 최적화

### 캐시 유효 시간: 5분

Bedrock Prompt Caching은 **마지막 호출로부터 5분** 동안 유효하다. 이것이 대규모 처리의 핵심 비용 요소:

- Worker가 연속으로 API를 호출하면 캐시 히트 → **90%+ 비용 절감**
- 5분 이상 간격이 벌어지면 캐시 미스 → **비용 5~10배 증가**

### 캐시 효율을 높이는 방법

1. **단계 사이에 긴 대기 금지**: Transform 끝나면 바로 Review 시작
2. **Worker 수가 너무 적으면 비효율**: Worker 1개이면 API 호출 간격이 길어져 캐시 미스 증가
3. **Worker 수가 너무 많아도 비효율**: Throttling으로 재시도 대기 → 캐시 만료 가능
4. **최적 균형**: Throttling 없이 연속 호출이 유지되는 worker 수 (보통 4~8)

### 비용 시뮬레이션

```
300 SQL × 4단계(Transform/Review/Validate/Test) = ~1,200 API 호출

캐시 히트 시: ~$3~5
캐시 미스 시: ~$30~50

→ 단계 간 빈틈 없이 실행하는 것이 10배 차이를 만든다
```

---

## 중단과 재개

### 자동 재개 메커니즘

모든 단계는 SQLite DB 플래그 기반으로 동작하므로, **중단 후 같은 명령어를 다시 실행하면 미완료분만 이어서 처리**한다.

```
transformed='N' → Transform 대상
reviewed='N'    → Review 대상
validated='N'   → Validate 대상
tested='N'      → Test 대상
```

```bash
# 중단 후 재실행 — 이미 완료된 건 스킵
python3 src/run_sql_transform.py --workers 6
# "✅ 200/300 already done, processing remaining 100..."
```

### 특정 단계 초기화

```bash
# Transform 전체 재실행
python3 src/run_sql_transform.py --reset --workers 6

# Review만 초기화
python3 src/run_sql_review.py --reset

# Test만 초기화
python3 src/run_sql_test.py --reset
```

### 주의: 파이프라인 순서 의존성

Review를 리셋하면 Validate/Test도 다시 해야 한다. Transform을 리셋하면 이후 전체 재실행.

```
Transform → Review → Validate → Test → Merge
리셋하면 ──────────→ 이후 단계 모두 재실행 필요
```

---

## 모니터링

### 실시간 진행률

각 단계는 progress log 파일에 실시간 기록하며, stderr로 tail 출력:

```
[  5%] [UserMapper] selectUserList - 🔄 변환중
[ 12%] [UserMapper] selectUserList - ✅ 완료
[ 15%] [OrderMapper] selectOrder - 🔄 변환중
```

### 별도 터미널에서 모니터링

```bash
# Transform 진행 상황
tail -f output/logs/transform_progress.log

# Review 진행 상황
tail -f output/logs/review_progress.log

# Mapper별 상세 로그
tail -f output/logs/transform/UserMapper.log
```

### DB 직접 조회

```bash
sqlite3 output/oma_control.db    # 또는 $OMA_OUTPUT_DIR/oma_control.db

-- 전체 현황
SELECT
  COUNT(*) as total,
  SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as transformed,
  SUM(CASE WHEN reviewed='Y' THEN 1 ELSE 0 END) as reviewed,
  SUM(CASE WHEN validated='Y' THEN 1 ELSE 0 END) as validated,
  SUM(CASE WHEN tested='Y' THEN 1 ELSE 0 END) as tested
FROM transform_target_list;

-- Mapper별 진행률
SELECT mapper_file,
  COUNT(*) as total,
  SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as done
FROM transform_target_list
GROUP BY mapper_file;

-- 실패 목록
SELECT mapper_file, sql_id, review_result
FROM transform_target_list
WHERE reviewed='F';
```

---

## 문제 해결

### 1. ThrottlingException (Bedrock 동시성 초과)

**증상**: 로그에 `ThrottlingException` 또는 `Too many requests` 에러.

**대응**:
```bash
# Worker 수 줄이기
python3 src/run_sql_transform.py --workers 4

# Review는 더 줄이기 (내부 2x 병렬)
python3 src/run_sql_review.py --workers 3
```

재실행하면 실패한 SQL만 자동으로 이어서 처리.

### 2. SQLite Database Locked

**증상**: `sqlite3.OperationalError: database is locked`

**원인**: 8개 worker가 동시에 SQLite에 쓰기 시도. 기본 retry (5회, 최대 2.5초 대기)로 대부분 해결되지만, 극단적 동시성에서 발생 가능.

**대응**:
- Worker 수 줄이기 (`--workers 4`)
- 다른 프로세스가 DB를 점유하고 있지 않은지 확인
- `lsof output/oma_control.db`로 점유 프로세스 확인

### 3. 특정 Mapper에서 반복 실패

**증상**: 같은 Mapper가 계속 에러.

**확인**:
```bash
# Mapper별 상세 로그
cat output/logs/transform/ProblemMapper.log

# DB에서 실패 SQL 확인
sqlite3 output/oma_control.db \
  "SELECT sql_id, review_result FROM transform_target_list WHERE mapper_file='ProblemMapper.xml' AND reviewed='F'"
```

**대응**: Orchestrator로 개별 SQL 재처리:
```
🧑 > ProblemMapper.xml의 selectComplexQuery 재변환해줘
```

### 4. Prompt Caching 미작동 (비용 급증)

**확인**: AWS CloudWatch에서 Bedrock 호출별 `CacheReadInputTokens` 메트릭 확인. 0이면 캐시 미스.

**원인**:
- 모델이 Prompt Caching 미지원 (Sonnet 4.6, Opus 4.6 등)
- System prompt가 변경됨 (strategy 파일 업데이트 후 캐시 무효화)
- API 호출 간격이 5분 초과

**대응**:
- `OMA_MODEL_ID` 확인 — 반드시 캐싱 지원 모델 사용
- Worker가 최소 2개 이상으로 연속 호출 유지

### 5. Test Phase 1 타임아웃

**증상**: Java bulk test가 600초 제한에 걸림.

**원인**: 대규모 SQL을 순차 실행하는 Phase 1의 한계.

**대응**:
- PostgreSQL 연결 상태 확인 (느린 쿼리 없는지)
- Phase 1이 타임아웃되더라도 Phase 2에서 실패 건을 Agent가 개별 수정

---

## 대규모 프로젝트 체크리스트

```
실행 전:
  □ AWS Bedrock 동시성 한도 확인 (Service Quotas)
  □ OMA_MODEL_ID가 Prompt Caching 지원 모델인지 확인
  □ PostgreSQL 타겟 DB 접속 가능 확인 (Test 단계용)
  □ 디스크 여유 공간 확인 (output/ 디렉토리)
  □ input/ 경로에 Mapper XML 배치 확인

실행 중:
  □ 단계별 개별 실행 (--workers 조절)
  □ Review는 worker를 Transform의 절반으로
  □ progress log 또는 DB 쿼리로 진행률 확인
  □ 단계 간 빈틈 없이 연속 실행 (캐시 유효 5분)

실행 후:
  □ DB에서 최종 현황 확인 (전체 Y 여부)
  □ output/merge/ 에 최종 XML 확인
  □ reviewed='F' 인 SQL은 수동 검토
  □ output/logs/fix_history/ 에서 수정 이력 확인
```
