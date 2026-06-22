package com.lter.infra.domain.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.time.LocalDateTime;

/**
 * PipelineRun 내 각 단계(Step)의 실행 결과.
 * 대상 서버 1개 × Step 1개 = StepRun 1개.
 */
@Entity
@Table(name = "pipeline_step_run")
@Getter
@Setter
@NoArgsConstructor
public class PipelineStepRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "pipeline_run_id", nullable = false)
    private PipelineRun pipelineRun;

    @JsonProperty("pipelineRunId")
    public Long getPipelineRunId() { return pipelineRun != null ? pipelineRun.getId() : null; }

    @Column(nullable = false)
    private Integer stepOrder;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private PipelineStep.StepType stepType;

    /** 연결된 JobHistory ID (실제 실행 결과 참조용) */
    @Column
    private Long jobHistoryId;

    @Column(length = 100)
    private String serverName;

    @Column(length = 50)
    private String serverIp;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private StepRunStatus status;

    @Column(nullable = false)
    private LocalDateTime startedAt;

    @Column
    private LocalDateTime finishedAt;

    @PrePersist
    protected void onCreate() {
        startedAt = LocalDateTime.now();
        status = StepRunStatus.RUNNING;
    }

    public enum StepRunStatus {
        RUNNING, SUCCESS, FAIL, SKIPPED
    }
}
