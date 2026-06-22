package com.lter.infra.util;

import com.lter.infra.domain.entity.InfraConfig;
import com.lter.infra.service.SystemConfigService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.List;
import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class InventoryGenerator {

    private final SystemConfigService systemConfigService;

    /** 단일 서버 (패스워드 없음) */
    public void generate(String ipAddress) {
        generate(Collections.singletonList(ipAddress), Collections.emptyMap());
    }

    /** 다중 서버 (패스워드 없음) */
    public void generate(List<String> ipAddresses) {
        generate(ipAddresses, Collections.emptyMap());
    }

    /**
     * 다중 서버 + 서버별 패스워드로 inventory 생성.
     * ipPasswordMap: ip -> ansible_password (없으면 해당 항목 생략)
     *
     * 생성 형식:
     * [vcs]
     * 192.168.1.10 ansible_user=root ansible_password=secret1
     * 192.168.1.11 ansible_user=root
     */
    public void generate(List<String> ipAddresses, Map<String, String> ipPasswordMap) {
        String inventoryPath = systemConfigService.get(InfraConfig.ANSIBLE_INVENTORY);
        String content = buildInventory(ipAddresses, ipPasswordMap);

        try {
            Path path = Paths.get(inventoryPath);
            Files.createDirectories(path.getParent());
            Files.write(path, content.getBytes());
            log.info("Ansible inventory 생성 완료: {} -> {}", ipAddresses, inventoryPath);
        } catch (IOException e) {
            throw new RuntimeException("Ansible inventory 파일 생성 실패: " + inventoryPath, e);
        }
    }

    /** 대상 호스트 그룹 이름 (Ansible inventory 의 그룹 헤더). */
    public static final String HOST_GROUP = "vcs";

    /**
     * inventory 파일 본문 문자열을 생성한다 (순수 함수 — 파일 IO 없음, 단위테스트 대상).
     *
     * <pre>
     * [vcs]
     * 192.168.1.10 ansible_user=root ansible_password=secret1
     * 192.168.1.11 ansible_user=root
     * </pre>
     *
     * @param ipAddresses    대상 서버 IP 목록 (null 이면 빈 그룹)
     * @param ipPasswordMap  ip → ansible_password (없으면 비밀번호 항목 생략, null 허용)
     */
    public static String buildInventory(List<String> ipAddresses, Map<String, String> ipPasswordMap) {
        StringBuilder sb = new StringBuilder("[").append(HOST_GROUP).append("]\n");
        if (ipAddresses != null) {
            Map<String, String> pwMap = ipPasswordMap != null ? ipPasswordMap : Collections.emptyMap();
            for (String ip : ipAddresses) {
                sb.append(ip).append(" ansible_user=root");
                String pw = pwMap.get(ip);
                if (pw != null && !pw.isEmpty()) {
                    sb.append(" ansible_password=").append(pw);
                }
                sb.append("\n");
            }
        }
        return sb.toString();
    }
}
