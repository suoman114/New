-- LTER Infra DB 초기화 SQL (MariaDB)
-- prod 프로파일 최초 기동 전 수동 실행

CREATE DATABASE IF NOT EXISTS lter_infra
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE lter_infra;

-- 계정 생성 (없을 경우)
CREATE USER IF NOT EXISTS 'lter'@'%' IDENTIFIED BY 'lter.123';
GRANT ALL PRIVILEGES ON lter_infra.* TO 'lter'@'%';
FLUSH PRIVILEGES;

-- ============================================================
-- 테이블 생성 (JPA ddl-auto: update 가 없을 경우 대비)
-- ============================================================

CREATE TABLE IF NOT EXISTS target_server (
    id          BIGINT          NOT NULL AUTO_INCREMENT,
    server_name VARCHAR(100)    NOT NULL,
    ip_address  VARCHAR(50)     NOT NULL,
    os_type     VARCHAR(20)     NOT NULL COMMENT 'CENTOS | UBUNTU',
    os_version  VARCHAR(50),
    status      VARCHAR(20)     NOT NULL DEFAULT 'REGISTERED' COMMENT 'REGISTERED | SETUP_DONE | VERIFIED | ERROR',
    description  VARCHAR(200),
    ssh_password VARCHAR(200),
    created_at   DATETIME        NOT NULL,
    updated_at   DATETIME,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ip_address (ip_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='대상 서버 목록';

CREATE TABLE IF NOT EXISTS git_repo (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    repo_name       VARCHAR(100)    NOT NULL,
    repo_url        VARCHAR(500)    NOT NULL,
    branch          VARCHAR(100)    NOT NULL,
    auth_type       VARCHAR(20)     NOT NULL COMMENT 'SSH | PASSWORD',
    username        VARCHAR(200),
    password        VARCHAR(200),
    ssh_key_path    TEXT,
    local_path      VARCHAR(500)    NOT NULL,
    repo_type       VARCHAR(20)     NOT NULL COMMENT 'RPM | SCRIPT',
    description     VARCHAR(200),
    created_at      DATETIME        NOT NULL,
    last_pulled_at  DATETIME,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Git 저장소 정보';

CREATE TABLE IF NOT EXISTS package (
    id           BIGINT          NOT NULL AUTO_INCREMENT,
    package_name VARCHAR(100)    NOT NULL,
    version      VARCHAR(50)     NOT NULL,
    git_path     VARCHAR(200),
    git_repo_id  BIGINT,
    local_path   VARCHAR(500)    NOT NULL,
    target_os    VARCHAR(20)     NOT NULL COMMENT 'CENTOS | UBUNTU',
    description  VARCHAR(200),
    created_at   DATETIME        NOT NULL,
    updated_at   DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT fk_package_git_repo FOREIGN KEY (git_repo_id) REFERENCES git_repo (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPM 패키지 관리';

CREATE TABLE IF NOT EXISTS script (
    id           BIGINT          NOT NULL AUTO_INCREMENT,
    script_name  VARCHAR(100)    NOT NULL,
    local_path   VARCHAR(500)    NOT NULL,
    git_path     VARCHAR(100),
    git_repo_id  BIGINT,
    script_type  VARCHAR(30)     NOT NULL COMMENT 'OS_AUDIT | VCS_INSTALL_VERIFY',
    description  VARCHAR(200),
    created_at   DATETIME        NOT NULL,
    updated_at   DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT fk_script_git_repo FOREIGN KEY (git_repo_id) REFERENCES git_repo (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Validation 스크립트 관리';

CREATE TABLE IF NOT EXISTS job_history (
    id            BIGINT          NOT NULL AUTO_INCREMENT,
    server_id     BIGINT,
    job_type      VARCHAR(30)     NOT NULL COMMENT 'OS_SETUP | PKG_INSTALL | VALIDATION | GIT_PULL',
    playbook_name VARCHAR(200),
    status        VARCHAR(20)     NOT NULL DEFAULT 'RUNNING' COMMENT 'RUNNING | SUCCESS | FAIL',
    exit_code     INT,
    std_out       TEXT,
    std_err       TEXT,
    started_at    DATETIME        NOT NULL,
    finished_at   DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT fk_job_history_server FOREIGN KEY (server_id) REFERENCES target_server (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='작업 실행 이력';

CREATE TABLE IF NOT EXISTS pipeline (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    name            VARCHAR(100)    NOT NULL,
    description     VARCHAR(300),
    execution_mode  VARCHAR(20)     NOT NULL COMMENT 'AUTO | MANUAL',
    created_at      DATETIME        NOT NULL,
    updated_at      DATETIME,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='파이프라인 정의';

CREATE TABLE IF NOT EXISTS pipeline_step (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    pipeline_id         BIGINT          NOT NULL,
    step_order          INT             NOT NULL,
    step_type           VARCHAR(30)     NOT NULL COMMENT 'OS_SETUP | PKG_SETUP | VALIDATION',
    selected_playbooks  TEXT,
    ntp_server          VARCHAR(50),
    maria_db_password   VARCHAR(100),
    database_name       VARCHAR(100),
    selected_packages   TEXT,
    remote_deploy_path  VARCHAR(200),
    script_id           BIGINT,
    script_args         VARCHAR(500),
    server_ids          TEXT,
    PRIMARY KEY (id),
    CONSTRAINT fk_pipeline_step_pipeline FOREIGN KEY (pipeline_id) REFERENCES pipeline (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='파이프라인 단계 정의';

CREATE TABLE IF NOT EXISTS pipeline_run (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    pipeline_id         BIGINT          NOT NULL,
    pipeline_name       VARCHAR(100),
    status              VARCHAR(20)     NOT NULL COMMENT 'RUNNING | WAITING_APPROVAL | SUCCESS | FAIL | CANCELLED',
    current_step_order  INT,
    started_at          DATETIME        NOT NULL,
    finished_at         DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT fk_pipeline_run_pipeline FOREIGN KEY (pipeline_id) REFERENCES pipeline (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='파이프라인 실행 이력';

CREATE TABLE IF NOT EXISTS pipeline_step_run (
    id                  BIGINT          NOT NULL AUTO_INCREMENT,
    pipeline_run_id     BIGINT          NOT NULL,
    step_order          INT             NOT NULL,
    step_type           VARCHAR(30)     NOT NULL,
    job_history_id      BIGINT,
    server_name         VARCHAR(100),
    server_ip           VARCHAR(50),
    status              VARCHAR(20)     NOT NULL COMMENT 'RUNNING | SUCCESS | FAIL | SKIPPED',
    started_at          DATETIME        NOT NULL,
    finished_at         DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT fk_step_run_pipeline_run FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_run (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='파이프라인 단계별 실행 결과';

CREATE TABLE IF NOT EXISTS infra_config (
    config_key      VARCHAR(100)    NOT NULL,
    config_value    VARCHAR(500)    NOT NULL,
    description     VARCHAR(200),
    PRIMARY KEY (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='시스템 설정 (key-value)';

INSERT IGNORE INTO infra_config (config_key, config_value, description) VALUES
    ('ansible.playbook-dir', '/opt/lter/infra/ansible',                  'Ansible playbook 디렉토리'),
    ('ansible.inventory',    '/opt/lter/infra/ansible/inventory/hosts',  'Ansible inventory 파일 경로'),
    ('script.local-base-dir',  '/opt/lter/infra/scripts',                'Validation 스크립트 로컬 저장 경로'),
    ('package.local-base-dir', '/opt/lter/infra/packages',               'RPM 패키지 로컬 저장 경로'),
    ('git.local-base-dir',     '/opt/lter/infra/repos',                  'Git 저장소 로컬 클론 경로');
