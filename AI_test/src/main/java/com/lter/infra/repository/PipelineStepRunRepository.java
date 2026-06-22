package com.lter.infra.repository;

import com.lter.infra.domain.entity.PipelineStepRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PipelineStepRunRepository extends JpaRepository<PipelineStepRun, Long> {
    List<PipelineStepRun> findByPipelineRun_IdOrderByStepOrderAsc(Long id);
}
