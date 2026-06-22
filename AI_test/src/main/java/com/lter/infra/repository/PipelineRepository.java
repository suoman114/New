package com.lter.infra.repository;

import com.lter.infra.domain.entity.Pipeline;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PipelineRepository extends JpaRepository<Pipeline, Long> {
}
