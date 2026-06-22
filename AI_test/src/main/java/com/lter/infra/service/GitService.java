package com.lter.infra.service;

import com.lter.infra.domain.entity.GitRepo;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.repository.GitRepoRepository;
import com.lter.infra.repository.JobHistoryRepository;
import com.lter.infra.util.GitExecutor;
import com.lter.infra.util.ProcessResult;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class GitService {

    private final GitRepoRepository gitRepoRepository;
    private final JobHistoryRepository jobHistoryRepository;
    private final GitExecutor gitExecutor;
    private final SseLogService sseLogService;

    @Transactional
    public GitRepo register(GitRepo gitRepo) {
        return gitRepoRepository.save(gitRepo);
    }

    @Transactional(readOnly = true)
    public List<GitRepo> findAll() {
        return gitRepoRepository.findAll();
    }

    @Transactional(readOnly = true)
    public GitRepo findById(Long id) {
        return gitRepoRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + id));
    }

    @Transactional
    public GitRepo update(Long id, GitRepo updated) {
        GitRepo repo = findById(id);
        repo.setRepoName(updated.getRepoName());
        repo.setRepoUrl(updated.getRepoUrl());
        repo.setBranch(updated.getBranch());
        repo.setAuthType(updated.getAuthType());
        repo.setUsername(updated.getUsername());
        repo.setPassword(updated.getPassword());
        repo.setSshKeyPath(updated.getSshKeyPath());
        repo.setLocalPath(updated.getLocalPath());
        repo.setRepoType(updated.getRepoType());
        repo.setDescription(updated.getDescription());
        return gitRepoRepository.save(repo);
    }

    @Transactional
    public void delete(Long id) {
        gitRepoRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + id));
        gitRepoRepository.deleteById(id);
    }

    @Async
    @Transactional
    public void pull(Long repoId) {
        GitRepo gitRepo = findById(repoId);

        JobHistory job = new JobHistory();
        job.setJobType(JobHistory.JobType.GIT_PULL);
        job.setPlaybookName(gitRepo.getRepoName());
        jobHistoryRepository.save(job);

        try {
            ProcessResult result = gitExecutor.cloneOrPull(gitRepo);

            job.setExitCode(result.getExitCode());
            job.setStdOut(result.getStdOut());
            job.setStdErr(result.getStdErr());
            job.setStatus(result.isSuccess() ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);
            job.setFinishedAt(LocalDateTime.now());

            if (result.isSuccess()) {
                gitRepo.setLastPulledAt(LocalDateTime.now());
                gitRepoRepository.save(gitRepo);
            }

        } catch (Exception e) {
            log.error("Git pull 실패", e);
            job.setStatus(JobHistory.JobStatus.FAIL);
            job.setStdErr(e.getMessage());
            job.setFinishedAt(LocalDateTime.now());
        }

        jobHistoryRepository.save(job);
    }

    /** SSE 실시간 로그와 함께 git clone/pull 실행 */
    @Async
    @Transactional
    public void pullWithStream(Long repoId, String jobKey) {
        GitRepo gitRepo = findById(repoId);

        JobHistory job = new JobHistory();
        job.setJobType(JobHistory.JobType.GIT_PULL);
        job.setPlaybookName(gitRepo.getRepoName());
        jobHistoryRepository.save(job);

        sseLogService.send(jobKey, "=== Git 시작: " + gitRepo.getRepoName() + " ===");

        try {
            ProcessResult result = gitExecutor.cloneOrPullWithStream(gitRepo,
                    line -> sseLogService.send(jobKey, line));

            job.setExitCode(result.getExitCode());
            job.setStdOut(result.getStdOut());
            job.setStdErr(result.getStdErr());
            job.setStatus(result.isSuccess() ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);
            job.setFinishedAt(LocalDateTime.now());

            if (result.isSuccess()) {
                gitRepo.setLastPulledAt(LocalDateTime.now());
                gitRepoRepository.save(gitRepo);
                sseLogService.send(jobKey, "[OK] Git 완료");
            } else {
                sseLogService.send(jobKey, "[FAIL] Git 실패 (exit=" + result.getExitCode() + ")");
            }

        } catch (Exception e) {
            log.error("Git pull 실패", e);
            job.setStatus(JobHistory.JobStatus.FAIL);
            job.setStdErr(e.getMessage());
            job.setFinishedAt(LocalDateTime.now());
            sseLogService.send(jobKey, "[ERROR] " + e.getMessage());
        }

        jobHistoryRepository.save(job);
        sseLogService.complete(jobKey);
    }
}
