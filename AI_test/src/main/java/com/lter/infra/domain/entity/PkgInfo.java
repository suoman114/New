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
@Table(name = "package")
@Getter
@Setter
@NoArgsConstructor
@JsonIgnoreProperties({"hibernateLazyInitializer", "handler"})
public class PkgInfo {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String packageName;

    @Column(nullable = false, length = 50)
    private String version;

    @Column(length = 200)
    private String gitPath;

    @JsonIgnore
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "git_repo_id")
    private GitRepo gitRepo;

    @JsonProperty("gitRepoId")
    public Long getGitRepoId() {
        return gitRepo != null ? gitRepo.getId() : null;
    }

    @Column(nullable = false, length = 500)
    private String localPath;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private TargetServer.OsType targetOs;

    @Column(length = 200)
    private String description;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @Column
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }
}
