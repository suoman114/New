package com.lter.infra.domain.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "pipeline_step")
@Getter
@Setter
@NoArgsConstructor
public class PipelineStep {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "pipeline_id", nullable = false)
    private Pipeline pipeline;

    @Column(nullable = false)
    private Integer stepOrder;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private StepType stepType;

    /** 선택된 playbook 목록 (쉼표 구분). null = 전체 실행 */
    @Column(columnDefinition = "TEXT")
    private String selectedPlaybooks;

    /** OS 셋업 전용: NTP 서버 IP */
    @Column(length = 50)
    private String ntpServer;

    /** PKG 셋업 전용: MariaDB 비밀번호 */
    @Column(length = 100)
    private String mariaDbPassword;

    /** PKG 셋업 전용: DB 이름 */
    @Column(length = 100)
    private String databaseName;

    /** PKG 셋업 전용: 배포할 패키지 파일명 목록 (쉼표 구분) */
    @Column(columnDefinition = "TEXT")
    private String selectedPackages;

    /** PKG 셋업 전용: 원격 서버 배포 경로 */
    @Column(length = 200)
    private String remoteDeployPath;

    /** Validation 전용: Script ID */
    @Column
    private Long scriptId;

    /** Validation 전용: 스크립트 실행 인자 (선택) */
    @Column(length = 500)
    private String scriptArgs;

    /** 이 단계에 연결된 대상 서버 ID 목록 (쉼표 구분) */
    @Column(columnDefinition = "TEXT")
    private String serverIds;

    public enum StepType {
        OS_SETUP, PKG_SETUP, VALIDATION
    }

    // ── 편의 메서드 ──────────────────────────────────────

    public List<String> getSelectedPlaybookList() {
        return splitToList(selectedPlaybooks);
    }

    public List<Long> getServerIdList() {
        List<Long> ids = new ArrayList<>();
        if (serverIds != null && !serverIds.trim().isEmpty()) {
            for (String s : serverIds.split(",")) {
                try { ids.add(Long.parseLong(s.trim())); } catch (NumberFormatException ignored) {}
            }
        }
        return ids;
    }

    public List<String> getSelectedPackageList() {
        return splitToList(selectedPackages);
    }

    public void setSelectedPackageList(List<String> list) {
        this.selectedPackages = (list == null || list.isEmpty()) ? null : String.join(",", list);
    }

    public void setSelectedPlaybookList(List<String> list) {
        this.selectedPlaybooks = (list == null || list.isEmpty()) ? null : String.join(",", list);
    }

    public void setServerIdList(List<Long> list) {
        if (list == null || list.isEmpty()) { this.serverIds = null; return; }
        StringBuilder sb = new StringBuilder();
        for (Long id : list) { if (sb.length() > 0) sb.append(","); sb.append(id); }
        this.serverIds = sb.toString();
    }

    private List<String> splitToList(String csv) {
        List<String> result = new ArrayList<>();
        if (csv != null && !csv.trim().isEmpty()) {
            for (String s : csv.split(",")) {
                String t = s.trim();
                if (!t.isEmpty()) result.add(t);
            }
        }
        return result;
    }
}
