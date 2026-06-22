package com.lter.infra.repository;

import com.lter.infra.domain.entity.PipelineRun;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PipelineRunRepository extends JpaRepository<PipelineRun, Long> {
    Page<PipelineRun> findByPipeline_IdOrderByStartedAtDesc(Long pipelineId, Pageable pageable);
    void deleteByPipeline_Id(Long pipelineId);
}
