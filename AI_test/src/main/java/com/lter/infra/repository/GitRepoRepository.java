package com.lter.infra.repository;

import com.lter.infra.domain.entity.GitRepo;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface GitRepoRepository extends JpaRepository<GitRepo, Long> {

    List<GitRepo> findByRepoType(GitRepo.RepoType repoType);
}
