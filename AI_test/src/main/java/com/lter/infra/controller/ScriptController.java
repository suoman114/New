package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.ScriptRequest;
import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.Script;
import com.lter.infra.service.ScriptService;
import com.lter.infra.service.SystemConfigService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import javax.validation.Valid;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@RestController
@RequestMapping("/api/v1/scripts")
@RequiredArgsConstructor
public class ScriptController {

    private final ScriptService scriptService;
    private final SystemConfigService systemConfigService;

    @GetMapping
    public ResponseEntity<ApiResponse<List<Script>>> list() {
        return ResponseEntity.ok(ApiResponse.ok(scriptService.findAll()));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<Script>> register(@Valid @RequestBody ScriptRequest request) {
        Script saved = scriptService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok("스크립트가 등록되었습니다.", saved));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<Script>> get(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(scriptService.findById(id)));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<Script>> update(@PathVariable Long id,
                                                       @Valid @RequestBody ScriptRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("스크립트가 수정되었습니다.", scriptService.update(id, request)));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        scriptService.delete(id);
        return ResponseEntity.ok(ApiResponse.ok("스크립트가 삭제되었습니다.", null));
    }

    /** 스크립트 경로의 .sh 파일 목록 */
    @GetMapping("/files")
    public ResponseEntity<ApiResponse<List<String>>> listFiles() {
        String dir = systemConfigService.get(InfraConfig.SCRIPT_BASE_DIR);
        File base = new File(dir);
        if (!base.exists() || !base.isDirectory()) {
            return ResponseEntity.ok(ApiResponse.ok(Collections.emptyList()));
        }
        File[] files = base.listFiles(f -> f.isFile() && f.getName().endsWith(".sh"));
        if (files == null) return ResponseEntity.ok(ApiResponse.ok(Collections.emptyList()));
        List<String> names = new ArrayList<>();
        for (File f : files) names.add(f.getName());
        Collections.sort(names);
        return ResponseEntity.ok(ApiResponse.ok(names));
    }

    /** 파일시스템 .sh 목록을 DB에 동기화 (미등록 파일 자동 등록) */
    @PostMapping("/sync")
    public ResponseEntity<ApiResponse<List<Script>>> sync() {
        scriptService.syncFromFilesystem();
        return ResponseEntity.ok(ApiResponse.ok(scriptService.findAll()));
    }

    /** 스크립트 파일 업로드 → 스크립트 경로에 저장 */
    @PostMapping("/upload")
    public ResponseEntity<ApiResponse<String>> upload(@RequestParam MultipartFile file) throws IOException {
        String dir = systemConfigService.get(InfraConfig.SCRIPT_BASE_DIR);
        File base = new File(dir);
        if (!base.exists()) base.mkdirs();
        String filename = file.getOriginalFilename();
        if (filename == null || !filename.endsWith(".sh")) {
            return ResponseEntity.badRequest().body(ApiResponse.fail(".sh 파일만 업로드 가능합니다."));
        }
        file.transferTo(new File(base, filename));
        // 실행 권한 부여
        new File(base, filename).setExecutable(true, false);
        return ResponseEntity.ok(ApiResponse.ok("업로드 완료: " + filename, filename));
    }
}
