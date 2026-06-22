package com.lter.infra.domain.dto;

import lombok.Getter;
import lombok.Setter;

import java.util.Map;

@Getter
@Setter
public class PipelineRunRequest {
    /** 서버별 SSH root 패스워드: serverId(문자열) -> password */
    private Map<String, String> sshPasswords;
}
