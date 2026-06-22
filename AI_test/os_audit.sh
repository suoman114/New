#!/bin/bash
# ============================================================
# OS Audit Script v2.0
# 사용법  : sudo ./os_audit.sh [서버명]
# 환경변수 : OS_AUDIT_REQUIRED_USERS  (기본: vcs|vcsdn)
#            OS_AUDIT_BACKUP_PATHS    (기본: /backup)
#            OS_AUDIT_SYSCTL_FILE     (기본: /etc/sysctl.d/vcs_system.conf)
# ============================================================

SERVER_NAME="${1:-$(hostname)}"
SUDO="${SUDO:-sudo}"
REQUIRED_USERS="${OS_AUDIT_REQUIRED_USERS:-vcs|vcsdn}"
BACKUP_PATHS="${OS_AUDIT_BACKUP_PATHS:-/backup}"
SYSCTL_FILE="${OS_AUDIT_SYSCTL_FILE:-/etc/sysctl.d/vcs_system.conf}"

# ─── Helpers ──────────────────────────────────────────────────

section() {
    printf '\n%s\n' "===SECTION:$1==="
}

config_item() {
    printf '\n%s\n' "===CONFIG:$1==="
    printf '%s\n'   "GUIDE:$2"
    printf '%s\n'   "RESULT:"
}

# sudo 가 필요한 명령어 실행
run() {
    $SUDO bash -c "$1" 2>/dev/null || echo "  N/A"
}

# 주석/빈줄 제거 (파일명 인자)
strip_comments() {
    grep -vE '^\s*#|^\s*$' "$1" 2>/dev/null || echo "  (없음)"
}

# 구분선
divider() {
    printf '%.0s─' {1..80}; echo
}

# ─── SECTION: META ────────────────────────────────────────────

section "META"
printf '%-15s %s\n' "server:"    "$SERVER_NAME"
printf '%-15s %s\n' "hostname:"  "$(hostname)"
printf '%-15s %s\n' "date:"      "$(date -Iseconds)"
printf '%-15s %s\n' "collector:" "$(whoami)"
printf '%-15s %s\n' "kernel:"    "$(uname -r)"
printf '%-15s %s\n' "os:"        "$(cat /etc/redhat-release 2>/dev/null || grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"

# ─── SECTION: User ────────────────────────────────────────────

section "User"
printf '%-15s %-6s %-6s %-30s %s\n' "계정명" "UID" "GID" "HOME" "SHELL"
divider
grep -E "^root:|^(${REQUIRED_USERS}):" /etc/passwd 2>/dev/null | \
while IFS=: read -r user _ uid gid _ home shell; do
    printf '%-15s %-6s %-6s %-30s %s\n' "$user" "$uid" "$gid" "$home" "$shell"
done || echo "  N/A"

# ─── SECTION: Network ─────────────────────────────────────────

section "Network"
echo "[ IP 주소 ]"
printf '  %-12s %-20s\n' "인터페이스" "IP/Mask"
printf '  '; divider
ip -4 addr show 2>/dev/null | awk '
    /^[0-9]+:/ { iface=$2; gsub(":","",iface) }
    /inet /    { printf "  %-12s %-20s\n", iface, $2 }
' || echo "  N/A"

echo ""
echo "[ 라우팅 테이블 ]"
ip route show 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

echo ""
echo "[ 본딩 상태 ]"
if compgen -G "/proc/net/bonding/*" > /dev/null 2>&1; then
    for bond in /proc/net/bonding/*; do
        printf '  === %s ===\n' "$(basename "$bond")"
        grep -E 'Bonding Mode|MII Status|Speed|Duplex|Slave Interface' "$bond" 2>/dev/null | \
        while read -r l; do printf '    %s\n' "$l"; done
    done
else
    echo "  본딩 없음"
fi

# ─── SECTION: Sudo ────────────────────────────────────────────

section "Sudo"
printf '%-50s %s\n' "설정" "파일"
divider
for f in /etc/sudoers /etc/sudoers.d/*; do
    [ -f "$f" ] || continue
    strip_comments "$f" | while read -r l; do
        printf '%-50s %s\n' "$l" "$f"
    done
done

# ─── SECTION: ulimit ──────────────────────────────────────────

section "ulimit"
echo "[ /etc/security/limits.conf ]"
printf '  %-15s %-10s %-20s %s\n' "도메인" "타입" "항목" "값"
printf '  '; divider
strip_comments /etc/security/limits.conf | \
awk '{printf "  %-15s %-10s %-20s %s\n", $1, $2, $3, $4}'

echo ""
echo "[ /etc/security/limits.d/* ]"
for f in /etc/security/limits.d/*.conf; do
    [ -f "$f" ] || continue
    printf '  === %s ===\n' "$f"
    strip_comments "$f" | awk '{printf "    %-15s %-10s %-20s %s\n", $1, $2, $3, $4}'
done

# ─── SECTION: Kernel ──────────────────────────────────────────

section "Kernel"
printf '  sysctl file: %s\n' "$SYSCTL_FILE"
if [ -f "$SYSCTL_FILE" ]; then
    strip_comments "$SYSCTL_FILE" | while read -r l; do printf '  %s\n' "$l"; done
else
    printf '  [없음] %s\n' "$SYSCTL_FILE"
fi

# ─── SECTION: SSH ─────────────────────────────────────────────

section "SSH"
printf '  %-35s %s\n' "파라미터" "값"
divider
grep -vE '^\s*#|^\s*$' /etc/ssh/sshd_config 2>/dev/null | \
while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

# ─── SECTION: Disk ────────────────────────────────────────────

section "Disk"
echo "[ 파일시스템 사용량 ]"
df -hT 2>/dev/null | grep -v tmpfs | \
awk 'NR==1 {printf "  %-25s %-8s %-6s %-6s %-6s %-6s %s\n",$1,$2,$3,$4,$5,$6,$7}
     NR>1  {printf "  %-25s %-8s %-6s %-6s %-6s %-6s %s\n",$1,$2,$3,$4,$5,$6,$7}' || echo "  N/A"

echo ""
echo "[ Inode 사용량 ]"
df -i 2>/dev/null | grep -v tmpfs | \
awk 'NR==1 {printf "  %-25s %-10s %-10s %-10s %s\n",$1,$2,$3,$4,$5}
     NR>1  {printf "  %-25s %-10s %-10s %-10s %s\n",$1,$2,$3,$4,$5}' | head -15

# ─── SECTION: SW_Backup_list ──────────────────────────────────

section "SW_Backup_list"
echo "[ 백업 경로 ]"
for _p in $(echo "$BACKUP_PATHS" | tr ',' ' '); do
    if [ -d "$_p" ]; then
        printf '  [OK]   %s\n' "$_p"
        ls -la "$_p" 2>/dev/null | head -10 | while read -r l; do printf '    %s\n' "$l"; done
    else
        printf '  [없음] %s\n' "$_p"
    fi
done

echo ""
echo "[ 백업 Cron ]"
for _c in skt-osbackup os_monthly; do
    f="/etc/cron.d/$_c"
    if [ -f "$f" ]; then
        printf '  === %s ===\n' "$f"
        strip_comments "$f" | while read -r l; do printf '    %s\n' "$l"; done
    else
        printf '  [없음] %s\n' "$f"
    fi
done

# ─── SECTION: config_full_audit ───────────────────────────────

section "config_full_audit"

# ══════════════════════════════════════════════════════
# 시스템 기본 (1~10)
# ══════════════════════════════════════════════════════

config_item "1. Firmware 버전" "H/W 모든 Part 최신 버전 설치 원칙"
echo "  N/A (H/W 별도 확인)"

config_item "2. BIOS 설정" "Workload Virtualization, Power Profile 등"
echo "  N/A (H/W 별도 확인)"

config_item "3. Time Zone / NTP" "Asia/Seoul (KST), NTP 동기화 확인"
timedatectl 2>/dev/null | grep -E 'Local time|Time zone|NTP|synchronized' | \
while read -r l; do printf '  %s\n' "$l"; done || date 2>/dev/null || echo "  N/A"

config_item "4. HOSTNAME" "FQDN Naming Rule 준수"
printf '  hostname      : %s\n' "$(hostname)"
printf '  hostname -f   : %s\n' "$(hostname -f 2>/dev/null || echo N/A)"
printf '  /etc/hostname : %s\n' "$(cat /etc/hostname 2>/dev/null || echo N/A)"

config_item "5. SELinux 설정" "SELINUX=disabled"
printf '  config  : %s\n' "$(grep -i ^SELINUX= /etc/selinux/config 2>/dev/null || echo N/A)"
printf '  runtime : %s\n' "$(getenforce 2>/dev/null || echo N/A)"

config_item "6. Partition / Filesystem" "df -hT (tmpfs 제외)"
df -hT 2>/dev/null | grep -v tmpfs | \
awk 'NR==1 {printf "  %-25s %-8s %-6s %-6s %-6s %-6s %s\n",$1,$2,$3,$4,$5,$6,$7}
     NR>1  {printf "  %-25s %-8s %-6s %-6s %-6s %-6s %s\n",$1,$2,$3,$4,$5,$6,$7}' || echo "  N/A"

config_item "7. Swap Space" "표준 8GB"
free -h 2>/dev/null | awk 'NR==1{printf "  %-10s %-10s %-10s %-10s %-10s %s\n",$1,$2,$3,$4,$5,$6}
                            NR>1{printf "  %-10s %-10s %-10s %-10s %-10s %s\n",$1,$2,$3,$4,$5,$6}' || echo "  N/A"

config_item "8. 필수 RPM 패키지 설치" "bash-completion, bind-utils, bzip2 등"
REQUIRED_RPMS="bash-completion bind-utils bzip2 ethtool lsof net-tools pciutils rsync sos strace sysstat tcpdump traceroute unzip vim-enhanced zip iptraf-ng iptstate nmap nmap-ncat numactl dstat iotop lsscsi ipmitool psmisc sysfsutils kernel-tools wget htop"
ALL_RPMS=$(rpm -qa 2>/dev/null)
printf '  %-30s %s\n' "패키지명" "결과"
divider
for pkg in $REQUIRED_RPMS; do
    ver=$(echo "$ALL_RPMS" | grep "^${pkg}-" | head -1)
    if [ -n "$ver" ]; then
        printf '  %-30s [OK]   %s\n' "$pkg" "$ver"
    else
        printf '  %-30s [MISS] 미설치\n' "$pkg"
    fi
done

config_item "9. 서비스 관리" "enabled 된 서비스 목록"
systemctl list-unit-files --type=service 2>/dev/null | grep -i enabled | \
awk '{printf "  %-45s %s\n", $1, $2}' | head -50 || echo "  N/A"

config_item "10. 사용자 계정 존재 확인" "skroot, suser, sguser, smartuser, tcore, bkms"
printf '  %-15s %s\n' "계정" "결과"
divider
for u in skroot suser sguser smartuser tcore bkms; do
    if id "$u" &>/dev/null; then
        printf '  %-15s [OK]   %s\n' "$u" "$(id "$u")"
    else
        printf '  %-15s [없음]\n' "$u"
    fi
done

# ══════════════════════════════════════════════════════
# 계정 / 보안 (11~20)
# ══════════════════════════════════════════════════════

config_item "11. /etc/passwd (필수 계정)" "required_users: $REQUIRED_USERS"
printf '  %-15s %-6s %-6s %-30s %s\n' "계정" "UID" "GID" "HOME" "SHELL"
divider
grep -E "^(${REQUIRED_USERS}):" /etc/passwd 2>/dev/null | \
while IFS=: read -r user _ uid gid _ home shell; do
    printf '  %-15s %-6s %-6s %-30s %s\n' "$user" "$uid" "$gid" "$home" "$shell"
done || echo "  N/A"

config_item "12. /etc/group" "wheel, vcs, vcsdn 그룹 확인"
grep -E 'wheel|vcs|vcsdn' /etc/group 2>/dev/null | \
while IFS=: read -r grp _ gid members; do
    printf '  %-15s GID:%-6s 멤버: %s\n' "$grp" "$gid" "$members"
done || echo "  N/A"

config_item "13. OS Backup 설정" "cron 등록 여부, /backup 경로 존재"
for _c in skt-osbackup os_monthly; do
    f="/etc/cron.d/$_c"
    [ -f "$f" ] && printf '  [OK]   %s\n' "$f" || printf '  [없음] %s\n' "$f"
done
for _p in $(echo "$BACKUP_PATHS" | tr ',' ' '); do
    [ -d "$_p" ] && printf '  [OK]   %s\n' "$_p" || printf '  [없음] %s\n' "$_p"
done

config_item "14.1 IP 주소" "ip -f inet -o addr"
ip -f inet -o addr 2>/dev/null | awk '{printf "  %-12s %s\n", $2, $4}' || echo "  N/A"

config_item "14.2 Bonding 설정 (ifcfg)" "mode=1 (active-backup)"
if compgen -G "/etc/sysconfig/network-scripts/ifcfg-bond*" > /dev/null 2>&1; then
    for f in /etc/sysconfig/network-scripts/ifcfg-bond*; do
        printf '  === %s ===\n' "$f"
        grep -E '^DEVICE|^BONDING_OPTS|^IPADDR|^NETMASK|^BOOTPROTO' "$f" 2>/dev/null | \
        while read -r l; do printf '    %s\n' "$l"; done
    done
else
    echo "  본딩 설정 파일 없음"
fi

config_item "15. /etc/hosts" "로컬 호스트 매핑"
strip_comments /etc/hosts | while read -r l; do printf '  %s\n' "$l"; done

config_item "16. /etc/resolv.conf" "DNS 설정"
strip_comments /etc/resolv.conf | while read -r l; do printf '  %s\n' "$l"; done

config_item "17. /etc/security/limits.conf" "nofile 65535, nproc 65535"
strip_comments /etc/security/limits.conf | \
awk '{printf "  %-15s %-10s %-20s %s\n", $1, $2, $3, $4}'

config_item "18. sysctl 커널 파라미터 (vcs)" "$SYSCTL_FILE"
if [ -f "$SYSCTL_FILE" ]; then
    strip_comments "$SYSCTL_FILE" | while read -r l; do printf '  %s\n' "$l"; done
else
    printf '  [없음] %s\n' "$SYSCTL_FILE"
fi

config_item "19. PermitRootLogin" "PermitRootLogin no 권장"
val=$(grep -i '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null | head -1 || echo "설정 없음")
printf '  %s\n' "$val"
echo "$val" | grep -qi 'no' && echo "  [OK]" || echo "  [WARN] root 로그인 허용 상태"

config_item "20. SSH authorized_keys" "주요 계정 authorized_keys 현황"
printf '  %-15s %-5s %s\n' "계정" "키수" "경로"
divider
for u in root $(grep -E "^(${REQUIRED_USERS}):" /etc/passwd 2>/dev/null | cut -d: -f1); do
    home=$(getent passwd "$u" 2>/dev/null | cut -d: -f6)
    ak="${home}/.ssh/authorized_keys"
    if [ -f "$ak" ]; then
        cnt=$(wc -l < "$ak" 2>/dev/null || echo 0)
        printf '  %-15s %-5s %s\n' "$u" "${cnt}개" "$ak"
    else
        printf '  %-15s %-5s %s\n' "$u" "-" "${ak} (없음)"
    fi
done

# ══════════════════════════════════════════════════════
# SSH / 서비스 / 로깅 (21~30)
# ══════════════════════════════════════════════════════

config_item "21. /etc/sudoers" "sudo 권한 전체 설정"
for f in /etc/sudoers /etc/sudoers.d/*; do
    [ -f "$f" ] || continue
    printf '  === %s ===\n' "$f"
    strip_comments "$f" | while read -r l; do printf '    %s\n' "$l"; done
done

config_item "22. NTP 동기화" "chronyd/ntpd 상태 및 실제 동기화 확인"
printf '  ntpd    : %s\n' "$(systemctl is-active ntpd 2>/dev/null || echo inactive)"
printf '  chronyd : %s\n' "$(systemctl is-active chronyd 2>/dev/null || echo inactive)"
echo "  [ 동기화 상태 ]"
if chronyc tracking &>/dev/null; then
    chronyc tracking 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
    echo "  [ chronyc sources ]"
    chronyc sources 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
else
    ntpq -p 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done || echo "    N/A"
fi

config_item "23. 방화벽 (firewalld)" "disabled 권장"
printf '  active  : %s\n' "$(systemctl is-active firewalld 2>/dev/null || echo N/A)"
printf '  enabled : %s\n' "$(systemctl is-enabled firewalld 2>/dev/null || echo N/A)"

config_item "24. kdump" "kdump 설정 및 상태"
printf '  active  : %s\n' "$(systemctl is-active kdump 2>/dev/null || echo N/A)"
printf '  enabled : %s\n' "$(systemctl is-enabled kdump 2>/dev/null || echo N/A)"
echo "  [ /etc/kdump.conf 주요 설정 ]"
strip_comments /etc/kdump.conf | head -10 | while read -r l; do printf '    %s\n' "$l"; done

config_item "25. rsyslog" "로깅 서비스 상태"
printf '  active  : %s\n' "$(systemctl is-active rsyslog 2>/dev/null || echo N/A)"
echo "  [ 주요 설정 ]"
grep -vE '^\s*#|^\s*$|\$ModLoad|\$Input' /etc/rsyslog.conf 2>/dev/null | head -15 | \
while read -r l; do printf '    %s\n' "$l"; done

config_item "26. crond" "cron 서비스 상태"
printf '  active  : %s\n' "$(systemctl is-active crond 2>/dev/null || echo N/A)"
printf '  enabled : %s\n' "$(systemctl is-enabled crond 2>/dev/null || echo N/A)"

config_item "27. logrotate" "로그 로테이션 설정 목록"
ls -1 /etc/logrotate.d/ 2>/dev/null | while read -r f; do printf '  %s\n' "$f"; done || echo "  N/A"

config_item "28. 커널 버전" "uname -r"
uname -r 2>/dev/null || echo "  N/A"

config_item "29. OS 버전" "릴리즈 정보"
cat /etc/redhat-release 2>/dev/null || \
grep -E '^PRETTY_NAME|^VERSION_ID' /etc/os-release 2>/dev/null || echo "  N/A"

config_item "30. /etc/rc.local" "부팅 시 실행 스크립트"
RC_FILE=""
[ -f /etc/rc.local ]       && RC_FILE=/etc/rc.local
[ -f /etc/rc.d/rc.local ]  && RC_FILE=/etc/rc.d/rc.local
if [ -n "$RC_FILE" ]; then
    strip_comments "$RC_FILE" | grep -v '^exit' | while read -r l; do printf '  %s\n' "$l"; done
else
    echo "  파일 없음"
fi

# ══════════════════════════════════════════════════════
# 보안 감사 (31~40)
# ══════════════════════════════════════════════════════

config_item "31. auditd" "보안 감사 서비스 상태"
printf '  active  : %s\n' "$(systemctl is-active auditd 2>/dev/null || echo N/A)"
printf '  enabled : %s\n' "$(systemctl is-enabled auditd 2>/dev/null || echo N/A)"

config_item "32. 실패한 서비스" "systemctl --failed"
failed=$(systemctl --failed 2>/dev/null | grep -E '●|UNIT' | head -20)
if [ -n "$failed" ]; then
    echo "$failed" | while read -r l; do printf '  %s\n' "$l"; done
else
    echo "  실패한 서비스 없음"
fi

config_item "33. cron 전체 현황" "root crontab + /etc/cron.d/* + /var/spool/cron/*"
echo "  [ root crontab ]"
crontab -l 2>/dev/null | grep -vE '^\s*#|^\s*$' | \
while read -r l; do printf '    %s\n' "$l"; done || echo "    없음"
echo "  [ /etc/cron.d/ ]"
for f in /etc/cron.d/*; do
    [ -f "$f" ] || continue
    printf '    === %s ===\n' "$f"
    strip_comments "$f" | while read -r l; do printf '      %s\n' "$l"; done
done
echo "  [ /var/spool/cron/ ]"
for f in /var/spool/cron/*; do
    [ -f "$f" ] || continue
    printf '    === %s ===\n' "$f"
    cat "$f" 2>/dev/null | grep -vE '^\s*#|^\s*$' | while read -r l; do printf '      %s\n' "$l"; done
done

config_item "34. UID 0 계정 목록" "root 외 UID 0 계정 점검"
awk -F: '$3==0 {print "  "$1" (UID 0)"}' /etc/passwd 2>/dev/null || echo "  N/A"

config_item "35. 패스워드 미설정 계정" "/etc/shadow empty password"
run "awk -F: '(\$2==\"\" || \$2==\"!\")&&\$1!=\"nfsnobody\"{print \"  [WARN] \"\$1\": 패스워드 없음/잠김\"}' /etc/shadow"

config_item "36. SUID/SGID 파일" "주요 경로 내 SUID 파일 목록"
find /usr /bin /sbin -perm /6000 -type f 2>/dev/null | head -20 | \
while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "37. 로그인 실패 이력" "/var/log/secure 최근 10건"
grep -iE 'Failed password|authentication failure' /var/log/secure 2>/dev/null | tail -10 | \
while read -r l; do printf '  %s\n' "$l"; done || \
grep -iE 'Failed password|authentication failure' /var/log/auth.log 2>/dev/null | tail -10 | \
while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "38. 현재 로그인 사용자 / 최근 이력" "who, last"
echo "  [ 현재 로그인 ]"
who 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done || echo "    없음"
echo "  [ 최근 로그인 10건 ]"
last -n 10 2>/dev/null | head -12 | while read -r l; do printf '    %s\n' "$l"; done

config_item "39. hosts.allow / hosts.deny" "TCP Wrapper 설정"
echo "  [ hosts.allow ]"
strip_comments /etc/hosts.allow | while read -r l; do printf '    %s\n' "$l"; done
echo "  [ hosts.deny ]"
strip_comments /etc/hosts.deny | while read -r l; do printf '    %s\n' "$l"; done

config_item "40. 시스템 로그 에러" "최근 에러/크리티컬 15건"
grep -iE 'error|failed|critical' /var/log/messages 2>/dev/null | tail -15 | \
while read -r l; do printf '  %s\n' "$l"; done || \
journalctl -p err -n 15 --no-pager 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || \
echo "  N/A"

# ══════════════════════════════════════════════════════
# 하드웨어 / 리소스 (41~50)
# ══════════════════════════════════════════════════════

config_item "41. 메모리 정보" "MemTotal, MemFree, Swap"
grep -E 'MemTotal|MemFree|MemAvailable|Buffers:|^Cached:|SwapTotal|SwapFree' /proc/meminfo 2>/dev/null | \
awk '{printf "  %-20s %s %s\n", $1, $2, $3}' || echo "  N/A"

config_item "42. CPU 정보" "소켓/코어/스레드, 모델명"
lscpu 2>/dev/null | grep -E '^CPU\(s\)|^Socket|^Core|^Thread|^Model name|^Architecture|^NUMA' | \
awk -F: '{printf "  %-35s %s\n", $1, $2}' || \
printf '  CPU 수: %s\n' "$(grep -c '^processor' /proc/cpuinfo 2>/dev/null || echo N/A)"

config_item "43. NUMA topology" "numactl --hardware"
numactl --hardware 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A (numactl 미설치)"

config_item "44. HugePages 설정" "HugePages_Total, transparent_hugepage"
grep -E 'HugePage|Hugepage' /proc/meminfo 2>/dev/null | \
awk '{printf "  %-30s %s\n", $1, $2" "$3}' || echo "  N/A"
printf '  %-30s %s\n' "vm.nr_hugepages:"      "$(sysctl -n vm.nr_hugepages 2>/dev/null || echo N/A)"
printf '  %-30s %s\n' "transparent_hugepage:" "$(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo N/A)"

config_item "45. 디스크 I/O 스케줄러" "/sys/block/*/queue/scheduler"
found=0
for dev in /sys/block/sd* /sys/block/vd* /sys/block/nvme* /sys/block/xvd*; do
    [ -f "${dev}/queue/scheduler" ] || continue
    printf '  %-10s : %s\n' "$(basename "$dev")" "$(cat "${dev}/queue/scheduler" 2>/dev/null)"
    found=1
done
[ "$found" -eq 0 ] && echo "  N/A"

config_item "46. /etc/fstab" "파일시스템 마운트 설정"
strip_comments /etc/fstab | \
awk '{printf "  %-30s %-15s %-8s %-20s %-4s %s\n", $1,$2,$3,$4,$5,$6}'

config_item "47. 마운트 현황" "현재 마운트된 파일시스템"
mount 2>/dev/null | grep -v tmpfs | while read -r l; do printf '  %s\n' "$l"; done | head -20 || echo "  N/A"

config_item "48. sysstat (sar/iostat)" "설치 및 서비스 상태"
printf '  sar    : %s\n' "$(which sar 2>/dev/null || echo 미설치)"
printf '  iostat : %s\n' "$(which iostat 2>/dev/null || echo 미설치)"
printf '  sysstat service: %s\n' "$(systemctl is-active sysstat 2>/dev/null || echo N/A)"

config_item "49. tuned 프로파일" "현재 활성 프로파일"
tuned-adm active 2>/dev/null || echo "  N/A"

config_item "50. 시스템 uptime / 부하" "uptime, load average"
uptime 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

# ══════════════════════════════════════════════════════
# 성능 / 튜닝 (51~60)
# ══════════════════════════════════════════════════════

config_item "51. vm 커널 파라미터" "swappiness, dirty_ratio 등"
for param in vm.swappiness vm.dirty_ratio vm.dirty_background_ratio vm.overcommit_memory vm.min_free_kbytes; do
    printf '  %-40s = %s\n' "$param" "$(sysctl -n "$param" 2>/dev/null || echo N/A)"
done

config_item "52. net 커널 파라미터" "net.core, net.ipv4 주요값"
for param in net.core.somaxconn net.core.rmem_max net.core.wmem_max \
             net.ipv4.tcp_fin_timeout net.ipv4.ip_local_port_range \
             net.ipv4.tcp_tw_reuse net.ipv4.tcp_max_syn_backlog \
             net.ipv4.tcp_syncookies net.ipv4.tcp_keepalive_time; do
    printf '  %-40s = %s\n' "$param" "$(sysctl -n "$param" 2>/dev/null || echo N/A)"
done

config_item "53. IRQ Affinity / NUMA Balance" "kernel.numa_balancing"
printf '  kernel.numa_balancing : %s\n' "$(sysctl -n kernel.numa_balancing 2>/dev/null || echo N/A)"
printf '  kernel.pid_max        : %s\n' "$(sysctl -n kernel.pid_max 2>/dev/null || echo N/A)"

config_item "54. 현재 ulimit (shell)" "ulimit -a (실제 적용된 값)"
ulimit -a 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "55. 디스크 I/O 현황" "iostat -x 1 1"
iostat -x 1 1 2>/dev/null | tail -20 | while read -r l; do printf '  %s\n' "$l"; done || echo "  sysstat 미설치"

config_item "56. 네트워크 연결 통계" "ss -s"
ss -s 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "57. 열린 포트 목록" "ss -tlnp (LISTEN 상태)"
printf '  %-8s %-30s %s\n' "상태" "로컬주소:포트" "프로세스"
divider
ss -tlnp 2>/dev/null | awk 'NR>1 {printf "  %-8s %-30s %s\n", $1, $4, $6}' || \
netstat -tlnp 2>/dev/null | awk 'NR>2 {printf "  %-8s %-30s %s\n", $1, $4, $7}' || \
echo "  N/A"

config_item "58. 로드된 커널 모듈" "lsmod 상위 30개"
lsmod 2>/dev/null | awk 'NR==1{printf "  %-25s %-10s %s\n",$1,$2,$3}
                          NR>1{printf "  %-25s %-10s %s\n",$1,$2,$3}' | head -31 || echo "  N/A"

config_item "59. 실행 중인 주요 프로세스" "CPU 사용률 상위 10"
printf '  %-10s %-7s %-5s %-5s %s\n' "USER" "PID" "%CPU" "%MEM" "COMMAND"
divider
ps aux --sort=-%cpu 2>/dev/null | awk 'NR>1 && NR<=12 {printf "  %-10s %-7s %-5s %-5s %s\n",$1,$2,$3,$4,$11}' || echo "  N/A"

config_item "60. iptables 규칙" "방화벽 규칙 현황"
run "iptables -L -n --line-numbers 2>/dev/null" | head -30 | \
while read -r l; do printf '  %s\n' "$l"; done

# ══════════════════════════════════════════════════════
# 네트워크 상세 (61~70)
# ══════════════════════════════════════════════════════

config_item "61. NTP 동기화 상세" "chronyc tracking + sources / ntpq -p"
if systemctl is-active chronyd &>/dev/null; then
    echo "  [ chronyc tracking ]"
    chronyc tracking 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
    echo "  [ chronyc sources ]"
    chronyc sources 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
elif systemctl is-active ntpd &>/dev/null; then
    echo "  [ ntpq -p ]"
    ntpq -p 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
else
    echo "  NTP 서비스 미실행"
fi

config_item "62. 네트워크 인터페이스 통계 (ethtool)" "속도, 듀플렉스, 링크 상태"
for iface in $(ip link show 2>/dev/null | awk -F': ' '/^[0-9]+:/{gsub(/@.*/,"",$2); print $2}' | grep -v '^lo$'); do
    printf '  [ %s ]\n' "$iface"
    ethtool "$iface" 2>/dev/null | grep -E 'Speed|Duplex|Link detected|Auto-negotiation' | \
    while read -r l; do printf '    %s\n' "$l"; done || printf '    ethtool N/A\n'
done

config_item "63. /etc/sysconfig/network" "전역 네트워크 설정"
strip_comments /etc/sysconfig/network 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "64. world-writable 디렉토리" "/tmp, /var/tmp 외 확인"
found=$(find / -xdev -type d -perm -0002 \
    -not -path '/tmp' -not -path '/var/tmp' \
    -not -path '/proc/*' -not -path '/sys/*' 2>/dev/null | head -10)
if [ -n "$found" ]; then
    echo "$found" | while read -r l; do printf '  [WARN] %s\n' "$l"; done
else
    echo "  없음 (정상)"
fi

config_item "65. 네트워크 라우팅 상세" "ip route, ip rule"
echo "  [ ip route ]"
ip route show 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
echo "  [ ip rule ]"
ip rule show 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done || echo "    N/A"

config_item "66. SELinux 전체 상태" "config + runtime 모두 확인"
printf '  config  : %s\n' "$(grep -i ^SELINUX= /etc/selinux/config 2>/dev/null || echo N/A)"
printf '  runtime : %s\n' "$(getenforce 2>/dev/null || echo N/A)"
sestatus 2>/dev/null | while read -r l; do printf '  %s\n' "$l"; done

config_item "67. /etc/sysconfig 네트워크 스크립트" "ifcfg-* 목록"
ls /etc/sysconfig/network-scripts/ifcfg-* 2>/dev/null | \
while read -r f; do printf '  %s\n' "$f"; done || echo "  N/A"

config_item "68. 커널 파라미터 전체 (주요 항목)" "sysctl -a 필터"
sysctl -a 2>/dev/null | grep -E '^(vm\.|net\.ipv4\.|kernel\.(pid_max|numa|perf|shmmax|shmall))' | \
awk '{printf "  %-45s = %s\n", $1, $3}' | head -40 || echo "  N/A"

config_item "69. 최근 부팅 이력" "last reboot"
last reboot 2>/dev/null | head -10 | while read -r l; do printf '  %s\n' "$l"; done || echo "  N/A"

config_item "70. 시스템 종합 상태" "uptime / memory / disk 요약"
echo "  [ uptime ]"
uptime 2>/dev/null | while read -r l; do printf '    %s\n' "$l"; done
echo "  [ 메모리 ]"
free -h 2>/dev/null | awk '{printf "    %-10s %-10s %-10s %-10s %-10s %s\n",$1,$2,$3,$4,$5,$6}'
echo "  [ 디스크 ]"
df -h 2>/dev/null | grep -v tmpfs | \
awk 'NR==1 {printf "    %-25s %-6s %-6s %-6s %-5s %s\n",$1,$2,$3,$4,$5,$6}
     NR>1  {printf "    %-25s %-6s %-6s %-6s %-5s %s\n",$1,$2,$3,$4,$5,$6}' | head -12

exit 0
