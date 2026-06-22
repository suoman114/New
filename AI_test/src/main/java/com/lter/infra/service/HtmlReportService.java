package com.lter.infra.service;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.repository.JobHistoryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.yaml.snakeyaml.Yaml;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class HtmlReportService {

    private final ServerService serverService;
    private final JobHistoryRepository jobHistoryRepository;
    private final SystemConfigService systemConfigService;

    // ── playbook 파일명 → 표시 이름 ──────────────────────────────────────────
    private static final Map<String, String> PLAYBOOK_NAMES = new LinkedHashMap<>();
    static {
        PLAYBOOK_NAMES.put("0_auto_pass",          "SSH 키 교환 / SELinux 비활성화");
        PLAYBOOK_NAMES.put("1_PAM_limits",          "PAM Limits 설정");
        PLAYBOOK_NAMES.put("2_systemctl_stop",      "서비스 중지 / rsyslog 설정");
        PLAYBOOK_NAMES.put("3_sysctl",              "커널 파라미터 설정 (sysctl)");
        PLAYBOOK_NAMES.put("4_ntp",                 "NTP 설치 및 설정");
        PLAYBOOK_NAMES.put("5_visudo_vcs",          "sudo 권한 설정");
        PLAYBOOK_NAMES.put("6_RMQ_vcs",             "RabbitMQ 설치 및 설정");
        PLAYBOOK_NAMES.put("7_openjdk",             "OpenJDK 1.8 설치");
        PLAYBOOK_NAMES.put("8-1_mariaDB",           "MariaDB 설치 및 DB 생성");
        PLAYBOOK_NAMES.put("8-2_mariaDB_chown",     "MariaDB 디렉토리 권한 설정");
        PLAYBOOK_NAMES.put("9-1_group_vcs",         "vcs 계정/그룹 생성");
        PLAYBOOK_NAMES.put("9-2_chmod_vcs",         "vcs 디렉토리 권한 설정");
        PLAYBOOK_NAMES.put("10-1_group_vcweb",      "vcweb 계정/그룹 생성");
        PLAYBOOK_NAMES.put("10-2_chmod_vcweb",      "vcweb 디렉토리 권한 설정");
        PLAYBOOK_NAMES.put("11_vcs_dic",            "VCS 패키지 배포 및 설치");
        PLAYBOOK_NAMES.put("12_Cron_root",          "헬스체크 Cron 등록");
        PLAYBOOK_NAMES.put("13_service_start",      "서비스 init.d 등록");
        PLAYBOOK_NAMES.put("14_ramdisk",            "Ramdisk 마운트 설정");
        PLAYBOOK_NAMES.put("15_ldconf",             "ld.so 설정");
        PLAYBOOK_NAMES.put("15_rclocal",            "rc.local 설정 (ring buffer / iptables)");
        PLAYBOOK_NAMES.put("16_watermark",          "Watermark 파일 복사");
    }

    public String generateReport(Long serverId, String phase) {
        return generateReport(serverId, phase, null);
    }

    public String generateReport(Long serverId, String phase, LocalDate selectedDate) {
        TargetServer server = serverService.findById(serverId);
        List<ReportItem>  items;
        List<LocalDate>   validationDates = Collections.emptyList();
        String phaseTitle;
        String phaseSubtitle;
        String nextStep;

        switch (phase) {
            case "os":
                phaseTitle    = "OS 셋업 보고서";
                phaseSubtitle = "OS Setup Report";
                nextStep      = "PKG 설치를 진행하십시오.";
                items         = buildOsItems(serverId);
                break;
            case "pkg":
                phaseTitle    = "PKG 설치 보고서";
                phaseSubtitle = "Package Setup Report";
                nextStep      = "설치 검증을 진행하십시오.";
                items         = buildPkgItems(serverId);
                break;
            case "validation":
                phaseTitle      = "설치 검증 보고서";
                phaseSubtitle   = "Validation Report";
                nextStep        = "모든 설치 및 검증이 완료되었습니다.";
                validationDates = jobHistoryRepository
                        .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                                serverId, JobHistory.JobType.VALIDATION)
                        .stream()
                        .filter(j -> j.getStartedAt() != null)
                        .map(j -> j.getStartedAt().toLocalDate())
                        .distinct()
                        .sorted(Comparator.reverseOrder())
                        .collect(Collectors.toList());
                items           = buildValidationItems(serverId, selectedDate);
                break;
            default:
                throw new IllegalArgumentException("지원하지 않는 phase: " + phase);
        }

        return buildHtml(server, phaseTitle, phaseSubtitle, phase, nextStep, items,
                validationDates, selectedDate);
    }

    // ── 내부 DTO ──────────────────────────────────────────────────────────────

    static class ReportItem {
        final String name;
        final String status;   // "OK", "COK", "NOK", "SKIP"
        final String detail;   // '\n' 구분 다중 행

        ReportItem(String name, String status, String detail) {
            this.name   = name;
            this.status = status;
            this.detail = detail;
        }
    }

    // ── Phase별 항목 구성 ──────────────────────────────────────────────────────

    private List<ReportItem> buildOsItems(Long serverId) {
        List<JobHistory> jobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.OS_SETUP, PageRequest.of(0, 50)).getContent();
        return toJobReportItems(jobs);
    }

    private List<ReportItem> buildPkgItems(Long serverId) {
        List<JobHistory> setupJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.PKG_SETUP, PageRequest.of(0, 50)).getContent();
        List<JobHistory> deployJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.PKG_DEPLOY, PageRequest.of(0, 50)).getContent();
        List<JobHistory> all = new ArrayList<>();
        all.addAll(setupJobs);
        all.addAll(deployJobs);
        all.sort((a, b) -> b.getStartedAt() != null && a.getStartedAt() != null
                ? b.getStartedAt().compareTo(a.getStartedAt()) : 0);
        return toJobReportItems(all);
    }

    /** playbook별 최신 1건만 남겨 ReportItem 변환 (상세는 YAML 파싱) */
    private List<ReportItem> toJobReportItems(List<JobHistory> jobs) {
        Map<String, JobHistory> latest = new LinkedHashMap<>();
        for (JobHistory job : jobs) {
            String key = job.getPlaybookName() != null ? job.getPlaybookName() : "unknown";
            latest.putIfAbsent(key, job);
        }

        String playbookDir = "";
        try {
            playbookDir = systemConfigService.get(InfraConfig.ANSIBLE_PLAYBOOK_DIR);
        } catch (Exception e) {
            log.warn("playbook-dir 설정을 읽을 수 없습니다: {}", e.getMessage());
        }

        List<ReportItem> result = new ArrayList<>();
        for (JobHistory job : latest.values()) {
            String pbName  = job.getPlaybookName() != null ? job.getPlaybookName() : "unknown";
            // DB에 .yml 확장자 포함 저장된 경우 제거 후 매핑
            String pbKey   = pbName.endsWith(".yml") ? pbName.substring(0, pbName.length() - 4) : pbName;
            String display = PLAYBOOK_NAMES.getOrDefault(pbKey, pbName);
            String status  = mapJobStatus(job.getStatus());
            String detail  = buildDetailFromYaml(playbookDir, pbName, job, status);
            result.add(new ReportItem(display, status, detail));
        }
        return result;
    }

    /**
     * YAML 파싱으로 task 파라미터 추출.
     * NOK 시에는 stderr 첫 줄을 앞에 추가.
     */
    private String buildDetailFromYaml(String playbookDir, String pbName,
                                       JobHistory job, String status) {
        String yamlDetail = extractPlaybookDetail(playbookDir, pbName);

        if ("NOK".equals(status) && job.getStdErr() != null
                && !job.getStdErr().trim().isEmpty()) {
            String firstErr = job.getStdErr().trim().split("\n")[0];
            String errLine  = "[ERROR] " + (firstErr.length() > 120
                    ? firstErr.substring(0, 120) + "..." : firstErr);
            return yamlDetail.isEmpty() ? errLine : errLine + "\n" + yamlDetail;
        }

        return yamlDetail;
    }

    /** SnakeYAML로 playbook 파일 파싱 → 의미있는 task 정보 추출 */
    @SuppressWarnings("unchecked")
    private String extractPlaybookDetail(String playbookDir, String pbName) {
        if (playbookDir == null || playbookDir.isEmpty() || pbName == null) return "";

        String baseName  = pbName.endsWith(".yml") ? pbName.substring(0, pbName.length() - 4) : pbName;
        File   file      = new File(playbookDir.replaceAll("/+$", "") + "/" + baseName + ".yml");
        if (!file.exists()) {
            log.debug("playbook 파일 없음: {}", file.getAbsolutePath());
            return "";
        }

        try (InputStream is = new FileInputStream(file)) {
            Yaml           yaml  = new Yaml();
            Object         loaded = yaml.load(is);
            if (!(loaded instanceof List)) return "";

            List<Object>   plays = (List<Object>) loaded;
            List<String>   lines = new ArrayList<>();

            for (Object playObj : plays) {
                if (!(playObj instanceof Map)) continue;
                Map<String, Object> play     = (Map<String, Object>) playObj;
                Object              tasksObj = play.get("tasks");
                if (!(tasksObj instanceof List)) continue;

                for (Object taskObj : (List<Object>) tasksObj) {
                    if (!(taskObj instanceof Map)) continue;
                    String line = formatTask((Map<String, Object>) taskObj);
                    if (line != null && !line.isEmpty()) {
                        lines.add(line);
                    }
                }
            }
            return String.join("\n", lines);
        } catch (Exception e) {
            log.warn("playbook YAML 파싱 실패 [{}]: {}", pbName, e.getMessage());
            return "";
        }
    }

    /** task Map → 한 줄 설명 문자열. null 반환 시 출력 생략. */
    @SuppressWarnings("unchecked")
    private String formatTask(Map<String, Object> task) {
        // 출력 생략 모듈
        if (hasKey(task, "debug", "set_fact", "find", "register")) return null;

        if (task.containsKey("pam_limits")) {
            Map<String, Object> m = asMap(task.get("pam_limits"));
            return m.get("domain") + " " + m.get("limit_type") + " " + m.get("limit_item") + "=" + m.get("value");
        }

        if (task.containsKey("sysctl")) {
            Map<String, Object> m = asMap(task.get("sysctl"));
            return m.get("name") + "=" + m.get("value");
        }

        if (task.containsKey("systemd")) {
            Map<String, Object> m = asMap(task.get("systemd"));
            StringBuilder sb = new StringBuilder();
            if (m.get("name")    != null) sb.append(m.get("name")).append(": ");
            if (m.get("state")   != null) sb.append("state=").append(m.get("state"));
            if (m.get("enabled") != null) sb.append(", enabled=").append(m.get("enabled"));
            return sb.toString();
        }

        if (task.containsKey("lineinfile")) {
            Map<String, Object> m = asMap(task.get("lineinfile"));
            String path   = str(m.get("path"));
            String line   = str(m.get("line"));
            String regexp = str(m.get("regexp"));
            String state  = str(m.get("state"));
            if ("absent".equals(state) && regexp != null) {
                return path + ": remove /" + trunc(regexp, 50) + "/";
            }
            if (line != null) return path + ": +" + trunc(line, 70);
            return path;
        }

        if (task.containsKey("replace")) {
            Map<String, Object> m = asMap(task.get("replace"));
            return m.get("path") + ": " + trunc(str(m.get("regexp")), 40) + " → " + trunc(str(m.get("replace")), 40);
        }

        if (task.containsKey("blockinfile")) {
            Map<String, Object> m = asMap(task.get("blockinfile"));
            return m.get("path") + ": +block";
        }

        if (task.containsKey("yum")) {
            Map<String, Object> m = asMap(task.get("yum"));
            String name  = str(m.get("name"));
            String state = str(m.get("state"));
            if ("absent".equals(state)) return "yum remove: " + name;
            return "yum install: " + trunc(name, 60);
        }

        if (task.containsKey("copy")) {
            Map<String, Object> m = asMap(task.get("copy"));
            String src  = trunc(str(m.get("src")), 50);
            String dest = trunc(str(m.get("dest")), 40);
            String mode = str(m.get("mode"));
            return "copy: " + src + " → " + dest + (mode != null ? " (mode=" + mode + ")" : "");
        }

        if (task.containsKey("unarchive")) {
            Map<String, Object> m = asMap(task.get("unarchive"));
            return "unarchive: " + trunc(str(m.get("src")), 50) + " → " + str(m.get("dest"));
        }

        if (task.containsKey("file")) {
            Map<String, Object> m = asMap(task.get("file"));
            StringBuilder sb = new StringBuilder("file: ").append(m.get("path"));
            if (m.get("owner") != null) sb.append("  owner=").append(m.get("owner"));
            if (m.get("group") != null) sb.append(" group=").append(m.get("group"));
            if (m.get("mode")  != null) sb.append(" mode=").append(m.get("mode"));
            return sb.toString();
        }

        if (task.containsKey("mount")) {
            Map<String, Object> m = asMap(task.get("mount"));
            return "mount: " + m.get("src") + " → " + m.get("name")
                    + " (" + m.get("fstype") + ", " + m.get("opts") + ")";
        }

        if (task.containsKey("cron")) {
            Map<String, Object> m = asMap(task.get("cron"));
            return "cron: " + m.get("name") + "  →  " + trunc(str(m.get("job")), 60);
        }

        if (task.containsKey("selinux")) {
            Map<String, Object> m = asMap(task.get("selinux"));
            return "SELinux: state=" + m.get("state");
        }

        if (task.containsKey("timezone")) {
            Map<String, Object> m = asMap(task.get("timezone"));
            return "timezone: " + m.get("name");
        }

        if (task.containsKey("authorized_key")) {
            Map<String, Object> m = asMap(task.get("authorized_key"));
            return "authorized_key: user=" + m.get("user") + "  state=" + m.get("state");
        }

        if (task.containsKey("group")) {
            Map<String, Object> m = asMap(task.get("group"));
            return "group: " + m.get("name") + "  gid=" + m.get("gid") + "  state=" + m.get("state");
        }

        if (task.containsKey("user")) {
            Map<String, Object> m = asMap(task.get("user"));
            return "user: " + m.get("name") + "  group=" + m.get("group") + "  state=" + m.get("state");
        }

        if (task.containsKey("shell")) {
            Object cmd = task.get("shell");
            String s   = cmd instanceof String ? (String) cmd : String.valueOf(cmd);
            return "$ " + trunc(s.trim(), 80);
        }

        if (task.containsKey("command")) {
            return "$ " + trunc(String.valueOf(task.get("command")).trim(), 80);
        }

        if (task.containsKey("mysql_db")) {
            Map<String, Object> m = asMap(task.get("mysql_db"));
            return "mysql db: " + m.get("name") + "  (" + m.get("state") + ")";
        }

        if (task.containsKey("mysql_user")) {
            Map<String, Object> m = asMap(task.get("mysql_user"));
            return "mysql user: " + m.get("name") + "  priv=" + m.get("priv");
        }

        if (task.containsKey("rabbitmq_user")) {
            Map<String, Object> m = asMap(task.get("rabbitmq_user"));
            return "rmq user: " + m.get("user");
        }

        if (task.containsKey("rabbitmq_plugin")) {
            Map<String, Object> m = asMap(task.get("rabbitmq_plugin"));
            return "rmq plugins: " + m.get("names");
        }

        // 처리되지 않은 모듈 - task name이 있으면 그것만
        String name = str(task.get("name"));
        return name;
    }

    /**
     * 스크립트별(playbookName) 최신 1건만 추출 후 섹션 헤더로 구분하여 합산.
     * date 지정 시 해당 날짜 범위의 job만 조회, null이면 최신 50건.
     * os_audit 포맷(===CONFIG:===) 감지 시 별도 파서 사용, 나머지는 태그 기반 파서.
     */
    private List<ReportItem> buildValidationItems(Long serverId, LocalDate date) {
        List<JobHistory> jobs;
        if (date != null) {
            jobs = jobHistoryRepository.findByTargetServerIdAndJobTypeAndStartedAtBetweenOrderByStartedAtDesc(
                    serverId, JobHistory.JobType.VALIDATION,
                    date.atStartOfDay(), date.plusDays(1).atStartOfDay());
        } else {
            jobs = jobHistoryRepository.findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                    serverId, JobHistory.JobType.VALIDATION, PageRequest.of(0, 50)).getContent();
        }

        // 스크립트명 기준 최신 1건만 유지 (삽입 순서 = 최신순)
        Map<String, JobHistory> latestByScript = new LinkedHashMap<>();
        for (JobHistory job : jobs) {
            String key = job.getPlaybookName() != null ? job.getPlaybookName() : "unknown";
            latestByScript.putIfAbsent(key, job);
        }

        List<ReportItem> allItems = new ArrayList<>();

        for (Map.Entry<String, JobHistory> entry : latestByScript.entrySet()) {
            String     scriptName = entry.getKey();
            JobHistory job        = entry.getValue();

            if (job.getStdOut() == null || job.getStdOut().isEmpty()) continue;

            List<ReportItem> scriptItems = job.getStdOut().contains("===CONFIG:")
                    ? parseOsAuditFormat(job.getStdOut())
                    : parseLegacyFormat(job.getStdOut());

            if (scriptItems.isEmpty()) continue;

            // 섹션 헤더: name=스크립트명, detail=실행시각
            String runAt = job.getStartedAt() != null
                    ? job.getStartedAt().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"))
                    : "-";
            allItems.add(new ReportItem(scriptName, "SECTION", runAt));
            allItems.addAll(scriptItems);
        }

        return allItems;
    }

    /** 기존 태그 기반 포맷 파싱 (verify_vcs_install.sh 등) */
    private List<ReportItem> parseLegacyFormat(String stdOut) {
        List<ReportItem> items    = new ArrayList<>();
        List<String>     dismcBuf = new ArrayList<>();

        for (String line : stdOut.split("\n")) {
            String t = line.trim();
            if (t.isEmpty()) continue;

            if (t.startsWith(">>>")) {
                dismcBuf.add(t.substring(3));
                continue;
            }

            if (t.startsWith(">>") && !items.isEmpty()) {
                String     append    = t.substring(2);
                ReportItem last      = items.remove(items.size() - 1);
                String     newDetail = last.detail.isEmpty() ? append : last.detail + "\n" + append;
                items.add(new ReportItem(last.name, last.status, newDetail));
                continue;
            }

            if (!dismcBuf.isEmpty() && !items.isEmpty()) {
                String html = formatDismcAsHtml(dismcBuf);
                dismcBuf.clear();
                if (html != null) {
                    ReportItem last = items.remove(items.size() - 1);
                    items.add(new ReportItem(last.name, last.status, "__HTML__" + html));
                }
            }

            String status = null;
            if      (t.contains("[OK]"))   status = "OK";
            else if (t.contains("[WARN]")) status = "COK";
            else if (t.contains("[MISS]")) status = "COK";
            else if (t.contains("[FAIL]")) status = "NOK";
            if (status != null) {
                String detail = t.replaceAll("\\[OK\\]|\\[WARN\\]|\\[MISS\\]|\\[FAIL\\]", "").trim();
                String name   = detail.length() > 60 ? detail.substring(0, 60) + "..." : detail;
                items.add(new ReportItem(name, status, detail));
            }
        }

        if (!dismcBuf.isEmpty() && !items.isEmpty()) {
            String html = formatDismcAsHtml(dismcBuf);
            if (html != null) {
                ReportItem last = items.remove(items.size() - 1);
                items.add(new ReportItem(last.name, last.status, "__HTML__" + html));
            }
        }

        return items;
    }

    /**
     * os_audit.sh 출력 파싱.
     * ===CONFIG:항목명=== / GUIDE:... / RESULT: 블록 구조를 ReportItem으로 변환.
     * 항목 내 태그 집계: [FAIL] → NOK, [WARN]/[MISS] → COK, [OK]만 있으면 → OK, 태그 없으면 → SKIP.
     */
    private List<ReportItem> parseOsAuditFormat(String stdOut) {
        List<ReportItem> items   = new ArrayList<>();
        String           name    = null;
        boolean          inResult = false;
        int              ok = 0, warn = 0, miss = 0, fail = 0;
        List<String>     detail  = new ArrayList<>();

        for (String line : stdOut.split("\n")) {
            String t = line.trim();

            // 섹션 구분자는 무시
            if (t.startsWith("===SECTION:")) {
                inResult = false;
                continue;
            }

            if (t.startsWith("===CONFIG:")) {
                // 이전 항목 flush
                if (name != null) {
                    items.add(new ReportItem(name, resolveAuditStatus(ok, warn, miss, fail),
                            String.join("\n", detail)));
                }
                name     = t.replace("===CONFIG:", "").replace("===", "").trim()
                                .replaceFirst("^[\\d.]+\\s+", "");
                inResult = false;
                ok = warn = miss = fail = 0;
                detail   = new ArrayList<>();
                continue;
            }

            if (t.startsWith("GUIDE:")) continue;

            if (t.equals("RESULT:")) {
                inResult = true;
                continue;
            }

            if (inResult && name != null) {
                if (t.contains("[OK]"))   ok++;
                if (t.contains("[WARN]")) warn++;
                if (t.contains("[MISS]")) miss++;
                if (t.contains("[FAIL]")) fail++;
                detail.add(line);
            }
        }

        // 마지막 항목 flush
        if (name != null) {
            items.add(new ReportItem(name, resolveAuditStatus(ok, warn, miss, fail),
                    String.join("\n", detail)));
        }
        return items;
    }

    /** os_audit 항목별 태그 집계 → 상태 결정 */
    private String resolveAuditStatus(int ok, int warn, int miss, int fail) {
        if (fail > 0)             return "NOK";
        if (warn > 0 || miss > 0) return "COK";
        if (ok   > 0)             return "OK";
        return "SKIP";
    }

    /**
     * dismc 출력 줄 목록 → HTML 테이블.
     * 헤더: Process PID STATUS CPU MEM FD TRD QKEY QCNT START_TIME IC GRP
     * ALIVE 행 녹색, DEAD 행 회색, TOTAL 라인은 footer에 표시.
     */
    private String formatDismcAsHtml(List<String> lines) {
        final String[] COLS = {"Process","PID","STATUS","CPU","MEM","FD","TRD","QKEY","QCNT","START_TIME","IC","GRP"};
        List<String[]> rows = new ArrayList<>();
        String totalLine = null;
        boolean headerPassed = false;

        for (String line : lines) {
            String t = line.trim();
            if (t.isEmpty() || t.startsWith("=") || t.startsWith("-")) continue;
            if (t.startsWith("stty:") || t.contains(".bashrc:"))       continue;
            if (t.startsWith("TOTAL:"))                                 { totalLine = t; continue; }
            if (t.contains("Process") && t.contains("STATUS"))         { headerPassed = true; continue; }
            if (headerPassed) rows.add(t.split("\\s+"));
        }

        if (rows.isEmpty()) return null;

        StringBuilder html = new StringBuilder();
        html.append("<table class=\"dismc-table\"><thead><tr>");
        for (String c : COLS) html.append("<th>").append(c).append("</th>");
        html.append("</tr></thead><tbody>");

        for (String[] p : rows) {
            String status  = p.length > 2 ? p[2] : "DEAD";
            String rowCls  = "ALIVE".equals(status) ? "dismc-alive" : "dismc-dead";
            html.append("<tr class=\"").append(rowCls).append("\">");
            for (int i = 0; i < COLS.length; i++) {
                String val = i < p.length ? esc(p[i]) : "-";
                if (i == 2) {
                    String sc = "ALIVE".equals(status) ? "dismc-s-alive" : "dismc-s-dead";
                    val = "<span class=\"" + sc + "\">" + val + "</span>";
                }
                html.append("<td>").append(val).append("</td>");
            }
            html.append("</tr>");
        }
        html.append("</tbody>");

        if (totalLine != null) {
            html.append("<tfoot><tr><td colspan=\"").append(COLS.length)
                .append("\" class=\"dismc-total\">").append(esc(totalLine))
                .append("</td></tr></tfoot>");
        }
        html.append("</table>");
        return html.toString();
    }

    /** detail 렌더링: "__HTML__" 접두어이면 이스케이프 없이 raw HTML 출력, 아니면 escMultiLine */
    private static String renderDetail(String detail) {
        if (detail == null || detail.isEmpty()) return "";
        if (detail.startsWith("__HTML__")) return detail.substring(8);
        return escMultiLine(detail);
    }

    private String mapJobStatus(JobHistory.JobStatus status) {
        if (status == null) return "SKIP";
        switch (status) {
            case SUCCESS: return "OK";
            case FAIL:    return "NOK";
            case RUNNING: return "COK";
            default:      return "SKIP";
        }
    }

    // ── 유틸 ──────────────────────────────────────────────────────────────────

    private boolean hasKey(Map<String, Object> map, String... keys) {
        for (String k : keys) if (map.containsKey(k)) return true;
        return false;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object o) {
        if (o instanceof Map) return (Map<String, Object>) o;
        return Collections.emptyMap();
    }

    private String str(Object o) {
        return o != null ? String.valueOf(o) : null;
    }

    private String trunc(String s, int max) {
        if (s == null) return "";
        return s.length() > max ? s.substring(0, max) + "…" : s;
    }

    // ── HTML 생성 ──────────────────────────────────────────────────────────────

    private String buildHtml(TargetServer server, String phaseTitle, String phaseSubtitle,
                             String phase, String nextStep, List<ReportItem> items,
                             List<LocalDate> validationDates, LocalDate selectedDate) {
        // SECTION 헤더는 통계 집계에서 제외
        long total     = items.stream().filter(i -> !"SECTION".equals(i.status)).count();
        long okCount   = items.stream().filter(i -> "OK".equals(i.status)).count();
        long cokCount  = items.stream().filter(i -> "COK".equals(i.status)).count();
        long nokCount  = items.stream().filter(i -> "NOK".equals(i.status)).count();
        long skipCount = items.stream().filter(i -> "SKIP".equals(i.status)).count();

        String now = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));

        String alertClass, alertMsg;
        if (nokCount > 0) {
            alertClass = "alert-danger";
            alertMsg   = "<strong>&#x2715; 이상 감지</strong><br>NOK 항목이 있습니다. 상세 결과를 확인하십시오.";
        } else if (cokCount > 0) {
            alertClass = "alert-warning";
            alertMsg   = "<strong>&#x26A0; 주의</strong><br>확인이 필요한 항목이 있습니다.";
        } else {
            alertClass = "alert-success";
            alertMsg   = "<strong>&#x2713; 양호</strong><br>모든 항목이 정상입니다. 다음 단계를 진행할 수 있습니다.";
        }

        StringBuilder sb = new StringBuilder();

        sb.append("<!DOCTYPE html>\n<html lang=\"ko\">\n<head>\n");
        sb.append("    <meta charset=\"UTF-8\">\n");
        sb.append("    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n");
        sb.append("    <title>LTER Infra ").append(esc(phaseTitle)).append("</title>\n");
        sb.append(CSS);
        sb.append("</head>\n<body>\n<div class=\"container\">\n\n");

        // Header
        sb.append("    <div class=\"header\">\n");
        sb.append("        <h1>LTER Infra ").append(esc(phaseTitle)).append("</h1>\n");
        sb.append("        <p>").append(esc(phaseSubtitle)).append(" - ").append(esc(server.getServerName())).append("</p>\n");
        sb.append("    </div>\n\n");

        // 날짜 드롭다운 (validation 전용)
        if ("validation".equals(phase) && validationDates != null && !validationDates.isEmpty()) {
            String baseUrl = "/api/v1/report/" + server.getId() + "/html/validation";
            String curVal  = selectedDate != null ? selectedDate.toString() : "";
            sb.append("    <div class=\"date-selector\">\n");
            sb.append("        <label for=\"dateSelect\">&#x1F4C5; 날짜 선택</label>\n");
            sb.append("        <select id=\"dateSelect\" onchange=\"location.href='")
              .append(baseUrl).append("?date='+this.value\">\n");
            sb.append("            <option value=\"\"").append(curVal.isEmpty() ? " selected" : "").append(">최신 결과</option>\n");
            for (LocalDate d : validationDates) {
                String dStr = d.toString();
                sb.append("            <option value=\"").append(dStr).append("\"")
                  .append(dStr.equals(curVal) ? " selected" : "").append(">")
                  .append(dStr).append("</option>\n");
            }
            sb.append("        </select>\n");
            sb.append("    </div>\n\n");
        }

        // Dashboard
        long pOk   = total > 0 ? okCount   * 100 / total : 0;
        long pCok  = total > 0 ? cokCount  * 100 / total : 0;
        long pNok  = total > 0 ? nokCount  * 100 / total : 0;
        long pSkip = total > 0 ? skipCount * 100 / total : 0;
        sb.append("    <div class=\"dashboard\">\n");
        sb.append("        <div class=\"stat-card\"><h3>전체</h3><div class=\"number\">").append(total).append("</div><p>Total Items</p></div>\n");
        sb.append("        <div class=\"stat-card ok\"><h3>OK</h3><div class=\"number\">").append(okCount).append("</div><div class=\"percent\">").append(pOk).append("%</div></div>\n");
        sb.append("        <div class=\"stat-card cok\"><h3>COK</h3><div class=\"number\">").append(cokCount).append("</div><div class=\"percent\">").append(pCok).append("%</div></div>\n");
        sb.append("        <div class=\"stat-card nok\"><h3>NOK</h3><div class=\"number\">").append(nokCount).append("</div><div class=\"percent\">").append(pNok).append("%</div></div>\n");
        sb.append("        <div class=\"stat-card skip\"><h3>SKIP</h3><div class=\"number\">").append(skipCount).append("</div><div class=\"percent\">").append(pSkip).append("%</div></div>\n");
        sb.append("    </div>\n\n");

        // Status alert
        sb.append("    <div class=\"alert ").append(alertClass).append("\">").append(alertMsg).append("</div>\n\n");

        // 기본 정보
        sb.append("    <div class=\"section\">\n");
        sb.append("        <h2 class=\"section-title\">기본 정보</h2>\n");
        sb.append("        <table class=\"info-table\">\n");
        sb.append("            <tr><td>서버명</td><td>").append(esc(server.getServerName())).append("</td></tr>\n");
        sb.append("            <tr><td>IP 주소</td><td>").append(esc(server.getIpAddress())).append("</td></tr>\n");
        String osStr = server.getOsType().name()
                + (server.getOsVersion() != null ? " " + server.getOsVersion() : "");
        sb.append("            <tr><td>OS</td><td>").append(esc(osStr)).append("</td></tr>\n");
        if (server.getKernelVersion() != null)
            sb.append("            <tr><td>Kernel</td><td>").append(esc(server.getKernelVersion())).append("</td></tr>\n");
        if (server.getCpuInfo() != null)
            sb.append("            <tr><td>CPU</td><td>").append(esc(server.getCpuInfo())).append("</td></tr>\n");
        if (server.getMemoryGb() != null)
            sb.append("            <tr><td>Memory</td><td>").append(esc(server.getMemoryGb())).append("</td></tr>\n");
        if (server.getDiskRootGb() != null)
            sb.append("            <tr><td>Disk (/)</td><td>").append(esc(server.getDiskRootGb())).append("</td></tr>\n");
        sb.append("            <tr><td>보고서 생성일시</td><td>").append(now).append("</td></tr>\n");
        sb.append("        </table>\n");
        sb.append("    </div>\n\n");

        // 상세 검사 결과
        sb.append("    <div class=\"section\">\n");
        sb.append("        <h2 class=\"section-title\">상세 검사 결과</h2>\n");
        if (items.isEmpty()) {
            sb.append("        <div class=\"alert alert-info\">이 Phase에 해당하는 실행 이력이 없습니다.</div>\n");
        } else {
            sb.append("        <table class=\"result-table\">\n");
            sb.append("            <thead><tr><th>No</th><th>항목</th><th>상태</th><th>상세</th></tr></thead>\n");
            sb.append("            <tbody>\n");
            int no = 1;
            for (ReportItem item : items) {
                if ("SECTION".equals(item.status)) {
                    sb.append("                <tr class=\"section-header-row\">\n");
                    sb.append("                    <td colspan=\"4\">")
                      .append("<span class=\"section-script-name\">").append(esc(item.name)).append("</span>")
                      .append("<span class=\"section-run-at\">실행: ").append(esc(item.detail)).append("</span>")
                      .append("</td>\n");
                    sb.append("                </tr>\n");
                    continue;
                }
                sb.append("                <tr>\n");
                sb.append("                    <td>").append(no++).append("</td>\n");
                sb.append("                    <td>").append(esc(item.name)).append("</td>\n");
                sb.append("                    <td><span class=\"status-").append(item.status.toLowerCase())
                  .append("\">").append(esc(item.status)).append("</span></td>\n");
                sb.append("                    <td>").append(renderDetail(item.detail)).append("</td>\n");
                sb.append("                </tr>\n");
            }
            sb.append("            </tbody>\n");
            sb.append("        </table>\n");
        }
        sb.append("    </div>\n\n");

        // 특이사항
        sb.append("    <div class=\"section\">\n");
        sb.append("        <h2 class=\"section-title\">특이사항</h2>\n");
        List<ReportItem> nokItems = items.stream()
                .filter(i -> "NOK".equals(i.status)).collect(Collectors.toList());
        if (nokItems.isEmpty()) {
            sb.append("        <div class=\"alert alert-success\"><strong>&#x2713; NOK 항목 없음</strong><br>NOK 상태의 항목이 없습니다.</div>\n");
        } else {
            sb.append("        <div class=\"alert alert-danger\"><strong>&#x2715; NOK 항목 목록</strong></div>\n");
            sb.append("        <ul class=\"nok-list\">\n");
            for (ReportItem item : nokItems) {
                sb.append("            <li><strong>").append(esc(item.name)).append("</strong>\n");
                sb.append("                <div class=\"detail\">").append(renderDetail(item.detail)).append("</div></li>\n");
            }
            sb.append("        </ul>\n");
        }
        sb.append("    </div>\n\n");

        // 다음 단계
        boolean allOk     = nokCount == 0;
        String  stepBg    = allOk ? "#d4edda" : "#f8d7da";
        String  stepBorder= allOk ? "#11998e" : "#721c24";
        String  stepColor = allOk ? "#155724" : "#721c24";
        sb.append("    <div class=\"section\">\n");
        sb.append("        <h2 class=\"section-title\">다음 단계</h2>\n");
        sb.append("        <div class=\"next-steps\" style=\"background-color:").append(stepBg)
          .append("; border-left-color:").append(stepBorder).append(";\">\n");
        if (allOk) {
            sb.append("            <h3 style=\"color:").append(stepColor).append(";\">&#x2713; 완료</h3>\n");
            sb.append("            <p style=\"color:").append(stepColor).append(";\">").append(esc(nextStep)).append("</p>\n");
        } else {
            sb.append("            <h3 style=\"color:").append(stepColor).append(";\">&#x2715; NOK 항목 조치 필요</h3>\n");
            sb.append("            <p style=\"color:").append(stepColor).append(";\">NOK 항목을 먼저 해결 후 다음 단계를 진행하십시오.</p>\n");
        }
        sb.append("        </div>\n");
        sb.append("    </div>\n\n");

        // Footer
        sb.append("    <div class=\"footer\">\n");
        sb.append("        <hr style=\"margin-bottom:20px;\">\n");
        sb.append("        <p><strong>보고서 생성 정보</strong></p>\n");
        sb.append("        <p>생성 일시: ").append(now).append("</p>\n");
        sb.append("        <p>생성 대상: ").append(esc(server.getServerName()))
          .append(" (").append(esc(server.getIpAddress())).append(")</p>\n");
        sb.append("        <p>Phase: ").append(esc(phase)).append("</p>\n");
        sb.append("        <hr style=\"margin:15px 0;\">\n");
        sb.append("        <p style=\"margin-top:20px; font-style:italic;\">")
          .append("이 보고서는 <strong>LTER Infra 자동화 도구</strong>에 의해 자동으로 생성되었습니다.</p>\n");
        sb.append("    </div>\n\n");

        sb.append("</div>\n</body>\n</html>");
        return sb.toString();
    }

    private static String esc(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    /** '\n' 구분 문자열을 <br> 태그로 변환하여 렌더링 */
    private static String escMultiLine(String s) {
        if (s == null || s.isEmpty()) return "";
        String[] lines = s.split("\n");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < lines.length; i++) {
            if (i > 0) sb.append("<br>");
            sb.append(esc(lines[i]));
        }
        return sb.toString();
    }

    // ── CSS ───────────────────────────────────────────────────────────────────

    private static final String CSS =
        "    <style>\n" +
        "        * { margin: 0; padding: 0; box-sizing: border-box; }\n" +
        "        body {\n" +
        "            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif, '나눔고딕', '돋움';\n" +
        "            color: #333; background-color: #f5f5f5; line-height: 1.6; padding: 20px;\n" +
        "        }\n" +
        "        .container {\n" +
        "            max-width: 1200px; margin: 0 auto; background-color: white;\n" +
        "            padding: 40px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);\n" +
        "        }\n" +
        "        .header {\n" +
        "            text-align: center; border-bottom: 3px solid #2c3e50;\n" +
        "            padding-bottom: 30px; margin-bottom: 40px;\n" +
        "        }\n" +
        "        .header h1 { font-size: 32px; color: #2c3e50; margin-bottom: 10px; font-weight: 700; }\n" +
        "        .header p  { color: #7f8c8d; font-size: 14px; }\n" +
        "        .dashboard {\n" +
        "            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));\n" +
        "            gap: 20px; margin-bottom: 40px;\n" +
        "        }\n" +
        "        .stat-card {\n" +
        "            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);\n" +
        "            color: white; padding: 25px; border-radius: 8px;\n" +
        "            text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);\n" +
        "        }\n" +
        "        .stat-card.ok   { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }\n" +
        "        .stat-card.cok  { background: linear-gradient(135deg, #4fc3f7 0%, #29b6f6 100%); color: white; }\n" +
        "        .stat-card.nok  { background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%); }\n" +
        "        .stat-card.skip { background: linear-gradient(135deg, #909090 0%, #c0c0c0 100%); }\n" +
        "        .stat-card h3 {\n" +
        "            font-size: 14px; font-weight: 500; margin-bottom: 10px;\n" +
        "            opacity: 0.9; text-transform: uppercase; letter-spacing: 1px;\n" +
        "        }\n" +
        "        .stat-card .number { font-size: 48px; font-weight: 700; line-height: 1; }\n" +
        "        .stat-card .percent { font-size: 14px; margin-top: 5px; opacity: 0.8; }\n" +
        "        .section { margin-bottom: 40px; }\n" +
        "        .section-title {\n" +
        "            font-size: 24px; color: #2c3e50; margin-bottom: 20px;\n" +
        "            padding-bottom: 10px; border-bottom: 2px solid #3498db; font-weight: 600;\n" +
        "        }\n" +
        "        .result-table {\n" +
        "            width: 100%; border-collapse: collapse; margin-bottom: 20px;\n" +
        "            box-shadow: 0 1px 3px rgba(0,0,0,0.1); table-layout: fixed;\n" +
        "        }\n" +
        "        .result-table th {\n" +
        "            background-color: #34495e; color: white; padding: 15px; text-align: left;\n" +
        "            font-weight: 600; font-size: 13px; letter-spacing: 0.5px; text-transform: uppercase;\n" +
        "        }\n" +
        "        .result-table td {\n" +
        "            padding: 12px 15px; border-bottom: 1px solid #ecf0f1;\n" +
        "            vertical-align: top; word-wrap: break-word; overflow-wrap: break-word;\n" +
        "        }\n" +
        "        .result-table tr:hover { background-color: #f8f9fa; }\n" +
        "        .result-table tr:last-child td { border-bottom: none; }\n" +
        "        .result-table th:nth-child(1), .result-table td:nth-child(1) { width: 5%;  text-align: center; }\n" +
        "        .result-table th:nth-child(2), .result-table td:nth-child(2) { width: 28%; }\n" +
        "        .result-table th:nth-child(3), .result-table td:nth-child(3) { width: 9%;  text-align: center; }\n" +
        "        .result-table th:nth-child(4), .result-table td:nth-child(4) { width: 58%; font-size: 13px; line-height: 1.7; }\n" +
        "        .status-ok   { background-color: #d4edda; color: #155724; font-weight: 600; padding: 6px 12px; border-radius: 4px; display: inline-block; }\n" +
        "        .status-cok  { background-color: #d1ecf1; color: #0c5460; font-weight: 600; padding: 6px 12px; border-radius: 4px; display: inline-block; }\n" +
        "        .status-nok  { background-color: #f8d7da; color: #721c24; font-weight: 600; padding: 6px 12px; border-radius: 4px; display: inline-block; }\n" +
        "        .status-skip { background-color: #e2e3e5; color: #383d41; font-weight: 600; padding: 6px 12px; border-radius: 4px; display: inline-block; }\n" +
        "        .section-header-row td { background-color: #2c3e50; padding: 10px 15px; border-bottom: none; }\n" +
        "        .section-script-name { color: #ecf0f1; font-weight: 700; font-size: 14px; margin-right: 16px; }\n" +
        "        .section-run-at { color: #95a5a6; font-size: 12px; }\n" +
        "        .date-selector { display: flex; align-items: center; gap: 12px; background: #f8f9fa;" +
        " border: 1px solid #dee2e6; border-radius: 6px; padding: 12px 20px; margin-bottom: 24px; }\n" +
        "        .date-selector label { font-weight: 600; color: #2c3e50; white-space: nowrap; }\n" +
        "        .date-selector select { padding: 6px 12px; border: 1px solid #ced4da; border-radius: 4px;" +
        " font-size: 14px; color: #2c3e50; cursor: pointer; }\n" +
        "        .info-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }\n" +
        "        .info-table td { padding: 12px 15px; border-bottom: 1px solid #ecf0f1; }\n" +
        "        .info-table td:first-child {\n" +
        "            font-weight: 600; background-color: #ecf0f1; width: 30%; color: #2c3e50;\n" +
        "        }\n" +
        "        .alert {\n" +
        "            padding: 15px; margin-bottom: 20px; border-radius: 4px; border-left: 4px solid;\n" +
        "        }\n" +
        "        .alert-info    { background-color: #d1ecf1; border-left-color: #0c5460; color: #0c5460; }\n" +
        "        .alert-warning { background-color: #fff3cd; border-left-color: #856404; color: #856404; }\n" +
        "        .alert-danger  { background-color: #f8d7da; border-left-color: #721c24; color: #721c24; }\n" +
        "        .alert-success { background-color: #d4edda; border-left-color: #155724; color: #155724; }\n" +
        "        .alert strong { font-weight: 600; }\n" +
        "        .nok-list { margin-left: 20px; }\n" +
        "        .nok-list li {\n" +
        "            margin-bottom: 15px; list-style: none;\n" +
        "            padding-left: 20px; position: relative;\n" +
        "        }\n" +
        "        .nok-list li:before {\n" +
        "            content: '\\26A0'; position: absolute; left: 0;\n" +
        "            color: #eb3349; font-weight: bold;\n" +
        "        }\n" +
        "        .nok-list strong { color: #2c3e50; display: block; margin-bottom: 5px; }\n" +
        "        .nok-list .detail { font-size: 13px; color: #555; margin: 5px 0; }\n" +
        "        .next-steps {\n" +
        "            background-color: #f8f9fa; padding: 20px;\n" +
        "            border-radius: 4px; border-left: 4px solid #3498db;\n" +
        "        }\n" +
        "        .next-steps h3 { color: #2c3e50; margin-bottom: 15px; font-size: 16px; }\n" +
        "        .footer {\n" +
        "            margin-top: 60px; padding-top: 20px;\n" +
        "            border-top: 1px solid #ecf0f1; text-align: center;\n" +
        "            color: #7f8c8d; font-size: 12px;\n" +
        "        }\n" +
        "        .footer p { margin-bottom: 5px; }\n" +
        "        @media print {\n" +
        "            body { background-color: white; padding: 0; }\n" +
        "            .container { box-shadow: none; padding: 0; }\n" +
        "            .section { page-break-inside: avoid; }\n" +
        "        }\n" +
        "        .dismc-table { width:100%; border-collapse:collapse; font-size:12px; margin-top:6px; }\n" +
        "        .dismc-table th { background:#34495e; color:white; padding:4px 6px; font-size:11px; text-align:center; white-space:nowrap; }\n" +
        "        .dismc-table td { padding:3px 6px; border-bottom:1px solid #ecf0f1; text-align:center; white-space:nowrap; }\n" +
        "        .dismc-alive { background-color:#f0fff4; }\n" +
        "        .dismc-dead  { background-color:#fafafa; color:#aaa; }\n" +
        "        .dismc-s-alive { background:#28a745; color:white; padding:2px 7px; border-radius:3px; font-size:11px; font-weight:600; }\n" +
        "        .dismc-s-dead  { background:#aaa;    color:white; padding:2px 7px; border-radius:3px; font-size:11px; font-weight:600; }\n" +
        "        .dismc-total { text-align:right; font-size:11px; color:#555; padding:5px 8px; background:#f8f9fa; font-weight:600; }\n" +
        "        @media (max-width: 768px) {\n" +
        "            .container { padding: 20px; }\n" +
        "            .header h1 { font-size: 24px; }\n" +
        "            .section-title { font-size: 18px; }\n" +
        "            .result-table { font-size: 12px; }\n" +
        "            th, td { padding: 10px; }\n" +
        "            .dashboard { grid-template-columns: 1fr; }\n" +
        "        }\n" +
        "    </style>\n";
}
