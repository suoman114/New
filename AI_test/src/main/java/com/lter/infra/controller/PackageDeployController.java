package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.service.PackageDeployService;
import com.lter.infra.service.SseLogService;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import lombok.Setter;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

@RestController
@RequestMapping("/api/v1/packages")
@RequiredArgsConstructor
public class PackageDeployController {

    private final PackageDeployService packageDeployService;
    private final SseLogService sseLogService;

    @PostMapping("/deploy")
    public ResponseEntity<ApiResponse<String>> deploy(@RequestBody DeployRequest request) {
        if (request.getServerId() == null) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("serverId는 필수입니다."));
        }
        if (request.getFileNames() == null || request.getFileNames().isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("배포할 파일을 선택해주세요."));
        }
        if (request.getRemotePath() == null || request.getRemotePath().trim().isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("원격 경로를 입력해주세요."));
        }
        int port = request.getSshPort() > 0 ? request.getSshPort() : 22;
        String jobKey = "pkg-deploy-" + request.getServerId() + "-" + System.currentTimeMillis();
        packageDeployService.deploy(request.getServerId(), request.getFileNames(),
                request.getRemotePath(), request.getSshPassword(), port, jobKey);
        return ResponseEntity.ok(ApiResponse.ok("패키지 배포가 시작되었습니다.", jobKey));
    }

    @GetMapping(value = "/deploy/log-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter logStream(@RequestParam String jobKey) {
        return sseLogService.subscribe(jobKey);
    }

    @Getter
    @Setter
    public static class DeployRequest {
        private Long serverId;
        private List<String> fileNames;
        private String remotePath;
        private String sshPassword;
        private int sshPort;
    }
}
