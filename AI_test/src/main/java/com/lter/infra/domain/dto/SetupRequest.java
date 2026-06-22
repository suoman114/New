package com.lter.infra.domain.dto;

import lombok.Getter;
import lombok.Setter;

import java.util.List;

@Getter
@Setter
public class SetupRequest {

    /** 대상 서버 ID 목록 (다중 선택) */
    private List<Long> serverIds;

    /** OS 셋업용: NTP 서버 IP (4_ntp.yml 에 -e 로 전달) */
    private String ntpServer;

    /** OS 셋업용: 서버별 SSH root 패스워드 (serverId -> password) */
    private java.util.Map<Long, String> sshPasswords;

    /** PKG 셋업용: MariaDB root 비밀번호 (8-1_mariaDB.yml) */
    private String mariaDbPassword;

    /** PKG 셋업용: 초기 DB 이름 (8-1_mariaDB.yml) */
    private String databaseName;

    /** 실행할 playbook 이름 목록. null 이면 전체 실행 */
    private List<String> selectedPlaybooks;

    /** 특정 playbook 부터 재실행. null 이면 처음부터 */
    private String resumeFrom;

    /** true 이면 playbook 실패 시에도 다음 playbook 계속 실행 */
    private boolean continueOnFailure;
}
