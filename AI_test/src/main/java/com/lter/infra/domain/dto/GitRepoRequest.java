package com.lter.infra.domain.dto;

import com.lter.infra.domain.entity.GitRepo;
import lombok.Getter;
import lombok.Setter;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;

@Getter
@Setter
public class GitRepoRequest {

    @NotBlank(message = "저장소 이름은 필수입니다.")
    private String repoName;

    @NotBlank(message = "저장소 URL은 필수입니다.")
    private String repoUrl;

    @NotBlank(message = "브랜치는 필수입니다.")
    private String branch;

    @NotNull(message = "인증 방식은 필수입니다.")
    private GitRepo.AuthType authType;

    private String username;

    private String password;

    private String sshKeyPath;

    @NotBlank(message = "로컬 저장 경로는 필수입니다.")
    private String localPath;

    @NotNull(message = "저장소 타입은 필수입니다.")
    private GitRepo.RepoType repoType;

    private String description;

    public GitRepo toEntity() {
        GitRepo repo = new GitRepo();
        repo.setRepoName(this.repoName);
        repo.setRepoUrl(this.repoUrl);
        repo.setBranch(this.branch);
        repo.setAuthType(this.authType);
        repo.setUsername(this.username);
        repo.setPassword(this.password);
        repo.setSshKeyPath(this.sshKeyPath);
        repo.setLocalPath(this.localPath);
        repo.setRepoType(this.repoType);
        repo.setDescription(this.description);
        return repo;
    }
}
