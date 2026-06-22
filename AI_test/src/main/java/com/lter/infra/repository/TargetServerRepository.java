package com.lter.infra.repository;

import com.lter.infra.domain.entity.TargetServer;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface TargetServerRepository extends JpaRepository<TargetServer, Long> {

    Optional<TargetServer> findByIpAddress(String ipAddress);

    List<TargetServer> findByOsType(TargetServer.OsType osType);

    List<TargetServer> findByStatus(TargetServer.ServerStatus status);

    boolean existsByIpAddress(String ipAddress);
}
