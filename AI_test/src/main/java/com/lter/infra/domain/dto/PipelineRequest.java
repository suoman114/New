package com.lter.infra.domain.dto;

import com.lter.infra.domain.entity.Pipeline;
import com.lter.infra.domain.entity.PipelineStep;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import java.util.List;

@Getter
@Setter
public class PipelineRequest {

    @NotBlank(message = "파이프라인 이름은 필수입니다.")
    private String name;

    private String description;

    @NotNull(message = "실행 모드는 필수입니다.")
    private Pipeline.ExecutionMode executionMode;

    @NotNull(message = "단계 목록은 필수입니다.")
    private List<StepDto> steps;

    @Getter
    @Setter
    public static class StepDto {

        @NotNull(message = "단계 순서는 필수입니다.")
        private Integer stepOrder;

        @NotNull(message = "단계 타입은 필수입니다.")
        private PipelineStep.StepType stepType;

        /** 대상 서버 ID 목록 */
        private List<Long> serverIds;

        /** 실행할 playbook 이름 목록 (null = 전체) */
        private List<String> selectedPlaybooks;

        /** OS 셋업: NTP 서버 IP */
        private String ntpServer;

        /** OS 셋업: 서버별 SSH root 패스워드 (serverId -> password) */
        private java.util.Map<Long, String> sshPasswords;

        /** PKG 셋업: MariaDB 비밀번호 */
        private String mariaDbPassword;

        /** PKG 셋업: DB 이름 */
        private String databaseName;

        /** PKG 셋업: 배포할 패키지 파일명 목록 */
        private List<String> selectedPackages;

        /** PKG 셋업: 원격 서버 배포 경로 */
        private String remoteDeployPath;

        /** Validation: 스크립트 ID */
        private Long scriptId;

        /** Validation: 스크립트 실행 인자 (선택) */
        private String scriptArgs;
    }
}
