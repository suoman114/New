package com.lter.infra.service;

import com.lter.infra.domain.dto.ScriptRequest;
import com.lter.infra.domain.entity.GitRepo;
import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.domain.entity.Script;
import com.lter.infra.repository.GitRepoRepository;
import com.lter.infra.repository.ScriptRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.File;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class ScriptService {

    private final ScriptRepository scriptRepository;
    private final GitRepoRepository gitRepoRepository;
    private final SystemConfigService systemConfigService;

    @Transactional
    public Script register(ScriptRequest request) {
        Script script = new Script();
        script.setScriptName(request.getScriptName());
        script.setLocalPath(request.getLocalPath());
        script.setGitPath(request.getGitPath());
        script.setScriptType(request.getScriptType());
        script.setDescription(request.getDescription());

        if (request.getGitRepoId() != null) {
            GitRepo gitRepo = gitRepoRepository.findById(request.getGitRepoId())
                    .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + request.getGitRepoId()));
            script.setGitRepo(gitRepo);
        }

        return scriptRepository.save(script);
    }

    @Transactional(readOnly = true)
    public List<Script> findAll() {
        return scriptRepository.findAll();
    }

    @Transactional(readOnly = true)
    public Script findById(Long id) {
        return scriptRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("스크립트를 찾을 수 없습니다. id=" + id));
    }

    @Transactional
    public Script update(Long id, ScriptRequest request) {
        Script script = findById(id);
        script.setScriptName(request.getScriptName());
        script.setLocalPath(request.getLocalPath());
        script.setGitPath(request.getGitPath());
        script.setScriptType(request.getScriptType());
        script.setDescription(request.getDescription());

        if (request.getGitRepoId() != null) {
            GitRepo gitRepo = gitRepoRepository.findById(request.getGitRepoId())
                    .orElseThrow(() -> new IllegalArgumentException("Git Repo를 찾을 수 없습니다. id=" + request.getGitRepoId()));
            script.setGitRepo(gitRepo);
        } else {
            script.setGitRepo(null);
        }

        return scriptRepository.save(script);
    }

    @Transactional
    public void delete(Long id) {
        scriptRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("스크립트를 찾을 수 없습니다. id=" + id));
        scriptRepository.deleteById(id);
    }

    /**
     * 스크립트 경로의 .sh 파일을 DB에 자동 동기화 (미등록 파일만 추가).
     * 파일명으로 scriptName, localPath 설정, scriptType은 파일명으로 추론.
     */
    @Transactional
    public void syncFromFilesystem() {
        String dir = systemConfigService.get(InfraConfig.SCRIPT_BASE_DIR);
        File base = new File(dir);
        if (!base.exists() || !base.isDirectory()) return;

        File[] shFiles = base.listFiles(f -> f.isFile() && f.getName().endsWith(".sh"));
        if (shFiles == null) return;

        // 이미 등록된 localPath 목록
        Set<String> existing = scriptRepository.findAll().stream()
                .map(Script::getLocalPath)
                .collect(Collectors.toSet());

        for (File f : shFiles) {
            String localPath = f.getAbsolutePath();
            if (existing.contains(localPath)) continue;

            Script s = new Script();
            s.setScriptName(f.getName());
            s.setLocalPath(localPath);
            s.setScriptType(guessType(f.getName()));
            scriptRepository.save(s);
        }
    }

    private Script.ScriptType guessType(String filename) {
        String lower = filename.toLowerCase();
        if (lower.contains("audit")) return Script.ScriptType.OS_AUDIT;
        return Script.ScriptType.VCS_INSTALL_VERIFY;
    }
}
