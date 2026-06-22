# LTER-infra 설치 가이드

RPM 패키지(`LTER-infra-R1.0.0.rpm`) 기준 설치 가이드입니다.  
폐쇄망 환경 전제 — 모든 패키지는 오프라인 RPM으로 설치합니다.

---

## 1. 사전 준비 패키지

### 1-1. Java 1.8 (OpenJDK)

#### CentOS 7 / RHEL 7

```bash
# 오프라인 RPM 설치 (의존 패키지 포함)
yum localinstall --disablerepo="*" java-1.8.0-openjdk-headless-*.rpm

# 설치 확인
java -version
# openjdk version "1.8.0_xxx"
```

필요 RPM 목록 (CentOS 7 기준):
```
java-1.8.0-openjdk-headless-1.8.0.xxx.el7.x86_64.rpm
copy-jdk-configs-3.3-10.el7_5.noarch.rpm
tzdata-java-xxxx.el7.noarch.rpm
javapackages-tools-3.4.1-11.el7.noarch.rpm
python-javapackages-3.4.1-11.el7.noarch.rpm
lksctp-tools-1.0.17-2.el7.x86_64.rpm   # (SCTP 지원, 선택)
```

#### Ubuntu 20.04 / 22.04

> Ubuntu는 RPM 패키지를 직접 사용할 수 없으므로 `.deb` 패키지로 준비합니다.

```bash
# 오프라인 deb 설치
dpkg -i openjdk-8-jdk-headless_*.deb

# 설치 확인
java -version
```

필요 deb 패키지 목록:
```
openjdk-8-jdk-headless_8uXXX_amd64.deb
openjdk-8-jre-headless_8uXXX_amd64.deb
libnspr4_*.deb
libnss3_*.deb
ca-certificates-java_*.deb
```

---

### 1-2. MariaDB 10.4

#### CentOS 7

```bash
# 설치
yum localinstall --disablerepo="*" \
    MariaDB-server-10.4.*.el7.x86_64.rpm \
    MariaDB-client-10.4.*.el7.x86_64.rpm \
    MariaDB-common-10.4.*.el7.x86_64.rpm \
    MariaDB-compat-10.4.*.el7.x86_64.rpm \
    galera-4-*.el7.x86_64.rpm

# 서비스 시작 및 활성화
systemctl enable mariadb
systemctl start mariadb

# 초기 보안 설정
mysql_secure_installation
```

#### Ubuntu 20.04

```bash
dpkg -i \
    mariadb-server-10.4_*.deb \
    mariadb-client-10.4_*.deb \
    mariadb-common_*.deb \
    libmariadb3_*.deb

systemctl enable mariadb
systemctl start mariadb
mysql_secure_installation
```

---

### 1-3. Ansible

> Ansible은 LTER-infra 서버(관리 노드)에만 설치합니다. 대상 서버에는 불필요합니다.

#### CentOS 7

```bash
# EPEL 없이 오프라인 설치 (Ansible 2.9 기준)
yum localinstall --disablerepo="*" \
    ansible-2.9.*.el7.noarch.rpm \
    python-jinja2-*.el7.noarch.rpm \
    python-paramiko-*.el7.noarch.rpm \
    python-cryptography-*.el7.x86_64.rpm \
    python-cffi-*.el7.x86_64.rpm \
    sshpass-1.*.el7.x86_64.rpm

# 설치 확인
ansible --version
```

#### Ubuntu 20.04

```bash
dpkg -i \
    ansible_2.9.*.deb \
    python3-jinja2_*.deb \
    python3-paramiko_*.deb \
    sshpass_*.deb

ansible --version
```

**sshpass 필수**: Ansible이 패스워드 기반 SSH 인증 시 필요합니다.

---

## 2. MariaDB 초기 설정

LTER-infra 앱이 사용할 DB와 계정을 생성합니다.

```bash
mysql -u root -p << 'EOF'
-- DB 생성
CREATE DATABASE lter_infra CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 계정 생성 및 권한 부여
CREATE USER 'lter'@'localhost' IDENTIFIED BY 'lter.123';
GRANT ALL PRIVILEGES ON lter_infra.* TO 'lter'@'localhost';
FLUSH PRIVILEGES;
EOF
```

> 비밀번호(`lter.123`)는 `application-prod.yml`의 `spring.datasource.password`와 일치해야 합니다.

---

## 3. LTER-infra RPM 설치

```bash
# RPM 설치
rpm -ivh LTER-infra-R1.0.0-1.noarch.rpm

# 설치 후 자동 생성 항목:
#   /opt/lter/infra/LTER-infra-R1.0.0.jar
#   /opt/lter/infra/config/application.yml
#   /opt/lter/infra/config/application-prod.yml
#   /opt/lter/infra/ansible/*.yml  (Ansible 플레이북)
#   /opt/lter/infra/scripts/*.sh   (Validation 스크립트)
#   /usr/lib/systemd/system/lter-infra.service
#   /var/log/lter-infra/
```

---

## 4. 설정 파일 수정

### application-prod.yml 수정

```bash
vi /opt/lter/infra/config/application-prod.yml
```

주요 수정 항목:
```yaml
spring:
  datasource:
    url: jdbc:mariadb://localhost:3306/lter_infra?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Seoul
    username: lter
    password: lter.123      # MariaDB 계정 비밀번호
```

### application.yml 수정 (Ansible/경로 설정)

```bash
vi /opt/lter/infra/config/application.yml
```

```yaml
infra:
  ansible:
    playbook-dir: /opt/lter/infra/ansible   # 플레이북 경로 (RPM 설치 경로)
    inventory: /opt/lter/infra/ansible/inventory/hosts
  git:
    local-base-dir: /opt/lter/infra/repos
  script:
    local-base-dir: /opt/lter/infra/scripts
  package:
    local-base-dir: /opt/lter/infra/packages
```

### Ansible Inventory 디렉토리 생성

```bash
mkdir -p /opt/lter/infra/ansible/inventory
cat > /opt/lter/infra/ansible/inventory/hosts << 'EOF'
[all]
# 대상 서버는 웹 UI에서 동적으로 생성됩니다.
# 이 파일은 Ansible executor가 실행 전 자동 갱신합니다.
EOF
chown -R lter:lter /opt/lter/infra/ansible
```

---

## 5. 서비스 시작

```bash
# 서비스 시작
systemctl start lter-infra

# 시작 확인 (포트 8080 Listen 확인)
systemctl status lter-infra
ss -tlnp | grep 8080

# 로그 확인
journalctl -u lter-infra -f
# 또는
tail -f /var/log/lter-infra/app.log
```

정상 기동 로그 예시:
```
Started InfraApplication in 12.345 seconds
Tomcat started on port(s): 8080 (http)
```

---

## 6. 방화벽 설정

### CentOS 7 (firewalld)

```bash
firewall-cmd --permanent --add-port=8080/tcp
firewall-cmd --reload
```

### Ubuntu (ufw)

```bash
ufw allow 8080/tcp
ufw reload
```

---

## 7. 웹 UI 접속

브라우저에서 접속:
```
http://<서버IP>:8080
```

---

## 8. 업그레이드

새 버전 RPM 배포 시:

```bash
# 서비스 중지 후 업그레이드
systemctl stop lter-infra
rpm -Uvh LTER-infra-R1.1.0-1.noarch.rpm
systemctl start lter-infra
```

> `rpm -Uvh`는 기존 설정 파일(`/opt/lter/infra/config/*.yml`)을 덮어쓰지 않습니다.  
> 단, 새 버전에서 설정 항목이 추가된 경우 수동으로 반영해야 합니다.

---

## 9. 제거

```bash
# RPM 제거 (설정 파일, 로그, 데이터는 유지됨)
rpm -e LTER-infra

# 완전 삭제 시 (설정, 로그 포함)
rpm -e LTER-infra
rm -rf /opt/lter
rm -rf /var/log/lter-infra
userdel -r lter 2>/dev/null || true
groupdel lter 2>/dev/null || true
```

---

## 10. 트러블슈팅

| 증상 | 원인 | 조치 |
|------|------|------|
| 포트 8080 미응답 | 기동 실패 | `journalctl -u lter-infra -n 50` 로그 확인 |
| DB 연결 실패 | MariaDB 미기동 또는 계정 오류 | `systemctl status mariadb`, DB 계정 확인 |
| Ansible 실행 실패 | sshpass 미설치 | `yum localinstall sshpass-*.rpm` |
| `Permission denied` | lter 사용자 권한 부족 | `chown -R lter:lter /opt/lter` |
| `java: command not found` | JAVA_HOME 미설정 | `/usr/bin/java` 경로 확인 또는 심볼릭 링크 |
| 로그파일 미생성 | `/var/log/lter-infra` 권한 | `chown lter:lter /var/log/lter-infra` |

---

## 부록: 오프라인 RPM 수집 방법 (인터넷 연결 가능한 별도 서버에서)

### CentOS 7에서 의존 패키지 일괄 다운로드

```bash
# Java
yumdownloader --resolve --destdir=/tmp/rpms java-1.8.0-openjdk-headless

# MariaDB (MariaDB 공식 repo 설정 후)
yumdownloader --resolve --destdir=/tmp/rpms MariaDB-server MariaDB-client

# Ansible + sshpass
yumdownloader --resolve --destdir=/tmp/rpms ansible sshpass

# 다운로드된 RPM을 폐쇄망으로 이전
tar czf offline-rpms.tar.gz /tmp/rpms/
```

### Ubuntu에서 의존 패키지 일괄 다운로드

```bash
apt-get download $(apt-rdepends openjdk-8-jdk-headless | grep -v "^ " | grep -v "^dpkg")
apt-get download $(apt-rdepends mariadb-server | grep -v "^ " | grep -v "^dpkg")
apt-get download ansible sshpass
```
