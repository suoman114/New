package com.lter.infra.service;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.repository.JobHistoryRepository;
import com.lter.infra.util.RemoteCommandBuilder;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.time.LocalDateTime;
import java.util.List;
import java.util.function.Consumer;

@Slf4j
@Service
@RequiredArgsConstructor
public class PackageDeployService {

    private final SystemConfigService systemConfigService;
    private final ServerService serverService;
    private final SseLogService sseLogService;
    private final JobHistoryRepository jobHistoryRepository;

    /**
     * 선택된 패키지 파일들을 대상 서버에 SCP로 전송 후 압축 해제
     * @param serverId     대상 서버 ID
     * @param fileNames    배포할 파일명 목록 (PACKAGE_BASE_DIR 기준)
     * @param remotePath   원격 서버의 저장 경로 (예: /opt/vcs)
     * @param sshPassword  SSH root 패스워드
     * @param sshPort      SSH 포트
     * @param jobKey       SSE jobKey
     */
    @Async
    public void deploy(Long serverId, List<String> fileNames, String remotePath,
                       String sshPassword, int sshPort, String jobKey) {
        TargetServer server = serverService.findById(serverId);
        String ip = server.getIpAddress();
        String localBaseDir = systemConfigService.get(InfraConfig.PACKAGE_BASE_DIR);
        Consumer<String> log = line -> sseLogService.send(jobKey, line);

        log.accept("=== 패키지 배포 시작: " + server.getServerName() + " ===");

        for (String fileName : fileNames) {
            File localFile = new File(localBaseDir, fileName);
            if (!localFile.exists()) {
                log.accept("[SKIP] 파일 없음: " + fileName);
                continue;
            }

            JobHistory job = new JobHistory();
            job.setTargetServer(server);
            job.setJobType(JobHistory.JobType.PKG_DEPLOY);
            job.setPlaybookName("deploy:" + fileName);
            jobHistoryRepository.save(job);

            StringBuilder output = new StringBuilder();
            boolean ok = true;

            // 1단계: SCP 전송
            log.accept("[SCP] " + fileName + " → " + ip + ":" + remotePath);
            ok = runCmd(buildScpCmd(localFile.getAbsolutePath(), ip, sshPort, sshPassword, remotePath),
                    output, log);

            // 2단계: 압축 해제
            if (ok) {
                String extractCmd = buildExtractCmd(remotePath, fileName);
                log.accept("[EXTRACT] " + fileName);
                ok = runCmd(buildSshCmd(ip, sshPort, sshPassword, extractCmd), output, log);
            }

            job.setStdOut(output.toString());
            job.setStatus(ok ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);
            job.setFinishedAt(LocalDateTime.now());
            job.setExitCode(ok ? 0 : 1);
            jobHistoryRepository.save(job);

            if (ok) log.accept("[OK] " + fileName + " 배포 완료");
            else     log.accept("[FAIL] " + fileName + " 배포 실패");
        }

        log.accept("=== 패키지 배포 종료 ===");
        sseLogService.complete(jobKey);
    }

    /**
     * 파이프라인 내부에서 동기적으로 패키지 배포 (SSE 없이 logConsumer로 로그 전달)
     */
    public boolean deploySync(TargetServer server, List<String> fileNames, String remotePath,
                              String sshPassword, Consumer<String> logConsumer) {
        String ip = server.getIpAddress();
        int sshPort = 22;
        String baseDir = systemConfigService.get(InfraConfig.PACKAGE_BASE_DIR);
        boolean allOk = true;

        for (String fileName : fileNames) {
            File localFile = new File(baseDir, fileName);
            if (!localFile.exists()) {
                logConsumer.accept("[SKIP] 파일 없음: " + fileName);
                continue;
            }

            JobHistory job = new JobHistory();
            job.setTargetServer(server);
            job.setJobType(JobHistory.JobType.PKG_DEPLOY);
            job.setPlaybookName("deploy:" + fileName);
            jobHistoryRepository.save(job);

            StringBuilder output = new StringBuilder();

            logConsumer.accept("[SCP] " + fileName + " → " + ip + ":" + remotePath);
            boolean ok = runCmd(buildScpCmd(localFile.getAbsolutePath(), ip, sshPort, sshPassword, remotePath), output, logConsumer);

            if (ok) {
                String extractCmd = buildExtractCmd(remotePath, fileName);
                logConsumer.accept("[EXTRACT] " + fileName);
                ok = runCmd(buildSshCmd(ip, sshPort, sshPassword, extractCmd), output, logConsumer);
            }

            job.setStdOut(output.toString());
            job.setStatus(ok ? JobHistory.JobStatus.SUCCESS : JobHistory.JobStatus.FAIL);
            job.setFinishedAt(java.time.LocalDateTime.now());
            job.setExitCode(ok ? 0 : 1);
            jobHistoryRepository.save(job);

            if (ok) logConsumer.accept("[OK] " + fileName + " 배포 완료");
            else   { logConsumer.accept("[FAIL] " + fileName + " 배포 실패"); allOk = false; }
        }
        return allOk;
    }

    // 원격 명령 구성은 RemoteCommandBuilder(순수 함수, 단위테스트 대상)에 위임한다.
    private List<String> buildScpCmd(String localPath, String ip, int port,
                                      String password, String remotePath) {
        return RemoteCommandBuilder.scp(localPath, ip, port, password, remotePath);
    }

    private List<String> buildSshCmd(String ip, int port, String password, String remoteCmd) {
        return RemoteCommandBuilder.ssh(ip, port, password, remoteCmd);
    }

    private String buildExtractCmd(String remotePath, String fileName) {
        return RemoteCommandBuilder.extractCommand(remotePath, fileName);
    }

    private boolean runCmd(List<String> cmd, StringBuilder output, Consumer<String> log) {
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            Process process = pb.start();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(process.getInputStream()))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    output.append(line).append("\n");
                    log.accept("  " + line);
                }
            }
            int exit = process.waitFor();
            return exit == 0;
        } catch (Exception e) {
            log.accept("[ERROR] " + e.getMessage());
            output.append(e.getMessage());
            return false;
        }
    }
}
