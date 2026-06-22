package com.lter.infra.domain.dto;

import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotNull;

@Getter
@Setter
public class ValidationRequest {

    @NotNull(message = "스크립트 ID는 필수입니다.")
    private Long scriptId;

    /** 스크립트 실행 시 전달할 추가 인자 (선택) */
    private String scriptArgs;
}
