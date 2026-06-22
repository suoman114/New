package com.lter.infra.util;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

@Slf4j
@Component
public class ScriptExecutor {

    public ProcessResult runRemote(String targetIp, String scriptPath, String serverName) {
        return runRemote(targetIp, scriptPath, serverName, null, null, null);
    }

    public ProcessResult runRemote(String targetIp, String scriptPath, String serverName,
                                   Consumer<String> logConsumer) {
        return runRemote(targetIp, scriptPath, serverName, null, null, logConsumer);
    }

    public ProcessResult runRemote(String targetIp, String scriptPath, String serverName,
                                   String scriptArgs, Consumer<String> logConsumer) {
        return runRemote(targetIp, scriptPath, serverName, scriptArgs, null, logConsumer);
    }

    public ProcessResult runRemote(String targetIp, String scriptPath, String serverName,
                                   String scriptArgs, String sshPassword, Consumer<String> logConsumer) {
        List<String> cmd = new ArrayList<>();
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            cmd.add("sshpass");
            cmd.add("-p");
            cmd.add(sshPassword);
        }
        cmd.add("ssh");
        cmd.add("-o"); cmd.add("StrictHostKeyChecking=no");
        cmd.add("-o"); cmd.add("ConnectTimeout=10");
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            cmd.add("-o"); cmd.add("PubkeyAuthentication=no");
            cmd.add("-o"); cmd.add("PreferredAuthentications=password");
        }
        cmd.add("root@" + targetIp);

        StringBuilder remoteCmd = new StringBuilder("bash ").append(scriptPath);
        if (scriptArgs != null && !scriptArgs.trim().isEmpty()) {
            remoteCmd.append(" ").append(scriptArgs.trim());
        } else {
            remoteCmd.append(" '").append(serverName).append("'");
        }
        cmd.add(remoteCmd.toString());

        log.info("스크립트 원격 실행: {} @ {} args=[{}]", scriptPath, targetIp, scriptArgs);
        return execute(cmd, logConsumer);
    }

    public ProcessResult copyScript(String localScriptPath, String targetIp, String remotePath) {
        return copyScript(localScriptPath, targetIp, remotePath, null);
    }

    public ProcessResult copyScript(String localScriptPath, String targetIp, String remotePath, String sshPassword) {
        // 원격 디렉토리 생성 (없으면 scp 실패)
        String remoteDir = remotePath.substring(0, remotePath.lastIndexOf('/'));
        List<String> mkdirCmd = new ArrayList<>();
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            mkdirCmd.add("sshpass"); mkdirCmd.add("-p"); mkdirCmd.add(sshPassword);
        }
        mkdirCmd.add("ssh");
        mkdirCmd.add("-o"); mkdirCmd.add("StrictHostKeyChecking=no");
        mkdirCmd.add("-o"); mkdirCmd.add("ConnectTimeout=10");
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            mkdirCmd.add("-o"); mkdirCmd.add("PubkeyAuthentication=no");
            mkdirCmd.add("-o"); mkdirCmd.add("PreferredAuthentications=password");
        }
        mkdirCmd.add("root@" + targetIp);
        mkdirCmd.add("mkdir -p " + remoteDir);
        execute(mkdirCmd, null);

        List<String> cmd = new ArrayList<>();
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            cmd.add("sshpass"); cmd.add("-p"); cmd.add(sshPassword);
        }
        cmd.add("scp");
        cmd.add("-o"); cmd.add("StrictHostKeyChecking=no");
        if (sshPassword != null && !sshPassword.trim().isEmpty()) {
            cmd.add("-o"); cmd.add("PubkeyAuthentication=no");
            cmd.add("-o"); cmd.add("PreferredAuthentications=password");
        }
        cmd.add(localScriptPath);
        cmd.add("root@" + targetIp + ":" + remotePath);

        log.info("스크립트 전송: {} -> {}:{}", localScriptPath, targetIp, remotePath);
        return execute(cmd, null);
    }

    public ValidationSummary parseValidationResult(String stdOut) {
        int ok = 0, warn = 0, fail = 0;
        for (String line : stdOut.split("\n")) {
            if      (line.contains("[OK]"))   ok++;
            else if (line.contains("[WARN]")) warn++;
            else if (line.contains("[MISS]")) warn++;   // os_audit 전용 태그, warn으로 집계
            else if (line.contains("[FAIL]")) fail++;
        }
        return new ValidationSummary(ok, warn, fail);
    }

    private ProcessResult execute(List<String> cmd, Consumer<String> logConsumer) {
        StringBuilder stdOut = new StringBuilder();
        StringBuilder stdErr = new StringBuilder();
        int exitCode = -1;

        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(false);
            Process process = pb.start();

            Thread outThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        stdOut.append(line).append("\n");
                        if (logConsumer != null) logConsumer.accept(line);
                    }
                } catch (Exception ignored) {}
            });

            Thread errThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getErrorStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        stdErr.append(line).append("\n");
                        if (logConsumer != null) logConsumer.accept("[ERR] " + line);
                    }
                } catch (Exception ignored) {}
            });

            outThread.start();
            errThread.start();
            outThread.join();
            errThread.join();

            exitCode = process.waitFor();
            log.info("스크립트 완료 - exitCode: {}", exitCode);

        } catch (Exception e) {
            log.error("스크립트 실행 오류", e);
            stdErr.append(e.getMessage());
            if (logConsumer != null) logConsumer.accept("[ERROR] " + e.getMessage());
        }

        return new ProcessResult(exitCode, stdOut.toString(), stdErr.toString());
    }

    @lombok.Getter
    @lombok.AllArgsConstructor
    public static class ValidationSummary {
        private final int ok;
        private final int warn;
        private final int fail;

        public boolean isPassed() {
            return fail == 0;
        }
    }
}
