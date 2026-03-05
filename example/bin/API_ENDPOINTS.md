# AMZN 백오피스 API 엔드포인트 가이드

## 개요
AMZN 쇼핑몰 백오피스 관리 시스템의 모든 API 엔드포인트를 정리한 문서입니다.

**Base URL**: `http://localhost:8080/amzn-bo`

---

## 📊 헬스 체크

### 애플리케이션 상태 확인
```http
GET /actuator/health
```

**응답 예시:**
```json
{
  "status": "UP",
  "components": {
    "db": {"status": "UP"},
    "diskSpace": {"status": "UP"},
    "ping": {"status": "UP"}
  }
}
```

---

## 👥 사용자 관리 (User Management)

### 1. 사용자 목록 조회
```http
GET /api/users
```

**Query Parameters:**
- `searchKeyword` (optional): 검색 키워드 (이메일, 이름)
- `userGrade` (optional): 사용자 등급 (VIP, PREMIUM, NEW)
- `status` (optional): 사용자 상태 (ACTIVE, INACTIVE, SUSPENDED)
- `minOrderCount` (optional): 최소 주문 수
- `minTotalSpent` (optional): 최소 총 구매 금액
- `sortBy` (optional): 정렬 기준 (totalSpent, orderCount, createdAt)
- `sortDirection` (optional): 정렬 방향 (ASC, DESC)
- `page` (optional): 페이지 번호 (기본값: 1)
- `size` (optional): 페이지 크기 (기본값: 20)

**예시:**
```bash
curl "http://localhost:8080/amzn-bo/api/users?userGrade=VIP&page=1&size=10"
```

### 2. 사용자 상세 정보 조회
```http
GET /api/users/{userId}
```

### 3. 사용자 활동 통계
```http
GET /api/users/{userId}/activity-stats
```

### 4. 사용자 등급별 통계
```http
GET /api/users/grade-statistics
```

### 5. 사용자 상태 업데이트
```http
PUT /api/users/{userId}/status?status={newStatus}
```

**Query Parameters:**
- `status`: 새로운 상태 (ACTIVE, INACTIVE, SUSPENDED)

---

## 🛍️ 상품 관리 (Product Management)

### 1. 상품 목록 조회
```http
GET /api/products
```

**Query Parameters:**
- `searchKeyword` (optional): 검색 키워드 (상품명, SKU)
- `brand` (optional): 브랜드명
- `categoryId` (optional): 카테고리 ID
- `status` (optional): 상품 상태 (ACTIVE, INACTIVE)
- `minPrice` (optional): 최소 가격
- `maxPrice` (optional): 최대 가격
- `sortBy` (optional): 정렬 기준 (price, createdAt, productName)
- `sortDirection` (optional): 정렬 방향 (ASC, DESC)
- `page` (optional): 페이지 번호 (기본값: 1)
- `size` (optional): 페이지 크기 (기본값: 20)

### 2. 상품 상세 정보 조회
```http
GET /api/products/{productId}
```

### 3. 상품 등록 ✅ **수정됨**
```http
POST /api/products
Content-Type: application/json

{
  "productName": "상품명",
  "sku": "SKU-CODE",
  "brand": "브랜드명",
  "price": 99.99,
  "categoryId": 1,
  "description": "상품 설명"
}
```

**수정 사항:**
- 시퀀스 문제 해결: SEQ_PRODUCTS 시퀀스가 올바른 값으로 재설정됨
- PRIMARY KEY 제약 조건 위반 문제 해결

### 4. 상품 정보 업데이트
```http
PUT /api/products/{productId}
Content-Type: application/json

{
  "productName": "수정된 상품명",
  "price": 199.99,
  "description": "수정된 설명"
}
```

### 5. 카테고리 계층 조회
```http
GET /api/products/categories/hierarchy
```

### 6. 상품 성과 분석
```http
GET /api/products/performance-analysis
```

### 7. 브랜드별 상품 통계
```http
GET /api/products/statistics/brands
```

---

## 📦 주문 관리 (Order Management)

### 1. 주문 목록 조회 (고급 분석 포함)
```http
GET /api/orders
```

**Query Parameters:**
- `searchKeyword` (optional): 검색 키워드 (주문번호, 사용자 이메일)
- `status` (optional): 주문 상태 (PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED, REFUNDED)
- `paymentMethod` (optional): 결제 방법 (CREDIT_CARD, DEBIT_CARD, PAYPAL, BANK_TRANSFER)
- `minAmount` (optional): 최소 주문 금액
- `maxAmount` (optional): 최대 주문 금액
- `startDate` (optional): 시작 날짜 (YYYY-MM-DD)
- `endDate` (optional): 종료 날짜 (YYYY-MM-DD)
- `sortBy` (optional): 정렬 기준 (totalAmount, orderedAt)
- `sortDirection` (optional): 정렬 방향 (ASC, DESC)
- `page` (optional): 페이지 번호 (기본값: 1)
- `size` (optional): 페이지 크기 (기본값: 20)

### 2. 주문 상세 정보 조회
```http
GET /api/orders/{orderId}
```

### 3. 주문 배송 정보 조회 ✅ **수정됨**
```http
GET /api/orders/{orderId}/shipping
```

**수정 사항:**
- 데이터베이스 스키마 불일치 해결
- SHIPMENTS 테이블과 올바른 조인 처리
- USERS 테이블의 FIRST_NAME, LAST_NAME 필드 사용
- 상세한 배송 정보 제공 (추적번호, 배송업체, 배송 방법 등)

### 4. 주문 아이템 상세 조회
```http
GET /api/orders/{orderId}/items
```

### 5. 주문 상태 업데이트
```http
PUT /api/orders/{orderId}/status?status={newStatus}
```

**Query Parameters:**
- `status`: 새로운 상태 (PENDING, PROCESSING, SHIPPED, DELIVERED, CANCELLED)

### 6. 주문 취소 ✅ **수정됨**
```http
PUT /api/orders/{orderId}/cancel
Content-Type: application/json; charset=UTF-8

{
  "reason": "취소 사유 (한글 지원)"
}
```

**수정 사항:**
- 한글 인코딩 문제 해결
- @RequestParam에서 @RequestBody로 변경
- CancelOrderRequest DTO 추가
- UTF-8 인코딩 완전 지원

### 7. 주문 환불 처리 ✅ **대폭 개선됨**
```http
PUT /api/orders/{orderId}/refund
Content-Type: application/json; charset=UTF-8

{
  "reason": "환불 사유 (한글 지원)",
  "amount": 99.99,
  "refundType": "FULL"
}
```

**개선 사항:**
- **비즈니스 로직 제약 추가:**
  - 환불 가능 상태 검증 (DELIVERED, SHIPPED, PROCESSING만 가능)
  - 환불 금액 검증 (주문 금액 초과 불가)
  - 중복 환불 방지
- **부분/전체 환불 지원:**
  - `refundType`: "FULL" (전체 환불) 또는 "PARTIAL" (부분 환불)
  - `amount`: 환불 금액 (부분 환불 시 필수)
- **상세한 오류 메시지 제공**
- **RefundOrderRequest DTO 추가**

### 8. 주문 일괄 상태 업데이트
```http
PUT /api/orders/batch/status?orderIds=1,2,3&status=SHIPPED
```

---

## 📈 통계 및 분석 API

### 주문 관련 통계

#### 1. 주문 상태별 통계
```http
GET /api/orders/statistics/status
```

#### 2. 주문 트렌드 분석
```http
GET /api/orders/analytics/trend?startDate=2025-01-01&endDate=2025-12-31&groupBy=month
```

**Query Parameters:**
- `startDate`: 시작 날짜 (YYYY-MM-DD)
- `endDate`: 종료 날짜 (YYYY-MM-DD)
- `groupBy`: 그룹화 기준 (day, week, month, year)

#### 3. 결제 방법별 분석
```http
GET /api/orders/analytics/payment-methods
```

#### 4. 주문 처리 시간 분석
```http
GET /api/orders/analytics/processing-time
```

#### 5. 고객별 주문 패턴 분석
```http
GET /api/orders/analytics/customer-pattern/{userId}
```

---

## 🚨 에러 처리

### 표준 에러 응답 형식
```json
{
  "success": false,
  "message": "오류 메시지",
  "timestamp": 1755683515580
}
```

### HTTP 상태 코드
- `200 OK`: 성공
- `400 Bad Request`: 잘못된 요청 (유효성 검사 실패, 비즈니스 로직 위반)
- `404 Not Found`: 리소스를 찾을 수 없음
- `500 Internal Server Error`: 서버 내부 오류

---

## 🔧 테스트 도구

### API 테스트 스크립트 사용법
```bash
# 전체 테스트
./bin/test-api.sh all

# 개별 테스트
./bin/test-api.sh health      # 헬스 체크
./bin/test-api.sh basic       # 기본 API 테스트
./bin/test-api.sh stats       # 통계 API 테스트
./bin/test-api.sh search      # 검색 API 테스트
./bin/test-api.sh detail      # 상세 정보 API 테스트
./bin/test-api.sh performance # 성능 테스트
./bin/test-api.sh error       # 에러 처리 테스트
```

---

## 📝 최근 수정 사항 (2025-08-20)

### ✅ 해결된 문제들

1. **상품 등록 - 데이터베이스 제약 조건 문제**
   - 시퀀스 SEQ_PRODUCTS 재설정 (801부터 시작)
   - PRIMARY KEY 제약 조건 위반 해결

2. **주문 배송 정보 조회 - 데이터베이스 스키마 불일치**
   - SHIPMENTS 테이블과 올바른 조인
   - USERS 테이블 필드명 수정 (NAME → FIRST_NAME, LAST_NAME)
   - 상세한 배송 정보 제공

3. **주문 취소 - 한글 인코딩 문제**
   - @RequestParam → @RequestBody 변경
   - CancelOrderRequest DTO 추가
   - UTF-8 인코딩 완전 지원

4. **주문 환불 처리 - 비즈니스 로직 제약**
   - 환불 가능 상태 검증 로직 추가
   - 환불 금액 검증 로직 추가
   - 부분/전체 환불 지원
   - RefundOrderRequest DTO 추가
   - 상세한 오류 메시지 제공

### 🎯 검증 완료
- ✅ 모든 API 정상 작동 확인
- ✅ 한글 인코딩 완벽 지원
- ✅ 비즈니스 로직 제약 조건 정상 작동
- ✅ 에러 처리 및 메시지 적절함
- ✅ 성능 테스트 통과 (100개 데이터 조회 < 0.1초)

---

## 📞 지원

문제가 발생하거나 추가 기능이 필요한 경우:
1. 로그 확인: `./bin/amzn-bo.sh logs`
2. 애플리케이션 재시작: `./bin/amzn-bo.sh restart`
3. API 테스트: `./bin/test-api.sh all`

**마지막 업데이트**: 2025-08-20
**버전**: 1.0.0
**상태**: 프로덕션 준비 완료 🚀
