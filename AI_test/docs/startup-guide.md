# LTER-infra 서버 기동 가이드

## 환경 구성

| 항목 | 내용 |
|------|------|
| 빌드 위치 | WSL CentOS7 |
| Java | OpenJDK 1.8.0_412 |
| Maven | 3.9.6 (`/opt/apache-maven-3.9.6`) |
| JAR 경로 | `/mnt/d/AI_test/target/LTER-infra-R1.0.0.jar` |
| 기본 포트 | `8080` |

---

## 프로파일별 DB 구성

| 프로파일 | DB | ddl-auto | 용도 |
|----------|----|----------|------|
| `dev` (기본) | H2 인메모리 | create-drop | 개발 / 기능 확인 |
| `prod` | MariaDB | update | 운영 / RPM 배포 |

---

## 빌드

```bash
# 프로젝트 경로로 이동
cd /mnt/d/AI_test

# JAR 빌드 (테스트 스킵)
mvn clean package -DskipTests

# RPM 빌드
mvn clean package -Prpm -DskipTests
```

---

## 기동 방법

### 1. 개발 환경 (H2 내장 DB)

```bash
# 포그라운드 실행 (로그 직접 확인)
java -jar /mnt/d/AI_test/target/LTER-infra-R1.0.0.jar --spring.profiles.active=dev

# 백그라운드 실행
nohup java -jar /mnt/d/AI_test/target/LTER-infra-R1.0.0.jar \
  --spring.profiles.active=dev \
  > /tmp/lter-infra.log 2>&1 &
echo $! > /tmp/lter-infra.pid
echo "PID: $(cat /tmp/lter-infra.pid)"
```

### 2. 운영 환경 (MariaDB)

```bash
# 기본 설정 사용 (application-prod.yml)
java -jar LTER-infra-R1.0.0.jar --spring.profiles.active=prod

# DB 접속 정보 오버라이드
java -jar LTER-infra-R1.0.0.jar \
  --spring.profiles.active=prod \
  --spring.datasource.url=jdbc:mariadb://192.168.1.10:3306/lter_infra \
  --spring.datasource.username=lter \
  --spring.datasource.password=lter.123
```

### 3. 포트 변경이 필요한 경우

```bash
java -jar LTER-infra-R1.0.0.jar \
  --spring.profiles.active=dev \
  --server.port=9090
```

---

## 프로세스 관리

```bash
# 실행 중인 PID 확인
pgrep -fa LTER-infra

# 로그 실시간 확인
tail -f /tmp/lter-infra.log

# 정상 종료
kill $(cat /tmp/lter-infra.pid)

# 강제 종료
pkill -f LTER-infra
```

---

## 기동 확인

```bash
# 서버 상태 확인
curl http://localhost:8080/api/v1/servers

# 정상 응답 예시
# {"success":true,"message":"OK","data":[]}
```

---

## 웹 접근 (Windows 브라우저)

WSL2 IP: `172.22.19.9` (재시작 시 변경될 수 있음)

| 항목 | URL |
|------|-----|
| H2 Console (dev) | http://172.22.19.9:8080/h2-console |
| REST API 서버 목록 | http://172.22.19.9:8080/api/v1/servers |

> WSL IP 확인 명령어: `ip addr show eth0 | grep 'inet '`

### H2 Console 접속 정보

| 항목 | 값 |
|------|----|
| JDBC URL | `jdbc:h2:mem:lter_infra` |
| User Name | `sa` |
| Password | (없음, 빈칸) |

---

## 설정 파일 위치

| 파일 | 용도 |
|------|------|
| `src/main/resources/application.yml` | 공통 설정, 기본 프로파일 지정 |
| `src/main/resources/application-dev.yml` | H2 DB 설정 |
| `src/main/resources/application-prod.yml` | MariaDB 설정 |
