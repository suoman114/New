package com.lter.infra.service;

import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.repository.JobHistoryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class ReportService {

    private final ServerService serverService;
    private final JobHistoryRepository jobHistoryRepository;

    public Map<String, Object> buildReport(Long serverId) {
        com.lter.infra.domain.entity.TargetServer server = serverService.findById(serverId);

        List<JobHistory> osJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.OS_SETUP, PageRequest.of(0, 50)).getContent();
        List<JobHistory> pkgSetupJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.PKG_SETUP, PageRequest.of(0, 50)).getContent();
        List<JobHistory> pkgDeployJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.PKG_DEPLOY, PageRequest.of(0, 50)).getContent();
        List<JobHistory> pkgJobs = new ArrayList<>();
        pkgJobs.addAll(pkgSetupJobs);
        pkgJobs.addAll(pkgDeployJobs);
        pkgJobs.sort((a, b) -> b.getStartedAt() != null && a.getStartedAt() != null
                ? b.getStartedAt().compareTo(a.getStartedAt()) : 0);
        List<JobHistory> valJobs = jobHistoryRepository
                .findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                        serverId, JobHistory.JobType.VALIDATION, PageRequest.of(0, 20)).getContent();

        Map<String, Object> report = new LinkedHashMap<>();
        report.put("serverId", serverId);
        report.put("serverName", server.getServerName());
        report.put("ipAddress", server.getIpAddress());
        report.put("generatedAt", java.time.LocalDateTime.now().toString());
        report.put("osSetup", buildSetupResults(osJobs));
        report.put("pkgSetup", buildSetupResults(pkgJobs));
        report.put("validation", buildValidationResults(valJobs));
        return report;
    }

    /** playbook별 최신 실행 결과만 남김 */
    private List<Map<String, Object>> buildSetupResults(List<JobHistory> jobs) {
        Map<String, JobHistory> latestByPlaybook = new LinkedHashMap<>();
        for (JobHistory job : jobs) {
            String key = job.getPlaybookName() != null ? job.getPlaybookName() : "unknown";
            latestByPlaybook.putIfAbsent(key, job);
        }
        return latestByPlaybook.values().stream().map(j -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", j.getId());
            m.put("playbookName", j.getPlaybookName());
            m.put("status", j.getStatus() != null ? j.getStatus().name() : "UNKNOWN");
            m.put("startedAt", j.getStartedAt() != null ? j.getStartedAt().toString() : null);
            m.put("finishedAt", j.getFinishedAt() != null ? j.getFinishedAt().toString() : null);
            return m;
        }).collect(Collectors.toList());
    }

    private Map<String, Object> buildValidationResults(List<JobHistory> jobs) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (JobHistory job : jobs) {
            if (job.getStdOut() == null || job.getStdOut().isEmpty()) continue;
            String playbook = job.getPlaybookName() != null ? job.getPlaybookName().toLowerCase() : "";
            if (playbook.contains("os_audit") && !result.containsKey("osAudit")) {
                result.put("osAudit", buildOsAuditResult(job));
            } else if (playbook.contains("vcs_link") && !result.containsKey("vcsLink")) {
                result.put("vcsLink", buildVcsLinkResult(job));
            } else if (playbook.contains("verify") && !result.containsKey("vcsVerify")) {
                result.put("vcsVerify", buildVcsVerifyResult(job));
            }
        }
        return result;
    }

    private Map<String, Object> buildOsAuditResult(JobHistory job) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("jobId", job.getId());
        result.put("executedAt", job.getStartedAt() != null ? job.getStartedAt().toString() : null);
        result.put("sections", parseOsAuditSections(job.getStdOut()));
        result.put("items", parseCheckItems(job.getStdOut()));
        return result;
    }

    private static final java.util.regex.Pattern ANSI_PATTERN =
            java.util.regex.Pattern.compile("\u001B\\[[;\\d]*m");

    private Map<String, Object> buildVcsLinkResult(JobHistory job) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("jobId", job.getId());
        result.put("executedAt", job.getStartedAt() != null ? job.getStartedAt().toString() : null);
        String cleaned = job.getStdOut() != null
                ? ANSI_PATTERN.matcher(job.getStdOut()).replaceAll("").trim() : "";
        result.put("rawOutput", cleaned);
        return result;
    }

    private Map<String, Object> buildVcsVerifyResult(JobHistory job) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("jobId", job.getId());
        result.put("executedAt", job.getStartedAt() != null ? job.getStartedAt().toString() : null);
        result.put("items", parseCheckItems(job.getStdOut()));
        return result;
    }

    /** ===SECTION:name=== / ===CONFIG:name=== 파싱 */
    private Map<String, List<String>> parseOsAuditSections(String stdout) {
        Map<String, List<String>> sections = new LinkedHashMap<>();
        String currentSection = null;
        List<String> currentLines = new ArrayList<>();
        for (String line : stdout.split("\n")) {
            String trimmed = line.trim();
            if (trimmed.startsWith("===SECTION:") || trimmed.startsWith("===CONFIG:")) {
                if (currentSection != null) {
                    sections.put(currentSection, new ArrayList<>(currentLines));
                }
                currentSection = trimmed.replaceAll("===SECTION:|===CONFIG:|===", "").trim();
                currentLines = new ArrayList<>();
            } else if (!trimmed.isEmpty() && currentSection != null) {
                currentLines.add(trimmed);
            }
        }
        if (currentSection != null && !currentLines.isEmpty()) {
            sections.put(currentSection, currentLines);
        }
        return sections;
    }

    /** [OK] / [WARN] / [FAIL] 라인 파싱 */
    private List<Map<String, Object>> parseCheckItems(String stdout) {
        List<Map<String, Object>> items = new ArrayList<>();
        for (String line : stdout.split("\n")) {
            String trimmed = line.trim();
            String status = null;
            if (trimmed.contains("[OK]"))   status = "OK";
            else if (trimmed.contains("[WARN]")) status = "WARN";
            else if (trimmed.contains("[FAIL]")) status = "FAIL";
            if (status != null) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("status", status);
                item.put("detail", trimmed.replaceAll("\\[OK\\]|\\[WARN\\]|\\[FAIL\\]", "").trim());
                items.add(item);
            }
        }
        return items;
    }
}
