# 🚀 빠른 사용법

## 기본 명령어

```bash
# 시작
./bin/amzn-bo.sh start

# 중지
./bin/amzn-bo.sh stop

# 상태 확인
./bin/amzn-bo.sh status

# 로그 보기
./bin/amzn-bo.sh logs -f
```

## API 테스트

```bash
# 헬스 체크
curl http://localhost:8080/amzn-bo/actuator/health

# 사용자 목록
curl "http://localhost:8080/amzn-bo/api/users?page=1&size=5"

# 상품 목록
curl "http://localhost:8080/amzn-bo/api/products?page=1&size=5"
```

## 톰캣 스타일

```bash
# 시작
./bin/catalina.sh start

# 로그 보기
./bin/catalina.sh logs -f

# 중지
./bin/catalina.sh stop
```

---
자세한 내용은 `README.md` 참조
