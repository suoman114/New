package com.lter.infra.service;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.domain.dto.SetupRequest;
import com.lter.infra.repository.JobHistoryRepository;
import com.lter.infra.util.AnsibleExecutor;
import com.lter.infra.util.InventoryGenerator;
import com.lter.infra.util.PlaybookCatalog;
import com.lter.infra.util.ProcessResult;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.io.File;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Consumer;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class SetupService {

    private final AnsibleExecutor ansibleExecutor;
    private final JobHistoryRepository jobHistoryRepository;
    private final ServerService serverService;
    private final InventoryGenerator inventoryGenerator;
    private final SseLogService sseLogService;
    private final SystemConfigService systemConfigService;

    // playbook 분류(OS/PKG)·번호 prefix·정렬 규약은 PlaybookCatalog 가 단일 출처다.

    /** playbook 디렉토리에서 OS 관련 파일 목록을 읽어 반환 (prefix 번호 순 정렬) */
    public List<String> listOsPlaybooks() {
        return listPlaybooksByPrefixes(PlaybookCatalog.OS_PREFIX_NUMS);
    }

    /** playbook 디렉토리에서 PKG 관련 파일 목록을 읽어 반환 (prefix 번호 순 정렬) */
    public List<String> listPkgPlaybooks() {
        return listPlaybooksByPrefixes(PlaybookCatalog.PKG_PREFIX_NUMS);
    }

    private List<String> listPlaybooksByPrefixes(Set<Integer> prefixes) {
        String dir;
        try {
            dir = systemConfigService.get(InfraConfig.ANSIBLE_PLAYBOOK_DIR);
        } catch (Exception e) {
            log.warn("ansible.playbook-dir 설정을 읽을 수 없습니다: {}", e.getMessage());
            return Collections.emptyList();
        }
        File[] files = new File(dir).listFiles(
                (d, name) -> (name.endsWith(".yml") || name.endsWith(".yaml"))
                        && prefixes.contains(PlaybookCatalog.extractPrefixNum(name)));
        if (files == null) return Collections.emptyList();
        return PlaybookCatalog.filterAndSort(
                Arrays.stream(files).map(File::getName).collect(Collectors.toList()), prefixes);
    }

    /** OS + PKG 통합 셋업 - 사용자가 지정한 순서 그대로 playbook 실행 */
    @Async
    public void runSetupAllBatch(List<Long> serverIds, SetupRequest request, String jobKey) {
        Consumer<String> logConsumer = sseLogService.logConsumer(jobKey);
        List<TargetServer> servers = serverIds.stream()
                .map(serverService::findById).collect(Collectors.toList());

        Map<String, String> ipPasswordMap = buildIpPasswordMap(servers, request.getSshPasswords());
        inventoryGenerator.generate(
                servers.stream().map(TargetServer::getIpAddress).collect(Collectors.toList()),
                ipPasswordMap);

        logConsumer.accept("=== 셋업 시작: " + servers.stream()
                .map(TargetServer::getServerName).collect(Collectors.joining(", ")) + " ===");

        // 사용자 지정 순서 그대로 사용 (null이면 전체 목록을 prefix 순으로)
        List<String> ordered = request.getSelectedPlaybooks();
        if (ordered == null || ordered.isEmpty()) {
            ordered = listAllPlaybooks();
        }

        // resumeFrom 처리
        ordered = resolveResumeFrom(request.getResumeFrom(), ordered);

        // OS prefix 집합으로 각 playbook의 JobType 판별, extraVars 결정
        Map<String, String> osExtra = new HashMap<>();
        if (request.getNtpServer() != null) osExtra.put("ntp_server", request.getNtpServer());
        Map<String, String> pkgExtra = new HashMap<>();
        if (request.getMariaDbPassword() != null) pkgExtra.put("new_password", request.getMariaDbPassword());
        if (request.getDatabaseName() != null)    pkgExtra.put("database_name", request.getDatabaseName());

        for (String playbook : ordered) {
            JobHistory.JobType jobType = PlaybookCatalog.isPkg(playbook)
                    ? JobHistory.JobType.PKG_SETUP : JobHistory.JobType.OS_SETUP;
            Map<String, String> extra = jobType == JobHistory.JobType.PKG_SETUP ? pkgExtra : osExtra;
            runPlaybooks(servers, Collections.singletonList(playbook), jobType, extra,
                    logConsumer, request.isContinueOnFailure());
        }

        servers.forEach(s -> serverService.updateStatus(s.getId(), TargetServer.ServerStatus.PKG_SETUP_DONE));
        sseLogService.complete(jobKey);
    }

    /** 전체 playbook 목록(OS+PKG) 반환 - prefix 번호 순 정렬 */
    public List<String> listAllPlaybooks() {
        return listPlaybooksByPrefixes(PlaybookCatalog.allPrefixNums());
    }

    /** 다중 서버 OS 셋업 - SSE 실시간 로그 (병렬 실행) */
    @Async
    public void runOsSetupBatch(List<Long> serverIds, SetupRequest request, String jobKey) {
        Consumer<String> logConsumer = sseLogService.logConsumer(jobKey);
        List<TargetServer> servers = serverIds.stream()
                .map(serverService::findById).collect(Collectors.toList());

        // 서버별 패스워드 맵 (ip -> password)
        Map<String, String> ipPasswordMap = buildIpPasswordMap(servers, request.getSshPasswords());

        // inventory에 전체 서버 + 패스워드 등록 → ansible이 동시에 실행
        inventoryGenerator.generate(
                servers.stream().map(TargetServer::getIpAddress).collect(Collectors.toList()),
                ipPasswordMap);

        logConsumer.accept("=== OS 셋업 시작: " + servers.stream()
                .map(TargetServer::getServerName).collect(Collectors.joining(", ")) + " ===");

        Map<String, String> extraVars = new HashMap<>();
        if (request.getNtpServer() != null) extraVars.put("ntp_server", request.getNtpServer());

        List<String> playbooks = resolveResumeFrom(request.getResumeFrom(),
                resolvePlaybooks(request.getSelectedPlaybooks(), listOsPlaybooks()));
        runPlaybooks(servers, playbooks, JobHistory.JobType.OS_SETUP, extraVars, logConsumer, request.isContinueOnFailure());
        servers.forEach(s -> serverService.updateStatus(s.getId(), TargetServer.ServerStatus.OS_SETUP_DONE));
        sseLogService.complete(jobKey);
    }

    /** 다중 서버 PKG 셋업 - SSE 실시간 로그 (병렬 실행) */
    @Async
    public void runPkgSetupBatch(List<Long> serverIds, SetupRequest request, String jobKey) {
        Consumer<String> logConsumer = sseLogService.logConsumer(jobKey);
        List<TargetServer> servers = serverIds.stream()
                .map(serverService::findById).collect(Collectors.toList());

        inventoryGenerator.generate(
                servers.stream().map(TargetServer::getIpAddress).collect(Collectors.toList()),
                Collections.emptyMap());

        logConsumer.accept("=== PKG 셋업 시작: " + servers.stream()
                .map(TargetServer::getServerName).collect(Collectors.joining(", ")) + " ===");

        Map<String, String> extraVars = new HashMap<>();
        if (request.getMariaDbPassword() != null) extraVars.put("new_password", request.getMariaDbPassword());
        if (request.getDatabaseName() != null)    extraVars.put("database_name", request.getDatabaseName());

        List<String> playbooks = resolveResumeFrom(request.getResumeFrom(),
                resolvePlaybooks(request.getSelectedPlaybooks(), listPkgPlaybooks()));
        runPlaybooks(servers, playbooks, JobHistory.JobType.PKG_SETUP, extraVars, logConsumer, request.isContinueOnFailure());
        servers.forEach(s -> serverService.updateStatus(s.getId(), TargetServer.ServerStatus.PKG_SETUP_DONE));
        sseLogService.complete(jobKey);
    }

    @Async
    public void runOsSetup(Long serverId, SetupRequest request) {
        TargetServer server = serverService.findById(serverId);
        Map<String, String> ipPwMap = buildIpPasswordMap(
                Collections.singletonList(server), request.getSshPasswords());
        inventoryGenerator.generate(Collections.singletonList(server.getIpAddress()), ipPwMap);

        Map<String, String> extraVars = new HashMap<>();
        extraVars.put("ansible_host", server.getIpAddress());
        if (request.getNtpServer() != null) extraVars.put("ntp_server", request.getNtpServer());

        List<String> playbooks = resolveResumeFrom(request.getResumeFrom(),
                resolvePlaybooks(request.getSelectedPlaybooks(), listOsPlaybooks()));
        runPlaybooks(server, playbooks, JobHistory.JobType.OS_SETUP, extraVars, null, request.isContinueOnFailure());
        serverService.updateStatus(serverId, TargetServer.ServerStatus.OS_SETUP_DONE);
    }

    @Async
    public void runPkgSetup(Long serverId, SetupRequest request) {
        TargetServer server = serverService.findById(serverId);
        inventoryGenerator.generate(server.getIpAddress());

        Map<String, String> extraVars = new HashMap<>();
        extraVars.put("ansible_host", server.getIpAddress());
        if (request.getMariaDbPassword() != null) {
            extraVars.put("new_password", request.getMariaDbPassword());
        }
        if (request.getDatabaseName() != null) {
            extraVars.put("database_name", request.getDatabaseName());
        }

        List<String> playbooks = resolveResumeFrom(request.getResumeFrom(),
                resolvePlaybooks(request.getSelectedPlaybooks(), listPkgPlaybooks()));
        runPlaybooks(server, playbooks, JobHistory.JobType.PKG_SETUP, extraVars, null, request.isContinueOnFailure());
        serverService.updateStatus(serverId, TargetServer.ServerStatus.PKG_SETUP_DONE);
    }

    public JobHistory findJobById(Long jobId) {
        return jobHistoryRepository.findById(jobId)
                .orElseThrow(() -> new IllegalArgumentException("작업을 찾을 수 없습니다. jobId=" + jobId));
    }

    public List<JobHistory> findJobsByServer(Long serverId, int page) {
        Pageable pageable = PageRequest.of(page, 10);
        return jobHistoryRepository.findByTargetServerIdOrderByStartedAtDesc(serverId, pageable).getContent();
    }

    /**
     * selectedPlaybooks 가 null/비어있으면 전체(allPlaybooks) 반환.
     * 있으면 allPlaybooks 순서를 유지하면서 선택된 것만 필터링.
     */
    public List<String> resolvePlaybooks(List<String> selectedPlaybooks, List<String> allPlaybooks) {
        if (selectedPlaybooks == null || selectedPlaybooks.isEmpty()) {
            return allPlaybooks;
        }
        return allPlaybooks.stream()
                .filter(selectedPlaybooks::contains)
                .collect(Collectors.toList());
    }

    /**
     * resumeFrom 이 지정된 경우 해당 playbook 부터 잘라서 반환.
     */
    public List<String> resolveResumeFrom(String resumeFrom, List<String> playbooks) {
        if (resumeFrom == null || resumeFrom.isEmpty()) return playbooks;
        int idx = playbooks.indexOf(resumeFrom);
        if (idx <= 0) return playbooks;
        return new ArrayList<>(playbooks.subList(idx, playbooks.size()));
    }

    /**
     * 다중 서버 대상 runPlaybooks - Ansible 실행은 inventory에 등록된 전체 서버 대상 1회,
     * JobHistory는 서버별로 각각 저장.
     */
    public void runPlaybooks(List<TargetServer> servers, List<String> playbooks,
                             JobHistory.JobType jobType, Map<String, String> extraVars,
                             Consumer<String> logConsumer, boolean continueOnFailure) {
        for (String playbook : playbooks) {
            List<JobHistory> jobs = new ArrayList<>();
            for (TargetServer server : servers) {
                JobHistory job = new JobHistory();
                job.setTargetServer(server);
                job.setJobType(jobType);
                job.setPlaybookName(playbook);
                jobHistoryRepository.save(job);
                jobs.add(job);
            }

            if (logConsumer != null) logConsumer.accept("[START] " + playbook);

            try {
                ProcessResult result = ansibleExecutor.runPlaybook(playbook, extraVars, logConsumer);

                for (JobHistory job : jobs) {
                    job.setExitCode(result.getExitCode());
                    job.setStdOut(result.getStdOut());
                    job.setStdErr(result.getStdErr());
                    job.setFinishedAt(LocalDateTime.now());
                    job.setStatus(result.isSuccess() ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);
                    jobHistoryRepository.save(job);
                }

                if (result.isSuccess()) {
                    if (logConsumer != null) logConsumer.accept("[OK] " + playbook);
                } else {
                    if (logConsumer != null) logConsumer.accept("[FAIL] " + playbook + " (종료코드: " + result.getExitCode() + ")");
                    log.error("Playbook 실패: {}", playbook);
                    if (!continueOnFailure) break;
                }
            } catch (Exception e) {
                log.error("Playbook 실행 오류: {}", playbook, e);
                for (JobHistory job : jobs) {
                    job.setStatus(JobHistory.JobStatus.FAIL);
                    job.setStdErr(e.getMessage());
                    job.setFinishedAt(LocalDateTime.now());
                    jobHistoryRepository.save(job);
                }
                if (logConsumer != null) logConsumer.accept("[ERROR] " + playbook + " - " + e.getMessage());
                if (!continueOnFailure) break;
            }
        }
    }

    /**
     * PipelineService 에서도 재사용할 수 있도록 패키지 접근 가능하게 열어 둠.
     * logConsumer: 각 출력 라인을 SSE 등으로 전달할 콜백 (null 가능)
     * continueOnFailure: true 면 playbook 실패 시에도 다음 playbook 계속 실행
     */
    public void runPlaybooks(TargetServer server, List<String> playbooks,
                             JobHistory.JobType jobType, Map<String, String> extraVars,
                             Consumer<String> logConsumer, boolean continueOnFailure) {
        for (String playbook : playbooks) {
            JobHistory job = new JobHistory();
            job.setTargetServer(server);
            job.setJobType(jobType);
            job.setPlaybookName(playbook);
            jobHistoryRepository.save(job);

            if (logConsumer != null) {
                logConsumer.accept("[START] " + playbook);
            }

            try {
                ProcessResult result = ansibleExecutor.runPlaybook(playbook, extraVars, logConsumer);

                job.setExitCode(result.getExitCode());
                job.setStdOut(result.getStdOut());
                job.setStdErr(result.getStdErr());
                job.setFinishedAt(LocalDateTime.now());

                if (result.isSuccess()) {
                    job.setStatus(JobHistory.JobStatus.SUCCESS);
                    if (logConsumer != null) logConsumer.accept("[OK] " + playbook);
                } else {
                    job.setStatus(JobHistory.JobStatus.FAIL);
                    jobHistoryRepository.save(job);
                    if (logConsumer != null) logConsumer.accept("[FAIL] " + playbook + " (종료코드: " + result.getExitCode() + ")");
                    log.error("Playbook 실패: {}", playbook);
                    if (!continueOnFailure) break;
                }

            } catch (Exception e) {
                log.error("Playbook 실행 오류: {}", playbook, e);
                job.setStatus(JobHistory.JobStatus.FAIL);
                job.setStdErr(e.getMessage());
                job.setFinishedAt(LocalDateTime.now());
                jobHistoryRepository.save(job);
                if (logConsumer != null) logConsumer.accept("[ERROR] " + playbook + " - " + e.getMessage());
                if (!continueOnFailure) break;
            }

            jobHistoryRepository.save(job);
        }
    }

    /** serverId -> password 맵을 ip -> password 맵으로 변환 */
    public Map<String, String> buildIpPasswordMap(List<TargetServer> servers, Map<Long, String> sshPasswords) {
        Map<String, String> result = new HashMap<>();
        if (sshPasswords == null || sshPasswords.isEmpty()) return result;
        for (TargetServer s : servers) {
            String pw = sshPasswords.get(s.getId());
            if (pw != null && !pw.isEmpty()) result.put(s.getIpAddress(), pw);
        }
        return result;
    }
}
