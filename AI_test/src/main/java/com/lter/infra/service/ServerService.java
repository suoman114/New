package com.lter.infra.service;

import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.domain.dto.ServerRequest;
import com.lter.infra.repository.TargetServerRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class ServerService {

    private final TargetServerRepository serverRepository;

    @Transactional
    public TargetServer register(ServerRequest request) {
        if (serverRepository.existsByIpAddress(request.getIpAddress())) {
            throw new IllegalArgumentException("이미 등록된 IP입니다: " + request.getIpAddress());
        }

        TargetServer server = new TargetServer();
        server.setServerName(request.getServerName());
        server.setIpAddress(request.getIpAddress());
        server.setOsType(request.getOsType());
        server.setOsVersion(request.getOsVersion());
        server.setDescription(request.getDescription());
        server.setSshPassword(request.getSshPassword());

        return serverRepository.save(server);
    }

    @Transactional(readOnly = true)
    public List<TargetServer> findAll() {
        return serverRepository.findAll();
    }

    @Transactional(readOnly = true)
    public TargetServer findById(Long id) {
        return serverRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("서버를 찾을 수 없습니다. id=" + id));
    }

    @Transactional
    public TargetServer update(Long id, ServerRequest request) {
        TargetServer server = findById(id);

        if (!server.getIpAddress().equals(request.getIpAddress())
                && serverRepository.existsByIpAddress(request.getIpAddress())) {
            throw new IllegalArgumentException("이미 등록된 IP입니다: " + request.getIpAddress());
        }

        server.setServerName(request.getServerName());
        server.setIpAddress(request.getIpAddress());
        server.setOsType(request.getOsType());
        server.setOsVersion(request.getOsVersion());
        server.setDescription(request.getDescription());
        server.setSshPassword(request.getSshPassword());

        return serverRepository.save(server);
    }

    @Transactional
    public void delete(Long id) {
        TargetServer server = findById(id);
        serverRepository.delete(server);
    }

    @Transactional
    public List<TargetServer> registerBulk(List<ServerRequest> requests) {
        List<TargetServer> saved = new ArrayList<>();
        for (int i = 0; i < requests.size(); i++) {
            ServerRequest req = requests.get(i);
            int row = i + 1;
            if (req.getServerName() == null || req.getServerName().trim().isEmpty()) {
                throw new IllegalArgumentException(row + "번째 행: 서버명이 비어있습니다.");
            }
            if (req.getIpAddress() == null || req.getIpAddress().trim().isEmpty()) {
                throw new IllegalArgumentException(row + "번째 행: IP 주소가 비어있습니다.");
            }
            if (!req.getIpAddress().matches("^((25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.){3}(25[0-5]|2[0-4]\\d|[01]?\\d\\d?)$")) {
                throw new IllegalArgumentException(row + "번째 행: IP 주소 형식이 올바르지 않습니다. (" + req.getIpAddress() + ")");
            }
            if (serverRepository.existsByIpAddress(req.getIpAddress())) {
                throw new IllegalArgumentException("이미 등록된 IP입니다: " + req.getIpAddress());
            }
            TargetServer server = new TargetServer();
            server.setServerName(req.getServerName());
            server.setIpAddress(req.getIpAddress());
            server.setOsType(req.getOsType());
            server.setOsVersion(req.getOsVersion());
            server.setDescription(req.getDescription());
            server.setSshPassword(req.getSshPassword());
            saved.add(serverRepository.save(server));
        }
        return saved;
    }

    public Map<String, Object> sshPing(Long id, String password, int port) {
        TargetServer server = findById(id);
        String ip = server.getIpAddress();

        // 1단계: TCP 포트 연결 확인
        boolean portOpen = false;
        String portMessage;
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(ip, port), 5000);
            portOpen = true;
            portMessage = "포트(" + port + ") 열림";
        } catch (java.net.SocketTimeoutException e) {
            portMessage = "포트(" + port + ") 타임아웃 (5초)";
        } catch (Exception e) {
            portMessage = "포트(" + port + ") 연결 거부됨";
        }

        // 2단계: SSH 인증 확인 (패스워드 있을 때만)
        boolean authOk = false;
        String authMessage;
        if (!portOpen) {
            authMessage = "포트 연결 실패로 인증 불가";
        } else if (password == null || password.trim().isEmpty()) {
            authMessage = "패스워드 미입력 (인증 미확인)";
        } else {
            try {
                List<String> cmd = new ArrayList<>();
                cmd.add("sshpass"); cmd.add("-p"); cmd.add(password);
                cmd.add("ssh");
                cmd.add("-o"); cmd.add("StrictHostKeyChecking=no");
                cmd.add("-o"); cmd.add("ConnectTimeout=5");
                cmd.add("-o"); cmd.add("BatchMode=no");
                // 키 인증 비활성화 → 패스워드 인증만 강제
                cmd.add("-o"); cmd.add("PubkeyAuthentication=no");
                cmd.add("-o"); cmd.add("PreferredAuthentications=password");
                cmd.add("-p"); cmd.add(String.valueOf(port));
                cmd.add("root@" + ip);
                cmd.add("echo ok");

                ProcessBuilder pb = new ProcessBuilder(cmd);
                pb.redirectErrorStream(true);
                Process process = pb.start();
                StringBuilder out = new StringBuilder();
                try (java.io.BufferedReader br = new java.io.BufferedReader(
                        new java.io.InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = br.readLine()) != null) out.append(line);
                }
                int exit = process.waitFor();
                String outStr = out.toString().toLowerCase();
                authOk = exit == 0 && out.toString().contains("ok");
                if (authOk) {
                    authMessage = "인증 성공";
                } else if (outStr.contains("permission denied") || outStr.contains("authentication failed")) {
                    authMessage = "인증 실패 (패스워드 오류)";
                } else {
                    authMessage = "SSH 응답 오류 (exit=" + exit + ")";
                }
            } catch (Exception e) {
                authMessage = "SSH 실행 오류: " + e.getMessage();
            }
        }

        // 인증 성공 시 시스템 정보 수집
        if (authOk && password != null && !password.trim().isEmpty()) {
            collectAndSaveSystemInfo(server, ip, password, port);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("serverId", id);
        result.put("ipAddress", ip);
        result.put("port", port);
        result.put("portOpen", portOpen);
        result.put("portMessage", portMessage);
        result.put("authOk", authOk);
        result.put("authMessage", authMessage);
        return result;
    }

    private void collectAndSaveSystemInfo(TargetServer server, String ip, String password, int port) {
        try {
            List<String> cmd = new ArrayList<>();
            cmd.add("sshpass"); cmd.add("-p"); cmd.add(password);
            cmd.add("ssh");
            cmd.add("-o"); cmd.add("StrictHostKeyChecking=no");
            cmd.add("-o"); cmd.add("ConnectTimeout=5");
            cmd.add("-o"); cmd.add("BatchMode=no");
            cmd.add("-o"); cmd.add("PubkeyAuthentication=no");
            cmd.add("-o"); cmd.add("PreferredAuthentications=password");
            cmd.add("-p"); cmd.add(String.valueOf(port));
            cmd.add("root@" + ip);
            cmd.add("uname -r && nproc && awk '/MemTotal/{printf \"%.2f\", $2/1024/1024}' /proc/meminfo && df / | awk 'NR==2{printf \"%.2f\", $2/1024/1024}'");

            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            Process proc = pb.start();
            List<String> lines = new ArrayList<>();
            try (java.io.BufferedReader br = new java.io.BufferedReader(
                    new java.io.InputStreamReader(proc.getInputStream()))) {
                String line;
                while ((line = br.readLine()) != null) {
                    String trimmed = line.trim();
                    if (!trimmed.isEmpty()) lines.add(trimmed);
                }
            }
            proc.waitFor();

            if (lines.size() >= 4) {
                server.setKernelVersion(lines.get(0));
                server.setCpuInfo(lines.get(1) + " vCPU(s)");
                server.setMemoryGb(lines.get(2) + " GB");
                server.setDiskRootGb(lines.get(3) + " GB");
                serverRepository.save(server);
                log.info("시스템 정보 수집 완료: {}", ip);
            } else {
                log.warn("시스템 정보 수집 결과 부족 ({}줄): {}", lines.size(), ip);
            }
        } catch (Exception e) {
            log.warn("시스템 정보 수집 실패 [{}]: {}", ip, e.getMessage());
        }
    }

    @Transactional
    public void updateStatus(Long id, TargetServer.ServerStatus status) {
        TargetServer server = findById(id);
        server.setStatus(status);
        serverRepository.save(server);
    }
}
