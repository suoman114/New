package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.service.SystemConfigService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/config")
@RequiredArgsConstructor
public class SystemConfigController {

    private final SystemConfigService systemConfigService;

    @GetMapping
    public ResponseEntity<ApiResponse<List<InfraConfig>>> getAll() {
        return ResponseEntity.ok(ApiResponse.ok(systemConfigService.findAll()));
    }

    @PutMapping("/{key}")
    public ResponseEntity<ApiResponse<InfraConfig>> update(@PathVariable String key,
                                                            @RequestBody Map<String, String> body) {
        String value = body.get("value");
        if (value == null || value.trim().isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.fail("value 필드는 필수입니다."));
        }
        return ResponseEntity.ok(ApiResponse.ok("설정이 저장되었습니다.", systemConfigService.update(key, value)));
    }

    @PutMapping
    public ResponseEntity<ApiResponse<Void>> updateAll(@RequestBody Map<String, String> entries) {
        systemConfigService.updateAll(entries);
        return ResponseEntity.ok(ApiResponse.ok("설정이 저장되었습니다.", null));
    }
}
