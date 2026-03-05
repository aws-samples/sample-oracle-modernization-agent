# AMZN 백오피스 애플리케이션 관리 스크립트

이 디렉토리에는 AMZN 백오피스 Spring Boot 애플리케이션을 관리하기 위한 스크립트들이 포함되어 있습니다.

## 📁 파일 구조

```
bin/
├── README.md                    # 이 파일
├── amzn-bo.sh                  # 메인 관리 스크립트
├── amzn-bo-maven.sh            # Maven 기반 관리 스크립트
├── catalina.sh                 # 톰캣 스타일 관리 스크립트
├── amzn-backoffice.pid         # 프로세스 ID 파일 (자동 생성)
├── amzn-backoffice.log         # 애플리케이션 로그 파일
└── catalina.out                # 톰캣 스타일 로그 파일
```

## 🚀 기본 사용법

### 1. 메인 관리 스크립트 (amzn-bo.sh)

가장 많이 사용하는 기본 스크립트입니다.

#### 애플리케이션 관리
```bash
# 애플리케이션 시작 (백그라운드)
./bin/amzn-bo.sh start

# 애플리케이션 중지
./bin/amzn-bo.sh stop

# 애플리케이션 재시작
./bin/amzn-bo.sh restart

# 상태 확인
./bin/amzn-bo.sh status
```

#### 로그 관리
```bash
# 기본 로그 보기 (최근 50줄)
./bin/amzn-bo.sh logs

# 실시간 로그 모니터링
./bin/amzn-bo.sh logs -f

# 특정 줄 수만 보기
./bin/amzn-bo.sh logs -n 100

# 에러 로그만 보기
./bin/amzn-bo.sh logs --error

# 경고 로그만 보기
./bin/amzn-bo.sh logs --warn

# 로그 파일 크기 확인
./bin/amzn-bo.sh logs --size

# 로그 파일 비우기
./bin/amzn-bo.sh logs --clear
```

### 2. 톰캣 스타일 관리 (catalina.sh)

톰캣에 익숙한 사용자를 위한 스크립트입니다.

```bash
# 백그라운드 시작 (catalina.out으로 로그 출력)
./bin/catalina.sh start

# 포그라운드 실행 (개발/디버깅용)
./bin/catalina.sh run

# 중지
./bin/catalina.sh stop

# catalina.out 로그 보기
./bin/catalina.sh logs

# 실시간 로그 모니터링 (tail -f catalina.out 스타일)
./bin/catalina.sh logs -f

# 특정 줄 수만 보기
./bin/catalina.sh logs -n 50

# 버전 정보 확인
./bin/catalina.sh version
```

### 3. Maven 기반 관리 (amzn-bo-maven.sh)

Maven의 spring-boot:run을 사용하는 스크립트입니다.

```bash
# Maven으로 백그라운드 시작
./bin/amzn-bo-maven.sh start

# 중지
./bin/amzn-bo-maven.sh stop

# 상태 확인
./bin/amzn-bo-maven.sh status

# 로그 보기
./bin/amzn-bo-maven.sh logs -f
```

## 📊 애플리케이션 정보

### 접속 정보
- **애플리케이션 URL**: http://localhost:8080/amzn-bo
- **포트**: 8080
- **컨텍스트 패스**: /amzn-bo

### 주요 API 엔드포인트
- **사용자 관리**: `GET /api/users`
- **상품 관리**: `GET /api/products`
- **주문 관리**: `GET /api/orders`
- **카테고리 계층**: `GET /api/products/categories/hierarchy`
- **사용자 통계**: `GET /api/users/grade-statistics`

## 🔧 로그 파일 위치

### amzn-bo.sh 사용 시
- **로그 파일**: `bin/amzn-backoffice.log`
- **PID 파일**: `bin/amzn-backoffice.pid`

### catalina.sh 사용 시
- **로그 파일**: `bin/catalina.out` (톰캣 스타일)
- **PID 파일**: `bin/amzn-backoffice.pid`

### amzn-bo-maven.sh 사용 시
- **로그 파일**: `bin/amzn-backoffice-maven.log`
- **PID 파일**: `bin/amzn-backoffice-maven.pid`

## 🧪 API 테스트 예시

### 기본 테스트
```bash
# 애플리케이션 상태 확인
curl -s http://localhost:8080/amzn-bo/actuator/health

# 사용자 목록 조회 (페이징)
curl -s "http://localhost:8080/amzn-bo/api/users?page=1&size=5" | python3 -m json.tool

# 상품 목록 조회
curl -s "http://localhost:8080/amzn-bo/api/products?page=1&size=3" | python3 -m json.tool

# 주문 목록 조회
curl -s "http://localhost:8080/amzn-bo/api/orders?page=1&size=3" | python3 -m json.tool
```

### 고급 검색 테스트
```bash
# 사용자 검색 (이름으로)
curl -s "http://localhost:8080/amzn-bo/api/users?searchKeyword=John&page=1&size=5"

# 상품 검색 (브랜드로)
curl -s "http://localhost:8080/amzn-bo/api/products?brandFilter=HP&page=1&size=5"

# 주문 상태별 통계
curl -s "http://localhost:8080/amzn-bo/api/orders/statistics/status"
```

## 🚨 문제 해결

### 포트 충돌 문제
```bash
# 포트 8080 사용 중인 프로세스 확인
netstat -tlnp | grep :8080

# 또는
lsof -i :8080

# 프로세스 강제 종료 (PID 확인 후)
kill -9 <PID>
```

### 애플리케이션이 시작되지 않을 때
```bash
# 로그 확인
./bin/amzn-bo.sh logs --error

# 또는 전체 로그 확인
./bin/amzn-bo.sh logs -n 100

# 데이터베이스 연결 확인 (로그에서)
./bin/amzn-bo.sh logs | grep -i "database\|connection"
```

### 메모리 사용량 확인
```bash
# 애플리케이션 상태에서 메모리 정보 확인
./bin/amzn-bo.sh status

# 또는 직접 프로세스 확인
ps aux | grep java | grep amzn-backoffice
```

## 📝 일반적인 작업 흐름

### 개발 시작 시
```bash
# 1. 애플리케이션 시작
./bin/amzn-bo.sh start

# 2. 상태 확인
./bin/amzn-bo.sh status

# 3. 로그 모니터링 (별도 터미널에서)
./bin/amzn-bo.sh logs -f

# 4. API 테스트
curl -s http://localhost:8080/amzn-bo/actuator/health
```

### 개발 종료 시
```bash
# 애플리케이션 중지
./bin/amzn-bo.sh stop
```

### 코드 변경 후 재배포
```bash
# 재시작 (자동으로 빌드 후 시작)
./bin/amzn-bo.sh restart
```

## 🔍 고급 기능

### 로그 분석
```bash
# 특정 시간대 로그 확인
./bin/amzn-bo.sh logs | grep "2025-08-20 07:"

# SQL 쿼리 로그 확인
./bin/amzn-bo.sh logs | grep -i "select\|insert\|update\|delete"

# 성능 관련 로그 확인
./bin/amzn-bo.sh logs | grep -i "slow\|timeout\|performance"
```

### 시스템 모니터링
```bash
# 실시간 시스템 리소스 모니터링
watch -n 2 './bin/amzn-bo.sh status'

# 로그 파일 크기 모니터링
watch -n 5 './bin/amzn-bo.sh logs --size'
```

## 📞 지원

문제가 발생하거나 추가 기능이 필요한 경우:

1. **로그 확인**: `./bin/amzn-bo.sh logs --error`
2. **상태 확인**: `./bin/amzn-bo.sh status`
3. **애플리케이션 재시작**: `./bin/amzn-bo.sh restart`

---

**참고**: 모든 스크립트는 프로젝트 루트 디렉토리(`/home/ec2-user/workspace/src-orcl`)에서 실행해야 합니다.
