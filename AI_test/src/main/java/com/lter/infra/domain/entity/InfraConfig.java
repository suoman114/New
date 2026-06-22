package com.lter.infra.domain.entity;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import javax.persistence.*;

@Entity
@Table(name = "infra_config")
@Getter
@Setter
@NoArgsConstructor
public class InfraConfig {

    @Id
    @Column(name = "config_key", length = 100)
    private String configKey;

    @Column(name = "config_value", nullable = false, length = 500)
    private String configValue;

    @Column(length = 200)
    private String description;

    public InfraConfig(String configKey, String configValue, String description) {
        this.configKey = configKey;
        this.configValue = configValue;
        this.description = description;
    }

    /** 설정 키 상수 */
    public static final String ANSIBLE_PLAYBOOK_DIR = "ansible.playbook-dir";
    public static final String ANSIBLE_INVENTORY    = "ansible.inventory";
    public static final String SCRIPT_BASE_DIR      = "script.local-base-dir";
    public static final String PACKAGE_BASE_DIR     = "package.local-base-dir";
    public static final String GIT_BASE_DIR         = "git.local-base-dir";
}
