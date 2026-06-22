package com.lter.infra.domain.dto;

import com.lter.infra.domain.entity.TargetServer;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Pattern;

@Getter
@Setter
public class ServerRequest {

    @NotBlank(message = "서버명은 필수입니다.")
    private String serverName;

    @NotBlank(message = "IP 주소는 필수입니다.")
    @Pattern(regexp = "^((25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.){3}(25[0-5]|2[0-4]\\d|[01]?\\d\\d?)$",
             message = "IP 주소 형식이 올바르지 않습니다.")
    private String ipAddress;

    @NotNull(message = "OS 타입은 필수입니다.")
    private TargetServer.OsType osType;

    private String osVersion;

    private String description;

    private String sshPassword;
}
