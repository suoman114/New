package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.PackageRequest;
import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.PkgInfo;
import com.lter.infra.service.PackageService;
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
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

@RestController
@RequestMapping("/api/v1/packages")
@RequiredArgsConstructor
public class PackageController {

    private final PackageService packageService;
    private final SystemConfigService systemConfigService;

    @GetMapping
    public ResponseEntity<ApiResponse<List<PkgInfo>>> list() {
        return ResponseEntity.ok(ApiResponse.ok(packageService.findAll()));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<PkgInfo>> register(@Valid @RequestBody PackageRequest request) {
        PkgInfo saved = packageService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok("패키지가 등록되었습니다.", saved));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<PkgInfo>> get(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(packageService.findById(id)));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<PkgInfo>> update(@PathVariable Long id,
                                                        @Valid @RequestBody PackageRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("패키지가 수정되었습니다.", packageService.update(id, request)));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(@PathVariable Long id) {
        packageService.delete(id);
        return ResponseEntity.ok(ApiResponse.ok("패키지가 삭제되었습니다.", null));
    }

    /** 패키지 경로의 파일 목록 (tar.gz / gz / zip) */
    @GetMapping("/files")
    public ResponseEntity<ApiResponse<List<String>>> listFiles() {
        String dir = systemConfigService.get(InfraConfig.PACKAGE_BASE_DIR);
        File base = new File(dir);
        if (!base.exists() || !base.isDirectory()) {
            return ResponseEntity.ok(ApiResponse.ok(Collections.emptyList()));
        }
        File[] files = base.listFiles(f -> f.isFile() && isArchive(f.getName()));
        if (files == null) return ResponseEntity.ok(ApiResponse.ok(Collections.emptyList()));
        List<String> names = new ArrayList<>();
        for (File f : files) names.add(f.getName());
        Collections.sort(names);
        return ResponseEntity.ok(ApiResponse.ok(names));
    }

    /** 패키지 파일 업로드 */
    @PostMapping("/upload")
    public ResponseEntity<ApiResponse<String>> upload(@RequestParam("file") MultipartFile file) throws IOException {
        String dir = systemConfigService.get(InfraConfig.PACKAGE_BASE_DIR);
        File base = new File(dir);
        if (!base.exists()) base.mkdirs();
        String filename = file.getOriginalFilename();
        if (filename == null || !isArchive(filename)) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("tar.gz / gz / zip 파일만 업로드 가능합니다."));
        }
        file.transferTo(new File(base, filename));
        return ResponseEntity.ok(ApiResponse.ok("업로드 완료: " + filename, filename));
    }

    private boolean isArchive(String name) {
        return name.endsWith(".tar.gz") || name.endsWith(".tgz")
                || name.endsWith(".gz") || name.endsWith(".zip");
    }
}
