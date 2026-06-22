package com.lter.infra.repository;

import com.lter.infra.domain.entity.InfraConfig;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InfraConfigRepository extends JpaRepository<InfraConfig, String> {
}
