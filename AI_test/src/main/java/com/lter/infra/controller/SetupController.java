package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.SetupRequest;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.service.SetupService;
import com.lter.infra.service.SseLogService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

@RestController
@RequestMapping("/api/v1/setup")
@RequiredArgsConstructor
public class SetupController {

    private final SetupService setupService;
    private final SseLogService sseLogService;

    @PostMapping("/all")
    public ResponseEntity<ApiResponse<String>> runSetupAll(@RequestBody(required = false) SetupRequest request) {
        SetupRequest req = request != null ? request : new SetupRequest();
        List<Long> serverIds = req.getServerIds();
        if (serverIds == null || serverIds.isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("serverIds는 필수입니다."));
        }
        String jobKey = "setup-all-" + System.currentTimeMillis();
        setupService.runSetupAllBatch(serverIds, req, jobKey);
        return ResponseEntity.ok(ApiResponse.ok("셋업이 시작되었습니다.", jobKey));
    }

    @GetMapping("/playbooks/all")
    public ResponseEntity<ApiResponse<List<String>>> allPlaybooks() {
        return ResponseEntity.ok(ApiResponse.ok(setupService.listAllPlaybooks()));
    }

    @PostMapping("/os")
    public ResponseEntity<ApiResponse<String>> runOsSetup(@RequestBody(required = false) SetupRequest request) {
        SetupRequest req = request != null ? request : new SetupRequest();
        List<Long> serverIds = req.getServerIds();
        if (serverIds == null || serverIds.isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("serverIds는 필수입니다."));
        }
        String jobKey = "setup-os-" + System.currentTimeMillis();
        setupService.runOsSetupBatch(serverIds, req, jobKey);
        return ResponseEntity.ok(ApiResponse.ok("OS 셋업이 시작되었습니다.", jobKey));
    }

    @PostMapping("/package")
    public ResponseEntity<ApiResponse<String>> runPkgSetup(@RequestBody(required = false) SetupRequest request) {
        SetupRequest req = request != null ? request : new SetupRequest();
        List<Long> serverIds = req.getServerIds();
        if (serverIds == null || serverIds.isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("serverIds는 필수입니다."));
        }
        String jobKey = "setup-pkg-" + System.currentTimeMillis();
        setupService.runPkgSetupBatch(serverIds, req, jobKey);
        return ResponseEntity.ok(ApiResponse.ok("PKG 셋업이 시작되었습니다.", jobKey));
    }

    @GetMapping(value = "/jobs/{jobKey}/log-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter logStream(@PathVariable String jobKey) {
        return sseLogService.subscribe(jobKey);
    }

    /** 하위 호환: 단일 서버 URL */
    @PostMapping("/os/{serverId}")
    public ResponseEntity<ApiResponse<Void>> runOsSetupLegacy(@PathVariable Long serverId,
                                                               @RequestBody(required = false) SetupRequest request) {
        SetupRequest req = request != null ? request : new SetupRequest();
        setupService.runOsSetup(serverId, req);
        return ResponseEntity.ok(ApiResponse.ok("OS 셋업이 시작되었습니다.", null));
    }

    @PostMapping("/package/{serverId}")
    public ResponseEntity<ApiResponse<Void>> runPkgSetupLegacy(@PathVariable Long serverId,
                                                                @RequestBody(required = false) SetupRequest request) {
        SetupRequest req = request != null ? request : new SetupRequest();
        setupService.runPkgSetup(serverId, req);
        return ResponseEntity.ok(ApiResponse.ok("PKG 셋업이 시작되었습니다.", null));
    }

    @GetMapping("/playbooks/os")
    public ResponseEntity<ApiResponse<List<String>>> osPlaybooks() {
        return ResponseEntity.ok(ApiResponse.ok(setupService.listOsPlaybooks()));
    }

    @GetMapping("/playbooks/pkg")
    public ResponseEntity<ApiResponse<List<String>>> pkgPlaybooks() {
        return ResponseEntity.ok(ApiResponse.ok(setupService.listPkgPlaybooks()));
    }

    @GetMapping("/status/{jobId}")
    public ResponseEntity<ApiResponse<JobHistory>> getJobStatus(@PathVariable Long jobId) {
        return ResponseEntity.ok(ApiResponse.ok(setupService.findJobById(jobId)));
    }

    @GetMapping("/history/{serverId}")
    public ResponseEntity<ApiResponse<List<JobHistory>>> getHistory(
            @PathVariable Long serverId,
            @RequestParam(defaultValue = "0") int page) {
        return ResponseEntity.ok(ApiResponse.ok(setupService.findJobsByServer(serverId, page)));
    }
}
