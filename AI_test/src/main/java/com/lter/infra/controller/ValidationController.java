package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.domain.dto.ValidationRequest;
import com.lter.infra.domain.entity.JobHistory;
import com.lter.infra.service.ValidationService;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import lombok.Setter;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.validation.Valid;
import javax.validation.constraints.NotEmpty;
import javax.validation.constraints.NotNull;
import java.util.List;

@RestController
@RequestMapping("/api/v1/validation")
@RequiredArgsConstructor
public class ValidationController {

    private final ValidationService validationService;

    @PostMapping("/run/{serverId}")
    public ResponseEntity<ApiResponse<Void>> run(@PathVariable Long serverId,
                                                  @Valid @RequestBody ValidationRequest request) {
        validationService.runValidation(serverId, request);
        return ResponseEntity.ok(ApiResponse.ok("Validation이 시작되었습니다.", null));
    }

    @PostMapping("/run/batch")
    public ResponseEntity<ApiResponse<Void>> runBatch(@Valid @RequestBody BatchValidationRequest request) {
        validationService.runValidationBatch(request.getServerIds(), request.toValidationRequest());
        return ResponseEntity.ok(ApiResponse.ok("Validation이 시작되었습니다. (서버 " + request.getServerIds().size() + "대)", null));
    }

    @Getter
    @Setter
    public static class BatchValidationRequest {
        @NotEmpty(message = "서버를 최소 1개 이상 선택하세요.")
        private List<Long> serverIds;

        @NotNull(message = "스크립트 ID는 필수입니다.")
        private Long scriptId;

        private String scriptArgs;

        public ValidationRequest toValidationRequest() {
            ValidationRequest req = new ValidationRequest();
            req.setScriptId(scriptId);
            req.setScriptArgs(scriptArgs);
            return req;
        }
    }

    @GetMapping("/result/{jobId}")
    public ResponseEntity<ApiResponse<JobHistory>> getResult(@PathVariable Long jobId) {
        return ResponseEntity.ok(ApiResponse.ok(validationService.findResultById(jobId)));
    }

    @GetMapping("/history/{serverId}")
    public ResponseEntity<ApiResponse<List<JobHistory>>> getHistory(
            @PathVariable Long serverId,
            @RequestParam(defaultValue = "0") int page) {
        return ResponseEntity.ok(ApiResponse.ok(validationService.findHistory(serverId, page)));
    }
}
