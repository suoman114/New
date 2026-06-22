package com.lter.infra.domain.dto;

import com.lter.infra.domain.entity.Script;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Getter
@Setter
public class ScriptRequest {

    @NotBlank(message = "스크립트 이름은 필수입니다.")
    private String scriptName;

    @NotBlank(message = "로컬 경로는 필수입니다.")
    private String localPath;

    private String gitPath;

    private Long gitRepoId;

    @NotNull(message = "스크립트 타입은 필수입니다.")
    private Script.ScriptType scriptType;

    private String description;
}
