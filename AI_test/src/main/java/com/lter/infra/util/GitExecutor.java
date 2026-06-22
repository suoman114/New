package com.lter.infra.util;

import com.lter.infra.domain.entity.GitRepo;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;

@Slf4j
@Component
public class GitExecutor {

    public ProcessResult clone(GitRepo gitRepo) {
        List<String> cmd = new ArrayList<>();
        cmd.add("git");
        cmd.add("clone");
        cmd.add("-b");
        cmd.add(gitRepo.getBranch());
        cmd.add(buildRepoUrl(gitRepo));
        cmd.add(gitRepo.getLocalPath());

        log.info("Git clone 실행: {} -> {}", gitRepo.getRepoUrl(), gitRepo.getLocalPath());
        return execute(cmd, null, buildSshEnv(gitRepo));
    }

    public ProcessResult pull(GitRepo gitRepo) {
        List<String> cmd = new ArrayList<>();
        cmd.add("git");
        cmd.add("pull");
        cmd.add("origin");
        cmd.add(gitRepo.getBranch());

        log.info("Git pull 실행: {}", gitRepo.getLocalPath());
        return execute(cmd, new File(gitRepo.getLocalPath()), buildSshEnv(gitRepo));
    }

    public ProcessResult cloneOrPull(GitRepo gitRepo) {
        File localDir = new File(gitRepo.getLocalPath());
        if (localDir.exists() && new File(localDir, ".git").exists()) {
            return pull(gitRepo);
        }
        return clone(gitRepo);
    }

    public ProcessResult cloneOrPullWithStream(GitRepo gitRepo, java.util.function.Consumer<String> logConsumer) {
        File localDir = new File(gitRepo.getLocalPath());
        List<String> cmd = new ArrayList<>();
        if (localDir.exists() && new File(localDir, ".git").exists()) {
            cmd.add("git"); cmd.add("pull"); cmd.add("origin"); cmd.add(gitRepo.getBranch());
            log.info("Git pull (stream) 실행: {}", gitRepo.getLocalPath());
            return executeWithStream(cmd, new File(gitRepo.getLocalPath()), buildSshEnv(gitRepo), logConsumer);
        } else {
            cmd.add("git"); cmd.add("clone"); cmd.add("-b"); cmd.add(gitRepo.getBranch());
            cmd.add(buildRepoUrl(gitRepo)); cmd.add(gitRepo.getLocalPath());
            log.info("Git clone (stream) 실행: {} -> {}", gitRepo.getRepoUrl(), gitRepo.getLocalPath());
            return executeWithStream(cmd, null, buildSshEnv(gitRepo), logConsumer);
        }
    }

    private ProcessResult executeWithStream(List<String> cmd, File workDir,
            java.util.Map<String, String> extraEnv, java.util.function.Consumer<String> logConsumer) {
        StringBuilder stdOut = new StringBuilder();
        StringBuilder stdErr = new StringBuilder();
        int exitCode = -1;
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            if (workDir != null) pb.directory(workDir);
            if (!extraEnv.isEmpty()) pb.environment().putAll(extraEnv);
            pb.redirectErrorStream(true); // stderr → stdout 합침 (git은 stderr로 진행상황 출력)
            Process process = pb.start();

            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    stdOut.append(line).append("\n");
                    if (logConsumer != null) logConsumer.accept(line);
                }
            }
            exitCode = process.waitFor();
            log.info("Git (stream) 완료 - exitCode: {}", exitCode);
        } catch (Exception e) {
            log.error("Git 실행 오류", e);
            stdErr.append(e.getMessage());
            if (logConsumer != null) logConsumer.accept("[ERROR] " + e.getMessage());
        }
        return new ProcessResult(exitCode, stdOut.toString(), stdErr.toString());
    }

    private String buildRepoUrl(GitRepo gitRepo) {
        if (gitRepo.getAuthType() == GitRepo.AuthType.PASSWORD
                && gitRepo.getUsername() != null && gitRepo.getPassword() != null) {
            // http(s)://username:password@host/repo 형태로 조합
            return RemoteCommandBuilder.injectHttpCredentials(
                    gitRepo.getRepoUrl(), gitRepo.getUsername(), gitRepo.getPassword());
        }
        return gitRepo.getRepoUrl();
    }

    /**
     * SSH 인증일 때 GIT_SSH_COMMAND 환경변수를 반환한다.
     * StrictHostKeyChecking=no 로 폐쇄망 최초 접속 시 known_hosts 확인을 건너뛴다.
     */
    private java.util.Map<String, String> buildSshEnv(GitRepo gitRepo) {
        if (gitRepo.getAuthType() == GitRepo.AuthType.SSH && gitRepo.getSshKeyPath() != null) {
            String sshCmd = "ssh -i " + gitRepo.getSshKeyPath()
                    + " -o StrictHostKeyChecking=no"
                    + " -o UserKnownHostsFile=/dev/null";
            java.util.Map<String, String> env = new java.util.HashMap<>();
            env.put("GIT_SSH_COMMAND", sshCmd);
            return env;
        }
        return java.util.Collections.emptyMap();
    }

    private ProcessResult execute(List<String> cmd, File workDir, java.util.Map<String, String> extraEnv) {
        StringBuilder stdOut = new StringBuilder();
        StringBuilder stdErr = new StringBuilder();
        int exitCode = -1;

        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            if (workDir != null) pb.directory(workDir);
            if (!extraEnv.isEmpty()) pb.environment().putAll(extraEnv);
            pb.redirectErrorStream(false);
            Process process = pb.start();

            Thread outThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) stdOut.append(line).append("\n");
                } catch (Exception ignored) {}
            });

            Thread errThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getErrorStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) stdErr.append(line).append("\n");
                } catch (Exception ignored) {}
            });

            outThread.start();
            errThread.start();
            outThread.join();
            errThread.join();

            exitCode = process.waitFor();
            log.info("Git 완료 - exitCode: {}", exitCode);

        } catch (Exception e) {
            log.error("Git 실행 오류", e);
            stdErr.append(e.getMessage());
        }

        return new ProcessResult(exitCode, stdOut.toString(), stdErr.toString());
    }
}
