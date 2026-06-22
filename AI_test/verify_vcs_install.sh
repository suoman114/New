#!/bin/bash

WORK_DIR="${APP_AUDIT:-$(cd "$(dirname "$0")" && pwd)}"
DATE_STR=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$WORK_DIR/VCS_INSTALL_VERIFY_${DATE_STR}.txt"
MY_IP=$(hostname -I | awk '{print $1}')

echo "==================================================" > "$REPORT_FILE"
echo " VCS 녹취 Application 설치 검증 보고서" >> "$REPORT_FILE"
echo " 점검 일시: $(date)" >> "$REPORT_FILE"
echo " 본 서버 IP: $MY_IP" >> "$REPORT_FILE"
echo "==================================================" >> "$REPORT_FILE"

log() { echo -e "$1" | tee -a "$REPORT_FILE"; }

compare_version() {
    local doc_ver=$1
    local cur_ver=$2
    local pkg_name=$3

    if [ "$doc_ver" == "$cur_ver" ]; then
        log "[OK] $pkg_name : $cur_ver (문서 기준 일치)"
    else
        IFS='.' read -r d_maj d_min d_pat d_bld <<< "${doc_ver//-/.}"
        IFS='.' read -r c_maj c_min c_pat c_bld <<< "${cur_ver//-/.}"

        local judge="다름"
        if [ "$d_maj" != "$c_maj" ]; then judge="메이저 다름"
        elif [ "$d_min" != "$c_min" ]; then judge="마이너 다름"
        elif [ "$d_pat" != "$c_pat" ]; then
            if [[ "$c_pat" > "$d_pat" ]]; then judge="패치 상위"
            else judge="패치 하위"; fi
        fi

        log "[WARN] $pkg_name 버전 상이"
        log "  [버전 비교]"
        log "  - 문서 기준: $doc_ver"
        log "  - 설치 RPM : $cur_ver"
        log "  - 판단     : $judge"
    fi
}

# ──────────────────────────────────────────────────────────
log "\n1. 3rd Party RPM 점검"

# Java: 1.8.x 설치 여부만 확인 (버전 무관)
java_rpm=$(rpm -qa | grep -E '^java-1\.8\.0-openjdk-[0-9]' | head -n 1)
if [ -n "$java_rpm" ]; then
    java_ver=$(echo "$java_rpm" | sed -r 's/java-1\.8\.0-openjdk-//g')
    log "[OK] Java OpenJDK 1.8 설치됨 (버전: $java_ver)"
else
    log "[FAIL] Java OpenJDK 1.8 미설치"
fi

# RabbitMQ / Erlang / MariaDB: 문서 기준 버전 비교
for pkg in "rabbitmq-server:3.7.13" "erlang:21.3.7" "MariaDB-server:10.4.12"; do
    p_name=${pkg%:*}
    p_doc=${pkg#*:}
    rpm_chk=$(rpm -qa | grep -i "^$p_name")
    if [ -n "$rpm_chk" ]; then
        p_cur=$(echo "$rpm_chk" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
        compare_version "$p_doc" "$p_cur" "$p_name"
    else
        log "[FAIL] $p_name 미설치"
    fi
done

# ──────────────────────────────────────────────────────────
log "\n2. OS 계정 점검"
id vcs   >/dev/null 2>&1 && log "[OK] vcs 계정 존재 ($(id vcs))"    || log "[FAIL] vcs 계정 없음"
id vcweb >/dev/null 2>&1 && log "[OK] vcweb 계정 존재 ($(id vcweb))" || log "[FAIL] vcweb 계정 없음"

# ──────────────────────────────────────────────────────────
log "\n3. 디렉터리 및 Web 패키지 점검"
for dir in HOME vced vcmc vcmm vcsm vctp; do
    [ -d "/home/vcs/$dir" ] && log "[OK] /home/vcs/$dir 존재" || log "[WARN] /home/vcs/$dir 없음"
done

rpm -qa | grep -q vcapi && log "[OK] vcapi RPM 설치됨" || log "[WARN] vcapi RPM 미설치"
[ -f "/home/vcweb/vcweb/bin/vcweb.sh" ] && log "[OK] vcweb.sh 존재" || log "[WARN] vcweb.sh 없음"

# ──────────────────────────────────────────────────────────
log "\n4. IP 및 프로세스 설정 점검"
VCMC_CONF="/home/vcs/HOME/vcmc_user.config"
if [ -f "$VCMC_CONF" ]; then
    vcmc_ip=$(grep "IP_ADDRESS" "$VCMC_CONF" | awk -F'=' '{print $2}' | tr -d ' \r')
    [ "$vcmc_ip" == "$MY_IP" ] \
        && log "[OK] vcmc_user.config IP 일치 ($vcmc_ip)" \
        || log "[WARN] vcmc_user.config IP 불일치 (설정:$vcmc_ip, 서버:$MY_IP)"

    vcmc_pid=$(pgrep -x vcmc)
    if [ -n "$vcmc_pid" ]; then
        listen_chk=$(ss -tlnp 2>/dev/null | grep "pid=$vcmc_pid,")
        [ -n "$listen_chk" ] \
            && log "[OK] vcmc ALIVE - 포트 LISTEN 상태 확인됨" \
            || log "[WARN] vcmc ALIVE - 포트 LISTEN 확인 안됨"
    else
        log "[-] vcmc 프로세스 미실행 상태"
    fi
fi

VCMM_CONF="/home/vcs/HOME/vcmm_user.config"
if [ -f "$VCMM_CONF" ]; then
    vcmm_ip=$(grep "SDP_LOCAL_IP" "$VCMM_CONF" | awk -F'=' '{print $2}' | tr -d ' \r')
    [ "$vcmm_ip" == "$MY_IP" ] \
        && log "[OK] vcmm_user.config IP 일치 ($vcmm_ip)" \
        || log "[WARN] vcmm_user.config IP 불일치 (설정:$vcmm_ip, 서버:$MY_IP)"
fi

# ──────────────────────────────────────────────────────────
log "\n5. dismc 실행"
if su - vcs -c "command -v dismc" >/dev/null 2>&1; then
    dismc_out=$(su - vcs -c "dismc" 2>&1)
    dismc_rc=$?
    [ $dismc_rc -eq 0 ] \
        && log "[OK] dismc 실행 완료 (exit=$dismc_rc)" \
        || log "[WARN] dismc 종료 코드: $dismc_rc"
    while IFS= read -r line; do
        [ -n "$line" ] && log ">>>$line"
    done <<< "$dismc_out"
else
    log "[WARN] dismc 명령어를 찾을 수 없음 (vcs 계정 PATH 확인 필요)"
fi

# ──────────────────────────────────────────────────────────
log "\n[검증 완료] 상세 내용은 $REPORT_FILE 를 확인하세요."
