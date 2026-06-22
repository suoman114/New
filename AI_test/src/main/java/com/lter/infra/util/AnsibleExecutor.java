package com.lter.infra.util;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.service.SystemConfigService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

@Slf4j
@Component
@RequiredArgsConstructor
public class AnsibleExecutor {

    private final SystemConfigService systemConfigService;

    public ProcessResult runPlaybook(String playbookName, Map<String, String> extraVars) {
        return runPlaybook(playbookName, extraVars, null);
    }

    public ProcessResult runPlaybook(String playbookName, Map<String, String> extraVars,
                                     Consumer<String> logConsumer) {
        String playbookDir = systemConfigService.get(InfraConfig.ANSIBLE_PLAYBOOK_DIR);
        String inventory   = systemConfigService.get(InfraConfig.ANSIBLE_INVENTORY);

        String dir = playbookDir.replaceAll("/+$", ""); // trailing slash 제거

        List<String> cmd = new ArrayList<>();
        cmd.add("ansible-playbook");
        cmd.add(dir + "/" + playbookName);
        cmd.add("-i");
        cmd.add(inventory);

        if (extraVars != null && !extraVars.isEmpty()) {
            StringBuilder vars = new StringBuilder();
            extraVars.forEach((k, v) -> vars.append(k).append("=").append(v).append(" "));
            cmd.add("-e");
            cmd.add(vars.toString().trim());
        }

        String cmdStr = String.join(" ", cmd);
        log.info("Ansible 실행: {}", cmdStr);
        if (logConsumer != null) logConsumer.accept("[CMD] " + cmdStr);
        return execute(cmd, logConsumer);
    }

    private ProcessResult execute(List<String> cmd, Consumer<String> logConsumer) {
        StringBuilder stdOut = new StringBuilder();
        StringBuilder stdErr = new StringBuilder();
        int exitCode = -1;

        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(false);
            Process process = pb.start();

            // stdout 스트리밍 스레드
            Thread outThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        stdOut.append(line).append("\n");
                        if (logConsumer != null) logConsumer.accept(line);
                    }
                } catch (Exception ignored) {}
            });

            // stderr 스트리밍 스레드
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
            log.info("Ansible 완료 - exitCode: {}", exitCode);

        } catch (Exception e) {
            log.error("Ansible 실행 오류", e);
            stdErr.append(e.getMessage());
            if (logConsumer != null) logConsumer.accept("[ERROR] " + e.getMessage());
        }

        return new ProcessResult(exitCode, stdOut.toString(), stdErr.toString());
    }
}
