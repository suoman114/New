package com.lter.infra.service;

import com.lter.infra.domain.dto.PackageRequest;
import com.lter.infra.domain.entity.GitRepo;
import com.lter.infra.domain.entity.PkgInfo;
import com.lter.infra.repository.GitRepoRepository;
import com.lter.infra.repository.PkgInfoRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
public class PackageService {

    private final PkgInfoRepository pkgInfoRepository;
    private final GitRepoRepository gitRepoRepository;

    @Transactional
    public PkgInfo register(PackageRequest request) {
        PkgInfo pkg = new PkgInfo();
        pkg.setPackageName(request.getPackageName());
        pkg.setVersion(request.getVersion());
        pkg.setGitPath(request.getGitPath());
        pkg.setLocalPath(request.getLocalPath());
        pkg.setTargetOs(request.getTargetOs());
        pkg.setDescription(request.getDescription());

        if (request.getGitRepoId() != null) {
            GitRepo gitRepo = gitRepoRepository.findById(request.getGitRepoId())
                    .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + request.getGitRepoId()));
            pkg.setGitRepo(gitRepo);
        }

        return pkgInfoRepository.save(pkg);
    }

    @Transactional(readOnly = true)
    public List<PkgInfo> findAll() {
        return pkgInfoRepository.findAll();
    }

    @Transactional(readOnly = true)
    public PkgInfo findById(Long id) {
        return pkgInfoRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("패키지를 찾을 수 없습니다. id=" + id));
    }

    @Transactional
    public PkgInfo update(Long id, PackageRequest request) {
        PkgInfo pkg = findById(id);
        pkg.setPackageName(request.getPackageName());
        pkg.setVersion(request.getVersion());
        pkg.setGitPath(request.getGitPath());
        pkg.setLocalPath(request.getLocalPath());
        pkg.setTargetOs(request.getTargetOs());
        pkg.setDescription(request.getDescription());

        if (request.getGitRepoId() != null) {
            GitRepo gitRepo = gitRepoRepository.findById(request.getGitRepoId())
                    .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + request.getGitRepoId()));
            pkg.setGitRepo(gitRepo);
        } else {
            pkg.setGitRepo(null);
        }

        return pkgInfoRepository.save(pkg);
    }

    @Transactional
    public void delete(Long id) {
        pkgInfoRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("패키지를 찾을 수 없습니다. id=" + id));
        pkgInfoRepository.deleteById(id);
    }
}
