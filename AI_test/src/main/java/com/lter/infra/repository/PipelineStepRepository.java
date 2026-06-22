package com.lter.infra.repository;

import com.lter.infra.domain.entity.PipelineStep;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PipelineStepRepository extends JpaRepository<PipelineStep, Long> {
    List<PipelineStep> findByPipeline_IdOrderByStepOrderAsc(Long pipelineId);
}
