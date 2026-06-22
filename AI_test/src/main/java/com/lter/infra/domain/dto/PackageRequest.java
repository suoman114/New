package com.lter.infra.domain.dto;

import com.lter.infra.domain.entity.TargetServer;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Getter
@Setter
public class PackageRequest {

    @NotBlank(message = "패키지 이름은 필수입니다.")
    private String packageName;

    @NotBlank(message = "버전은 필수입니다.")
    private String version;

    private String gitPath;

    private Long gitRepoId;

    @NotBlank(message = "로컬 경로는 필수입니다.")
    private String localPath;

    @NotNull(message = "대상 OS는 필수입니다.")
    private TargetServer.OsType targetOs;

    private String description;
}
