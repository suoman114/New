package com.lter.infra.domain.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "job_history")
@Getter
@Setter
@NoArgsConstructor
@JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
public class JobHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "server_id")
    private TargetServer targetServer;

    @JsonProperty("serverId")
    public Long getServerId() {
        return targetServer != null ? targetServer.getId() : null;
    }

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private JobType jobType;

    @Column(length = 200)
    private String playbookName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private JobStatus status;

    @Column(columnDefinition = "TEXT")
    private String stdOut;

    @Column(columnDefinition = "TEXT")
    private String stdErr;

    @Column
    private Integer exitCode;

    @Column(nullable = false)
    private LocalDateTime startedAt;

    @Column
    private LocalDateTime finishedAt;

    @PrePersist
    protected void onCreate() {
        startedAt = LocalDateTime.now();
        status = JobStatus.RUNNING;
    }

    public enum JobType {
        OS_SETUP, PKG_SETUP, PKG_DEPLOY, VALIDATION, GIT_PULL
    }

    public enum JobStatus {
        RUNNING, SUCCESS, FAIL
    }
}
