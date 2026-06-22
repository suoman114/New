package com.lter.infra.service;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.repository.InfraConfigRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import javax.annotation.PostConstruct;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class SystemConfigService {

    private final InfraConfigRepository configRepository;

    @Value("${infra.ansible.playbook-dir}")
    private String defaultPlaybookDir;

    @Value("${infra.ansible.inventory}")
    private String defaultInventory;

    @Value("${infra.script.local-base-dir}")
    private String defaultScriptDir;

    @Value("${infra.package.local-base-dir}")
    private String defaultPackageDir;

    @Value("${infra.git.local-base-dir}")
    private String defaultGitDir;

    /**
     * 앱 시작 시 DB에 기본값이 없으면 application.yml 값으로 초기화
     */
    @PostConstruct
    @Transactional
    public void init() {
        initIfAbsent(InfraConfig.ANSIBLE_PLAYBOOK_DIR, defaultPlaybookDir,  "Ansible playbook 디렉토리");
        initIfAbsent(InfraConfig.ANSIBLE_INVENTORY,    defaultInventory,     "Ansible inventory 파일 경로");
        initIfAbsent(InfraConfig.SCRIPT_BASE_DIR,      defaultScriptDir,     "Validation 스크립트 로컬 저장 경로");
        initIfAbsent(InfraConfig.PACKAGE_BASE_DIR,     defaultPackageDir,    "RPM 패키지 로컬 저장 경로");
        initIfAbsent(InfraConfig.GIT_BASE_DIR,         defaultGitDir,        "Git 저장소 로컬 기본 경로");
        log.info("시스템 설정 초기화 완료");
    }

    private void initIfAbsent(String key, String value, String desc) {
        if (!configRepository.existsById(key)) {
            configRepository.save(new InfraConfig(key, value, desc));
        }
    }

    @Transactional(readOnly = true)
    public List<InfraConfig> findAll() {
        return configRepository.findAll();
    }

    @Transactional(readOnly = true)
    public String get(String key) {
        return configRepository.findById(key)
                .map(InfraConfig::getConfigValue)
                .orElseThrow(() -> new IllegalStateException("설정을 찾을 수 없습니다: " + key));
    }

    @Transactional
    public InfraConfig update(String key, String value) {
        InfraConfig config = configRepository.findById(key)
                .orElseThrow(() -> new IllegalArgumentException("설정 키가 존재하지 않습니다: " + key));
        config.setConfigValue(value);
        return configRepository.save(config);
    }

    @Transactional
    public void updateAll(Map<String, String> entries) {
        entries.forEach(this::update);
    }
}
