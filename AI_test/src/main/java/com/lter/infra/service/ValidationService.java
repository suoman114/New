package com.lter.infra.service;

import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.domain.entity.Script;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.domain.dto.ValidationRequest;
import com.lter.infra.repository.JobHistoryRepository;
import com.lter.infra.repository.ScriptRepository;
import com.lter.infra.util.ProcessResult;
import com.lter.infra.util.ScriptExecutor;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.function.Consumer;

@Slf4j
@Service
@RequiredArgsConstructor
public class ValidationService {

    private final ScriptExecutor scriptExecutor;
    private final JobHistoryRepository jobHistoryRepository;
    private final ScriptRepository scriptRepository;
    private final ServerService serverService;

    private static final String REMOTE_SCRIPT_PATH = "/tmp/lter_script/";

    @Async
    public void runValidation(Long serverId, ValidationRequest request) {
        runValidationSync(serverId, request, null);
    }

    /** 다중 서버 병렬 실행 */
    @Async
    public void runValidationBatch(List<Long> serverIds, ValidationRequest request) {
        serverIds.parallelStream().forEach(serverId -> runValidationSync(serverId, request, null));
    }

    /** Pipeline 내부에서 동기 호출용 (logConsumer 로 실시간 로그 전달) */
    public void runValidationSync(Long serverId, ValidationRequest request, Consumer<String> logConsumer) {
        TargetServer server = serverService.findById(serverId);
        Script script = scriptRepository.findById(request.getScriptId())
                .orElseThrow(() -> new IllegalArgumentException("스크립트를 찾을 수 없습니다. id=" + request.getScriptId()));

        JobHistory job = new JobHistory();
        job.setTargetServer(server);
        job.setJobType(JobHistory.JobType.VALIDATION);
        job.setPlaybookName(script.getScriptName());
        jobHistoryRepository.save(job);

        try {
            // 1. 스크립트를 대상 서버로 전송
            String remoteScriptPath = REMOTE_SCRIPT_PATH + script.getScriptName();
            String localPath = script.getLocalPath();
            if (!localPath.endsWith(script.getScriptName())) {
                localPath = localPath.replaceAll("/+$", "") + "/" + script.getScriptName();
            }
            ProcessResult copyResult = scriptExecutor.copyScript(
                    localPath, server.getIpAddress(), remoteScriptPath, server.getSshPassword());

            if (!copyResult.isSuccess()) {
                failJob(job, copyResult);
                return;
            }

            // 2. 원격 스크립트 실행
            ProcessResult runResult = scriptExecutor.runRemote(
                    server.getIpAddress(), remoteScriptPath, server.getServerName(),
                    request.getScriptArgs(), server.getSshPassword(), logConsumer);

            // 3. 결과 파싱 및 저장
            ScriptExecutor.ValidationSummary summary = scriptExecutor.parseValidationResult(runResult.getStdOut());
            log.info("Validation 결과 - OK:{}, WARN:{}, FAIL:{}", summary.getOk(), summary.getWarn(), summary.getFail());

            job.setExitCode(runResult.getExitCode());
            job.setStdOut(runResult.getStdOut());
            job.setStdErr(runResult.getStdErr());
            job.setFinishedAt(LocalDateTime.now());
            job.setStatus(summary.isPassed() ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);

            if (summary.isPassed()) {
                serverService.updateStatus(serverId, TargetServer.ServerStatus.VERIFIED);
            }

        } catch (Exception e) {
            log.error("Validation 실행 오류", e);
            job.setStatus(JobHistory.JobStatus.FAIL);
            job.setStdErr(e.getMessage());
            job.setFinishedAt(LocalDateTime.now());
        }

        jobHistoryRepository.save(job);
    }

    @Transactional(readOnly = true)
    public JobHistory findResultById(Long jobId) {
        return jobHistoryRepository.findById(jobId)
                .orElseThrow(() -> new IllegalArgumentException("작업을 찾을 수 없습니다. jobId=" + jobId));
    }

    @Transactional(readOnly = true)
    public List<JobHistory> findHistory(Long serverId, int page) {
        org.springframework.data.domain.Pageable pageable =
                org.springframework.data.domain.PageRequest.of(page, 10);
        return jobHistoryRepository.findByTargetServerIdAndJobTypeOrderByStartedAtDesc(
                serverId, JobHistory.JobType.VALIDATION, pageable).getContent();
    }

    private void failJob(JobHistory job, ProcessResult result) {
        job.setExitCode(result.getExitCode());
        job.setStdOut(result.getStdOut());
        job.setStdErr(result.getStdErr());
        job.setStatus(JobHistory.JobStatus.FAIL);
        job.setFinishedAt(LocalDateTime.now());
        jobHistoryRepository.save(job);
    }
}
