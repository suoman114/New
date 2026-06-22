package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.GitRepoRequest;
import com.lter.infra.domain.entity.GitRepo;
import com.lter.infra.service.GitService;
import com.lter.infra.service.SseLogService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import javax.validation.Valid;
import java.util.List;

@RestController
@RequestMapping("/api/v1/git")
@RequiredArgsConstructor
public class GitController {

    private final GitService gitService;
    private final SseLogService sseLogService;

    @GetMapping("/repos")
    public ResponseEntity<ApiResponse<List<GitRepo>>> list() {
        return ResponseEntity.ok(ApiResponse.ok(gitService.findAll()));
    }

    @PostMapping("/repos")
    public ResponseEntity<ApiResponse<GitRepo>> register(@Valid @RequestBody GitRepoRequest request) {
        GitRepo saved = gitService.register(request.toEntity());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok("Git 저장소가 등록되었습니다.", saved));
    }

    @GetMapping("/repos/{id}")
    public ResponseEntity<ApiResponse<GitRepo>> get(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(gitService.findById(id)));
    }

    @PutMapping("/repos/{id}")
    public ResponseEntity<ApiResponse<GitRepo>> update(@PathVariable Long id, @Valid @RequestBody GitRepoRequest request) {
        GitRepo updated = gitService.update(id, request.toEntity());
        return ResponseEntity.ok(ApiResponse.ok("Git 저장소가 수정되었습니다.", updated));
    }

    @DeleteMapping("/repos/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        gitService.delete(id);
        return ResponseEntity.ok(ApiResponse.ok("Git 저장소가 삭제되었습니다.", null));
    }

    @PostMapping("/repos/{id}/pull")
    public ResponseEntity<ApiResponse<String>> pull(@PathVariable Long id) {
        String jobKey = "git-pull-" + id + "-" + System.currentTimeMillis();
        gitService.pullWithStream(id, jobKey);
        return ResponseEntity.ok(ApiResponse.ok("Git pull이 시작되었습니다.", jobKey));
    }

    @GetMapping(value = "/repos/{id}/log-stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter logStream(@PathVariable Long id, @RequestParam String jobKey) {
        return sseLogService.subscribe(jobKey);
    }
}
