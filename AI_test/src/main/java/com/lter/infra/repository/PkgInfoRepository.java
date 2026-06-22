package com.lter.infra.repository;

import com.lter.infra.domain.entity.PkgInfo;
import com.lter.infra.domain.entity.TargetServer;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PkgInfoRepository extends JpaRepository<PkgInfo, Long> {

    List<PkgInfo> findByTargetOs(TargetServer.OsType targetOs);
}
