package com.lter.infra.service;

import com.lter.infra.domain.dto.PipelineRequest;
import com.lter.infra.domain.entity.*;
import com.lter.infra.repository.*;
import com.lter.infra.util.InventoryGenerator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Lazy;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class PipelineService {

    private final PipelineRepository pipelineRepository;
    private final PipelineRunRepository pipelineRunRepository;
    private final PipelineStepRunRepository stepRunRepository;
    private final ServerService serverService;
    private final SetupService setupService;
    private final ValidationService validationService;
    private final SseLogService sseLogService;
    private final InventoryGenerator inventoryGenerator;
    private final PackageDeployService packageDeployService;

    // 내부 @Async 호출 시 프록시를 통하도록 self 주입
    @Lazy @Autowired
    private PipelineService self;

    // MANUAL 모드: runId -> 다음 단계 진행 여부 (true=승인, false=취소 대기)
    private final Map<Long, Object> approvalLocks = new ConcurrentHashMap<>();

    // ── CRUD ──────────────────────────────────────────────

    @Transactional
    public Pipeline create(PipelineRequest request) {
        Pipeline pipeline = new Pipeline();
        pipeline.setName(request.getName());
        pipeline.setDescription(request.getDescription());
        pipeline.setExecutionMode(request.getExecutionMode());
        pipelineRepository.save(pipeline);

        if (request.getSteps() != null) {
            for (PipelineRequest.StepDto dto : request.getSteps()) {
                PipelineStep step = toStep(dto, pipeline);
                pipeline.getSteps().add(step);
            }
        }
        return pipelineRepository.save(pipeline);
    }

    @Transactional
    public Pipeline update(Long id, PipelineRequest request) {
        Pipeline pipeline = findById(id);
        pipeline.setName(request.getName());
        pipeline.setDescription(request.getDescription());
        pipeline.setExecutionMode(request.getExecutionMode());
        pipeline.getSteps().clear();
        if (request.getSteps() != null) {
            for (PipelineRequest.StepDto dto : request.getSteps()) {
                pipeline.getSteps().add(toStep(dto, pipeline));
            }
        }
        return pipelineRepository.save(pipeline);
    }

    @Transactional(readOnly = true)
    public List<Pipeline> findAll() {
        return pipelineRepository.findAll();
    }

    @Transactional(readOnly = true)
    public Pipeline findById(Long id) {
        return pipelineRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("파이프라인을 찾을 수 없습니다. id=" + id));
    }

    @Transactional
    public void delete(Long id) {
        pipelineRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("파이프라인을 찾을 수 없습니다. id=" + id));
        pipelineRunRepository.deleteByPipeline_Id(id);
        pipelineRepository.deleteById(id);
    }

    @Transactional(readOnly = true)
    public List<PipelineRun> findRuns(Long pipelineId, int page) {
        return pipelineRunRepository.findByPipeline_IdOrderByStartedAtDesc(
                pipelineId, PageRequest.of(page, 10)).getContent();
    }

    @Transactional(readOnly = true)
    public PipelineRun findRunById(Long runId) {
        return pipelineRunRepository.findById(runId)
                .orElseThrow(() -> new IllegalArgumentException("실행 이력을 찾을 수 없습니다. runId=" + runId));
    }

    // ── 실행 ──────────────────────────────────────────────

    @Transactional
    public PipelineRun startRun(Long pipelineId, Map<Long, String> sshPasswords) {
        Pipeline pipeline = findById(pipelineId);
        PipelineRun run = new PipelineRun();
        run.setPipeline(pipeline);
        run.setPipelineName(pipeline.getName());
        run.setCurrentStepOrder(0);
        pipelineRunRepository.saveAndFlush(run);

        final Long runId = run.getId();
        final Long pid = pipeline.getId();
        // 트랜잭션 커밋 완료 후 async 실행 → findById race condition 방지
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    self.executeAsync(runId, pid, sshPasswords);
                }
            }
        );
        return run;
    }

    @Async
    public void executeAsync(Long runId, Long pipelineId, Map<Long, String> sshPasswords) {
        // 트랜잭션 밖에서 실행하므로 각 단계마다 직접 저장
        PipelineRun run = pipelineRunRepository.findById(runId).orElse(null);
        if (run == null) return;

        Pipeline pipeline = pipelineRepository.findById(pipelineId).orElse(null);
        if (pipeline == null) return;
        List<PipelineStep> steps = pipeline.getSteps();
        String sseKey = "pipeline-" + runId;

        // 프론트엔드 SSE 구독 대기 (최대 5초)
        for (int i = 0; i < 50 && !sseLogService.hasSubscriber(sseKey); i++) {
            try { Thread.sleep(100); } catch (InterruptedException e) {
                Thread.currentThread().interrupt(); return;
            }
        }

        sseLogService.send(sseKey, "=== 파이프라인 시작: " + pipeline.getName() + " ===");

        for (PipelineStep step : steps) {
            run.setCurrentStepOrder(step.getStepOrder());
            pipelineRunRepository.save(run);

            // MANUAL 모드: 첫 단계 제외하고 승인 대기
            if (pipeline.getExecutionMode() == Pipeline.ExecutionMode.MANUAL
                    && step.getStepOrder() > steps.get(0).getStepOrder()) {
                run.setStatus(PipelineRun.RunStatus.WAITING_APPROVAL);
                pipelineRunRepository.save(run);
                sseLogService.send(sseKey, "[WAITING] 단계 " + step.getStepOrder() + " 승인 대기 중...");

                // 승인 올 때까지 대기
                boolean approved = waitForApproval(runId);
                if (!approved) {
                    run.setStatus(PipelineRun.RunStatus.CANCELLED);
                    run.setFinishedAt(LocalDateTime.now());
                    pipelineRunRepository.save(run);
                    sseLogService.send(sseKey, "[CANCELLED] 사용자가 취소했습니다.");
                    sseLogService.complete(sseKey);
                    return;
                }
                run.setStatus(PipelineRun.RunStatus.RUNNING);
                pipelineRunRepository.save(run);
            }

            sseLogService.send(sseKey, "\n── 단계 " + step.getStepOrder() + ": " + step.getStepType() + " ──");
            boolean stepOk = executeStep(run, step, sseKey, sshPasswords);

            if (!stepOk) {
                run.setStatus(PipelineRun.RunStatus.FAIL);
                run.setFinishedAt(LocalDateTime.now());
                pipelineRunRepository.save(run);
                sseLogService.send(sseKey, "[FAIL] 단계 실패로 파이프라인 중단");
                sseLogService.complete(sseKey);
                return;
            }
        }

        run.setStatus(PipelineRun.RunStatus.SUCCESS);
        run.setFinishedAt(LocalDateTime.now());
        pipelineRunRepository.save(run);
        sseLogService.send(sseKey, "\n=== 파이프라인 완료 ===");
        sseLogService.complete(sseKey);
    }

    /** 수동 모드 승인 처리 */
    @Transactional
    public void approve(Long runId, boolean approved) {
        Object lock = approvalLocks.get(runId);
        if (lock != null) {
            synchronized (lock) {
                approvalLocks.put(runId, approved ? Boolean.TRUE : Boolean.FALSE);
                lock.notifyAll();
            }
        }
    }

    // ── 내부 헬퍼 ──────────────────────────────────────────

    private boolean waitForApproval(Long runId) {
        Object lock = new Object();
        approvalLocks.put(runId, lock);
        synchronized (lock) {
            try {
                lock.wait(); // 승인/거절 올 때까지 대기 (타임아웃 없음)
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        Object result = approvalLocks.remove(runId);
        return Boolean.TRUE.equals(result);
    }

    private boolean executeStep(PipelineRun run, PipelineStep step, String sseKey, Map<Long, String> sshPasswords) {
        List<Long> serverIds = step.getServerIdList();
        List<TargetServer> servers = new ArrayList<>();
        for (Long serverId : serverIds) {
            try {
                servers.add(serverService.findById(serverId));
            } catch (Exception e) {
                sseLogService.send(sseKey, "[ERROR] 서버 ID " + serverId + " 없음: " + e.getMessage());
            }
        }
        if (servers.isEmpty()) return false;

        // OS_SETUP: 전체 서버를 Ansible inventory에 등록 후 1회 실행
        if (step.getStepType() == PipelineStep.StepType.OS_SETUP) {
            return executeOsSetupForAll(run, step, servers, sseKey, sshPasswords);
        }

        // PKG_SETUP / VALIDATION: 서버별 병렬 실행
        List<PipelineStepRun> stepRuns = new ArrayList<>();
        for (TargetServer server : servers) {
            PipelineStepRun stepRun = new PipelineStepRun();
            stepRun.setPipelineRun(run);
            stepRun.setStepOrder(step.getStepOrder());
            stepRun.setStepType(step.getStepType());
            stepRun.setServerName(server.getServerName());
            stepRun.setServerIp(server.getIpAddress());
            stepRunRepository.save(stepRun);
            stepRuns.add(stepRun);
            sseLogService.send(sseKey, "  → 서버: " + server.getServerName() + " (" + server.getIpAddress() + ")");
        }

        List<CompletableFuture<Boolean>> futures = new ArrayList<>();
        for (TargetServer server : servers) {
            final TargetServer srv = server;
            futures.add(CompletableFuture.supplyAsync(() -> runStepForServer(step, srv, sseKey, sshPasswords)));
        }

        boolean allOk = true;
        for (int i = 0; i < futures.size(); i++) {
            boolean ok;
            try {
                ok = futures.get(i).get();
            } catch (Exception e) {
                ok = false;
                sseLogService.send(sseKey, "[ERROR] " + servers.get(i).getServerName() + ": " + e.getMessage());
            }
            PipelineStepRun stepRun = stepRuns.get(i);
            stepRun.setStatus(ok ? PipelineStepRun.StepRunStatus.SUCCESS : PipelineStepRun.StepRunStatus.FAIL);
            stepRun.setFinishedAt(LocalDateTime.now());
            stepRunRepository.save(stepRun);
            if (!ok) allOk = false;
        }
        return allOk;
    }

    private boolean executeOsSetupForAll(PipelineRun run, PipelineStep step, List<TargetServer> servers,
                                          String sseKey, Map<Long, String> sshPasswords) {
        List<PipelineStepRun> stepRuns = new ArrayList<>();
        for (TargetServer server : servers) {
            PipelineStepRun stepRun = new PipelineStepRun();
            stepRun.setPipelineRun(run);
            stepRun.setStepOrder(step.getStepOrder());
            stepRun.setStepType(step.getStepType());
            stepRun.setServerName(server.getServerName());
            stepRun.setServerIp(server.getIpAddress());
            stepRunRepository.save(stepRun);
            stepRuns.add(stepRun);
        }

        Map<String, String> ipPwMap = setupService.buildIpPasswordMap(servers, sshPasswords);
        inventoryGenerator.generate(
                servers.stream().map(TargetServer::getIpAddress).collect(Collectors.toList()),
                ipPwMap);

        Map<String, String> extraVars = new HashMap<>();
        if (step.getNtpServer() != null)       extraVars.put("ntp_server", step.getNtpServer());
        if (step.getMariaDbPassword() != null) extraVars.put("new_password", step.getMariaDbPassword());
        if (step.getDatabaseName() != null)    extraVars.put("database_name", step.getDatabaseName());

        List<String> playbooks = setupService.resolvePlaybooks(
                step.getSelectedPlaybookList(), setupService.listAllPlaybooks());

        final boolean[] failed = {false};
        setupService.runPlaybooks(servers, playbooks, JobHistory.JobType.OS_SETUP,
                extraVars, line -> {
                    sseLogService.send(sseKey, "  " + line);
                    if (line.startsWith("[FAIL]") || line.startsWith("[ERROR]")) failed[0] = true;
                }, false);

        boolean ok = !failed[0];
        PipelineStepRun.StepRunStatus status = ok
                ? PipelineStepRun.StepRunStatus.SUCCESS : PipelineStepRun.StepRunStatus.FAIL;
        for (PipelineStepRun sr : stepRuns) {
            sr.setStatus(status);
            sr.setFinishedAt(LocalDateTime.now());
            stepRunRepository.save(sr);
        }
        if (ok) {
            for (TargetServer server : servers) {
                serverService.updateStatus(server.getId(), TargetServer.ServerStatus.OS_SETUP_DONE);
            }
        }
        return ok;
    }

    private boolean runStepForServer(PipelineStep step, TargetServer server, String sseKey, Map<Long, String> sshPasswords) {
        try {
            switch (step.getStepType()) {
                case PKG_SETUP:
                    return runPkgSetupStep(step, server, sseKey, sshPasswords);
                case VALIDATION:
                    return runValidationStep(step, server, sseKey);
                default:
                    return false;
            }
        } catch (Exception e) {
            sseLogService.send(sseKey, "[ERROR] " + e.getMessage());
            return false;
        }
    }

    private boolean runPkgSetupStep(PipelineStep step, TargetServer server, String sseKey, Map<Long, String> sshPasswords) {
        String sshPassword = sshPasswords != null ? sshPasswords.get(server.getId()) : null;
        boolean allOk = true;

        // 패키지 배포
        List<String> packages = step.getSelectedPackageList();
        if (!packages.isEmpty()) {
            String remotePath = step.getRemoteDeployPath() != null ? step.getRemoteDeployPath() : "/tmp";
            sseLogService.send(sseKey, "=== 패키지 배포 시작: " + server.getServerName() + " ===");
            boolean ok = packageDeployService.deploySync(server, packages, remotePath, sshPassword,
                    line -> sseLogService.send(sseKey, "  " + line));
            if (!ok) allOk = false;
        }

        if (allOk) serverService.updateStatus(server.getId(), TargetServer.ServerStatus.PKG_SETUP_DONE);
        return allOk;
    }

    private boolean runValidationStep(PipelineStep step, TargetServer server, String sseKey) {
        if (step.getScriptId() == null) {
            sseLogService.send(sseKey, "[ERROR] Validation 단계에 scriptId가 없습니다.");
            return false;
        }
        com.lter.infra.domain.dto.ValidationRequest req = new com.lter.infra.domain.dto.ValidationRequest();
        req.setScriptId(step.getScriptId());
        req.setScriptArgs(step.getScriptArgs());
        // ValidationService.runValidation 은 @Async 이므로 동기 내부 메서드 직접 호출
        validationService.runValidationSync(server.getId(), req,
                line -> sseLogService.send(sseKey, "  " + line));
        return true;
    }

    private PipelineStep toStep(PipelineRequest.StepDto dto, Pipeline pipeline) {
        PipelineStep step = new PipelineStep();
        step.setPipeline(pipeline);
        step.setStepOrder(dto.getStepOrder());
        step.setStepType(dto.getStepType());
        step.setNtpServer(dto.getNtpServer());
        step.setMariaDbPassword(dto.getMariaDbPassword());
        step.setDatabaseName(dto.getDatabaseName());
        step.setScriptId(dto.getScriptId());
        step.setScriptArgs(dto.getScriptArgs());
        step.setSelectedPlaybookList(dto.getSelectedPlaybooks());
        step.setSelectedPackageList(dto.getSelectedPackages());
        step.setRemoteDeployPath(dto.getRemoteDeployPath());
        step.setServerIdList(dto.getServerIds());
        return step;
    }
}
