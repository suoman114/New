package com.lter.infra.domain.entity;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "target_server")
@Getter
@Setter
@NoArgsConstructor
public class TargetServer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String serverName;

    @Column(nullable = false, length = 50)
    private String ipAddress;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OsType osType;

    @Column(length = 50)
    private String osVersion;

    @Column(length = 200)
    private String description;

    @Column(length = 200)
    private String sshPassword;

    @Column(length = 100)
    private String kernelVersion;

    @Column(length = 100)
    private String cpuInfo;

    @Column(length = 50)
    private String memoryGb;

    @Column(length = 50)
    private String diskRootGb;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private ServerStatus status;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @Column
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        status = ServerStatus.REGISTERED;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public enum OsType {
        CENTOS, UBUNTU
    }

    public enum ServerStatus {
        REGISTERED, OS_SETUP_DONE, PKG_SETUP_DONE, VERIFIED, ERROR
    }
}
