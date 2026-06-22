package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.ApprovalRequest;
import com.lter.infra.domain.dto.PipelineRequest;
import com.lter.infra.domain.dto.PipelineRunRequest;
import com.lter.infra.domain.entity.Pipeline;
import com.lter.infra.domain.entity.PipelineRun;
import com.lter.infra.service.PipelineService;
import com.lter.infra.service.SseLogService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import javax.validation.Valid;
import java.util.List;

@RestController
@RequestMapping("/api/v1/pipelines")
@RequiredArgsConstructor
public class PipelineController {

    private final PipelineService pipelineService;
    private final SseLogService sseLogService;

    // ── CRUD ──────────────────────────────────────────

    @GetMapping
    public ResponseEntity<ApiResponse<List<Pipeline>>> list() {
        return ResponseEntity.ok(ApiResponse.ok(pipelineService.findAll()));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<Pipeline>> create(@Valid @RequestBody PipelineRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok("파이프라인이 생성되었습니다.", pipelineService.create(request)));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<Pipeline>> get(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(pipelineService.findById(id)));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<Pipeline>> update(@PathVariable Long id,
                                                         @Valid @RequestBody PipelineRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("파이프라인이 수정되었습니다.", pipelineService.update(id, request)));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        pipelineService.delete(id);
        return ResponseEntity.ok(ApiResponse.ok("파이프라인이 삭제되었습니다.", null));
    }

    // ── 실행 ──────────────────────────────────────────

    @PostMapping("/{id}/run")
    public ResponseEntity<ApiResponse<PipelineRun>> run(@PathVariable Long id,
                                                         @RequestBody(required = false) PipelineRunRequest request) {
        java.util.Map<Long, String> sshPasswords = (request != null && request.getSshPasswords() != null)
                ? parseSshPasswords(request.getSshPasswords()) : java.util.Collections.emptyMap();
        PipelineRun run = pipelineService.startRun(id, sshPasswords);
        return ResponseEntity.ok(ApiResponse.ok("파이프라인 실행이 시작되었습니다.", run));
    }

    /** JS에서 키가 문자열로 넘어오므로 Long으로 변환 */
    private java.util.Map<Long, String> parseSshPasswords(java.util.Map<String, String> raw) {
        java.util.Map<Long, String> result = new java.util.HashMap<>();
        raw.forEach((k, v) -> { try { result.put(Long.parseLong(k), v); } catch (NumberFormatException ignored) {} });
        return result;
    }

    @GetMapping("/{id}/runs")
    public ResponseEntity<ApiResponse<List<PipelineRun>>> runs(
            @PathVariable Long id,
            @RequestParam(defaultValue = "0") int page) {
        return ResponseEntity.ok(ApiResponse.ok(pipelineService.findRuns(id, page)));
    }

    @GetMapping("/runs/{runId}")
    public ResponseEntity<ApiResponse<PipelineRun>> getRun(@PathVariable Long runId) {
        return ResponseEntity.ok(ApiResponse.ok(pipelineService.findRunById(runId)));
    }

    /** 수동 모드: 다음 단계 승인 또는 취소 */
    @PostMapping("/runs/{runId}/approve")
    public ResponseEntity<ApiResponse<Void>> approve(@PathVariable Long runId,
                                                      @RequestBody ApprovalRequest request) {
        pipelineService.approve(runId, request.isApproved());
        String msg = request.isApproved() ? "다음 단계로 진행합니다." : "파이프라인 실행이 취소되었습니다.";
        return ResponseEntity.ok(ApiResponse.ok(msg, null));
    }

    // ── SSE 로그 스트림 ──────────────────────────────

    @GetMapping(value = "/runs/{runId}/log-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter logStream(@PathVariable Long runId) {
        return sseLogService.subscribe("pipeline-" + runId);
    }

    /** Setup Job SSE (단독 셋업 실행 시) */
    @GetMapping(value = "/jobs/{jobKey}/log-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter jobLogStream(@PathVariable String jobKey) {
        return sseLogService.subscribe("job-" + jobKey);
    }
}
