package com.lter.infra.common;

import java.util.Arrays;

/**
 * 폐쇄망 프로비저닝 대상 OS 타깃 (pkg-platform 공통 기반).
 *
 * <p>설치 자동화 스코프상 지원 대상은 <b>CentOS 7</b> 과 <b>RHEL 8</b> 두 가지다.
 * Ansible 플레이북/검증의 OS 분기는 이 enum 을 단일 출처로 사용한다.
 * (주의: {@code TargetServer.OsType} 은 서버 등록용 대분류(CENTOS/UBUNTU)로 별개이며,
 * 본 enum 은 버전까지 포함한 프로비저닝 타깃을 표현한다.)
 */
public enum OsTarget {

    CENTOS7("centos7", "CentOS 7", PackageManager.YUM, "3.10.0-1160"),
    RHEL8("rhel8", "RHEL 8", PackageManager.DNF, "4.18.0-348");

    public enum PackageManager {
        YUM("yum"),
        DNF("dnf");

        private final String command;

        PackageManager(String command) {
            this.command = command;
        }

        public String command() {
            return command;
        }
    }

    private final String code;
    private final String label;
    private final PackageManager packageManager;
    private final String kernelMinVersion;

    OsTarget(String code, String label, PackageManager packageManager, String kernelMinVersion) {
        this.code = code;
        this.label = label;
        this.packageManager = packageManager;
        this.kernelMinVersion = kernelMinVersion;
    }

    /** 플레이북 extra-vars 및 group_vars 분기에 쓰는 코드값 (예: "centos7"). */
    public String code() {
        return code;
    }

    /** 사람이 읽는 라벨 (예: "CentOS 7"). */
    public String label() {
        return label;
    }

    /** 패키지 매니저 (CentOS7=yum, RHEL8=dnf). */
    public PackageManager packageManager() {
        return packageManager;
    }

    /** 검증 기준 커널 최소 버전. */
    public String kernelMinVersion() {
        return kernelMinVersion;
    }

    /** RHEL8 계열에서만 dnf module stream 을 사용한다. */
    public boolean usesModuleStreams() {
        return this == RHEL8;
    }

    /**
     * 코드/라벨 문자열로부터 OsTarget 을 해석한다. 대소문자/공백/하이픈/언더스코어 무시.
     * 예: "centos7", "CentOS 7", "CENTOS-7", "rhel8", "RHEL_8".
     *
     * @throws IllegalArgumentException 지원하지 않는 값
     */
    public static OsTarget fromString(String value) {
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("OS 타깃이 비어 있습니다.");
        }
        String normalized = value.toLowerCase().replaceAll("[\\s_-]", "");
        return Arrays.stream(values())
                .filter(t -> normalized.equals(t.code.replaceAll("[\\s_-]", ""))
                        || normalized.equals(t.label.toLowerCase().replaceAll("[\\s_-]", "")))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(
                        "지원하지 않는 OS 타깃입니다: " + value + " (지원: centos7, rhel8)"));
    }
}
