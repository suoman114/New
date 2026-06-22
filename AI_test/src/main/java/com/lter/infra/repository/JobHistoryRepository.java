package com.lter.infra.repository;

import com.lter.infra.domain.entity.JobHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;

public interface JobHistoryRepository extends JpaRepository<JobHistory, Long> {

    Page<JobHistory> findByTargetServerIdOrderByStartedAtDesc(Long serverId, Pageable pageable);

    List<JobHistory> findByTargetServerIdOrderByStartedAtDesc(Long serverId);

    List<JobHistory> findByJobTypeOrderByStartedAtDesc(JobHistory.JobType jobType);

    List<JobHistory> findByTargetServerIdAndJobTypeOrderByStartedAtDesc(Long serverId, JobHistory.JobType jobType);

    Page<JobHistory> findByTargetServerIdAndJobTypeOrderByStartedAtDesc(Long serverId, JobHistory.JobType jobType, Pageable pageable);

    List<JobHistory> findByTargetServerIdAndJobTypeAndStartedAtBetweenOrderByStartedAtDesc(
            Long serverId, JobHistory.JobType jobType, LocalDateTime from, LocalDateTime to);
}
