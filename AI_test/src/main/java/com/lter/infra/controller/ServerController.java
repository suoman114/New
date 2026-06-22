package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.ServerRequest;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.service.ServerService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/servers")
@RequiredArgsConstructor
public class ServerController {

    private final ServerService serverService;

    @GetMapping
    public ResponseEntity<ApiResponse<List<TargetServer>>> findAll() {
        return ResponseEntity.ok(ApiResponse.ok(serverService.findAll()));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<TargetServer>> findById(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(serverService.findById(id)));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<TargetServer>> register(@Valid @RequestBody ServerRequest request) {
        TargetServer server = serverService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok("서버가 등록되었습니다.", server));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<TargetServer>> update(@PathVariable Long id,
                                                             @Valid @RequestBody ServerRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("서버 정보가 수정되었습니다.", serverService.update(id, request)));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        serverService.delete(id);
        return ResponseEntity.ok(ApiResponse.ok("서버가 삭제되었습니다.", null));
    }

    @PostMapping("/bulk")
    public ResponseEntity<ApiResponse<List<TargetServer>>> registerBulk(@Valid @RequestBody List<ServerRequest> requests) {
        if (requests == null || requests.isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("서버 목록이 비어있습니다."));
        }
        List<TargetServer> saved = serverService.registerBulk(requests);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok(saved.size() + "개 서버가 등록되었습니다.", saved));
    }

    @PostMapping("/{id}/ping")
    public ResponseEntity<ApiResponse<Map<String, Object>>> ping(
            @PathVariable Long id,
            @RequestBody(required = false) Map<String, String> body) {
        String password = body != null ? body.get("password") : null;
        int port = 22;
        try { if (body != null && body.get("port") != null) port = Integer.parseInt(body.get("port")); } catch (NumberFormatException ignored) {}
        return ResponseEntity.ok(ApiResponse.ok(serverService.sshPing(id, password, port)));
    }
}
