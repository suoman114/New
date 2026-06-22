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
        StringBuilder sb = new StringBuilder("[vcs]\n");
        for (String ip : ipAddresses) {
            sb.append(ip).append(" ansible_user=root");
            String pw = ipPasswordMap.get(ip);
            if (pw != null && !pw.isEmpty()) {
                sb.append(" ansible_password=").append(pw);
            }
            sb.append("\n");
        }

        try {
            Path path = Paths.get(inventoryPath);
            Files.createDirectories(path.getParent());
            Files.write(path, sb.toString().getBytes());
            log.info("Ansible inventory 생성 완료: {} -> {}", ipAddresses, inventoryPath);
        } catch (IOException e) {
            throw new RuntimeException("Ansible inventory 파일 생성 실패: " + inventoryPath, e);
        }
    }
}
