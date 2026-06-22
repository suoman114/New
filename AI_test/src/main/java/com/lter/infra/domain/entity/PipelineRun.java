package com.lter.infra.domain.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

/**
 * Pipeline 1회 실행 인스턴스.
 * 각 실행은 여러 PipelineStepRun 을 가진다.
 */
@Entity
@Table(name = "pipeline_run")
@Getter
@Setter
@NoArgsConstructor
public class PipelineRun {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "pipeline_id", nullable = false)
    private Pipeline pipeline;

    /** 직렬화 시 Lazy 로딩 회피용 - 실행 생성 시점에 복사 저장 */
    @Column(length = 100)
    private String pipelineName;

    @JsonProperty("pipelineId")
    public Long getPipelineId() { return pipeline != null ? pipeline.getId() : null; }

    @JsonProperty("pipelineName")
    public String getPipelineName() { return pipelineName; }

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private RunStatus status;

    /** 현재 실행 중인 stepOrder (수동 모드에서 WAITING 일 때 참조) */
    @Column
    private Integer currentStepOrder;

    @Column(nullable = false)
    private LocalDateTime startedAt;

    @Column
    private LocalDateTime finishedAt;

    @OneToMany(mappedBy = "pipelineRun", cascade = CascadeType.ALL, orphanRemoval = true, fetch = FetchType.EAGER)
    @OrderBy("stepOrder ASC")
    private List<PipelineStepRun> stepRuns = new ArrayList<>();

    @PrePersist
    protected void onCreate() {
        startedAt = LocalDateTime.now();
        status = RunStatus.RUNNING;
    }

    public enum RunStatus {
        RUNNING,          // 실행 중
        WAITING_APPROVAL, // 수동 모드: 다음 단계 사용자 승인 대기
        SUCCESS,
        FAIL,
        CANCELLED
    }
}
