# AMZN 백오피스 애플리케이션

AMZN 쇼핑몰의 백오피스 관리 시스템입니다. Spring Boot와 MyBatis를 사용하여 구축되었습니다.

## 프로젝트 구조

```
src/
├── main/
│   ├── java/amzn/bo/
│   │   ├── config/          # 설정 클래스들
│   │   ├── controller/      # REST API 컨트롤러들
│   │   ├── dto/            # 데이터 전송 객체들
│   │   ├── mapper/         # MyBatis 매퍼 인터페이스들
│   │   └── service/        # 비즈니스 로직 서비스들
│   └── resources/
│       ├── sqlmap/mapper/  # MyBatis XML 매퍼 파일들
│       └── application.yml # 애플리케이션 설정
├── ddl/                    # 데이터베이스 DDL 스크립트들
└── work/                   # 작업용 스크립트들
```

## 주요 기능

### 사용자 관리 (User Management)
- 사용자 목록 조회 (복합 검색, 고급 필터링)
- 사용자 상세 정보 및 활동 통계
- 사용자 등급별 통계 및 가입 추이 분석
- 사용자 상태 관리 및 정보 업데이트

### 상품 관리 (Product Management)
- 상품 목록 조회 및 검색
- 계층형 카테고리 관리
- 상품 성과 분석 (판매량, 수익, 평점 등)
- 재고 관리 및 브랜드/카테고리별 통계
- 상품 등록, 수정, 삭제

### 주문 관리 (Order Management)
- 주문 목록 조회 및 고급 분석
- 주문 상태별 통계 및 트렌드 분석
- 결제 방법별 통계 및 처리 시간 분석
- 고객별 주문 패턴 분석
- 주문 상태 관리, 배송 정보 업데이트
- 주문 취소 및 환불 처리

## 기술 스택

- **Framework**: Spring Boot 3.2.0
- **Database**: Oracle Database
- **ORM**: MyBatis 3.0.3
- **Build Tool**: Maven
- **Java Version**: 17
- **Connection Pool**: HikariCP

## API 엔드포인트

### 사용자 관리
- `GET /api/users` - 사용자 목록 조회
- `GET /api/users/{userId}` - 사용자 상세 정보
- `GET /api/users/{userId}/activity-stats` - 사용자 활동 통계
- `GET /api/users/grade-statistics` - 사용자 등급별 통계
- `PUT /api/users/{userId}/status` - 사용자 상태 업데이트

### 상품 관리
- `GET /api/products` - 상품 목록 조회
- `GET /api/products/{productId}` - 상품 상세 정보
- `GET /api/products/categories/hierarchy` - 카테고리 계층 조회
- `GET /api/products/performance-analysis` - 상품 성과 분석
- `POST /api/products` - 상품 등록
- `PUT /api/products/{productId}` - 상품 정보 업데이트

### 주문 관리
- `GET /api/orders` - 주문 목록 조회 (분석 포함)
- `GET /api/orders/{orderId}` - 주문 상세 정보
- `GET /api/orders/statistics/status` - 주문 상태별 통계
- `GET /api/orders/analytics/trend` - 주문 트렌드 분석
- `PUT /api/orders/{orderId}/status` - 주문 상태 업데이트
- `PUT /api/orders/{orderId}/cancel` - 주문 취소

## 설정

### 데이터베이스 연결
`src/main/resources/application.yml` 파일에서 데이터베이스 연결 정보를 설정하세요:

```yaml
spring:
  datasource:
    driver-class-name: oracle.jdbc.OracleDriver
    url: jdbc:oracle:thin:@localhost:1521:XE
    username: <your-username>
    password: <your-password>
```

## 실행 방법

1. 프로젝트 클론 및 의존성 설치:
```bash
mvn clean install
```

2. 애플리케이션 실행:
```bash
mvn spring-boot:run
```

3. 브라우저에서 접속:
```
http://localhost:8080/amzn-bo
```

## 개발 환경

- IDE: IntelliJ IDEA 또는 Eclipse
- JDK: OpenJDK 17 이상
- Maven: 3.6 이상
- Oracle Database: 12c 이상

## 주요 특징

1. **고성능 쿼리**: Oracle의 고급 기능 활용 (CONNECT BY, 윈도우 함수 등)
2. **페이징 처리**: 대용량 데이터 효율적 처리
3. **복합 검색**: 다양한 조건의 동적 쿼리 지원
4. **통계 및 분석**: 비즈니스 인사이트를 위한 다양한 분석 기능
5. **트랜잭션 관리**: 데이터 일관성 보장
6. **RESTful API**: 표준화된 API 설계
7. **에러 처리**: 체계적인 예외 처리 및 로깅

## 라이센스

이 프로젝트는 AMZN 내부 사용을 위한 것입니다.
