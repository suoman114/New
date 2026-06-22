package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RemoteCommandBuilderTest {

    @Test
    void scp_withPassword_wrapsWithSshpassAndTarget() {
        List<String> cmd = RemoteCommandBuilder.scp(
                "/opt/lter/packages/app.tar.gz", "10.0.0.5", 22, "pw1", "/opt/vcs");
        assertEquals("sshpass", cmd.get(0));
        assertEquals("-p", cmd.get(1));
        assertEquals("pw1", cmd.get(2));
        assertTrue(cmd.contains("scp"));
        assertTrue(cmd.contains("StrictHostKeyChecking=no"));
        // 마지막 인자는 대상 위치
        assertEquals("root@10.0.0.5:/opt/vcs", cmd.get(cmd.size() - 1));
        // 포트 옵션
        int pIdx = cmd.indexOf("-P");
        assertEquals("22", cmd.get(pIdx + 1));
    }

    @Test
    void scp_withoutPassword_hasNoSshpass() {
        List<String> cmd = RemoteCommandBuilder.scp("/a", "1.2.3.4", 2222, "  ", "/dst");
        assertFalse(cmd.contains("sshpass"));
        assertEquals("scp", cmd.get(0));
        int pIdx = cmd.indexOf("-P");
        assertEquals("2222", cmd.get(pIdx + 1));
    }

    @Test
    void ssh_forcesPasswordAuth() {
        List<String> cmd = RemoteCommandBuilder.ssh("10.0.0.9", 22, "pw", "whoami");
        assertEquals("sshpass", cmd.get(0));
        assertTrue(cmd.contains("PubkeyAuthentication=no"));
        assertTrue(cmd.contains("PreferredAuthentications=password"));
        assertEquals("root@10.0.0.9", cmd.get(cmd.size() - 2));
        assertEquals("whoami", cmd.get(cmd.size() - 1));
    }

    @Test
    void extractCommand_byExtension() {
        assertEquals("tar -xzf /opt/vcs/app.tar.gz -C /opt/vcs",
                RemoteCommandBuilder.extractCommand("/opt/vcs", "app.tar.gz"));
        assertEquals("tar -xzf /opt/vcs/app.tgz -C /opt/vcs",
                RemoteCommandBuilder.extractCommand("/opt/vcs", "app.tgz"));
        assertEquals("gunzip -f /opt/vcs/data.gz",
                RemoteCommandBuilder.extractCommand("/opt/vcs", "data.gz"));
        assertEquals("unzip -o /opt/vcs/web.zip -d /opt/vcs",
                RemoteCommandBuilder.extractCommand("/opt/vcs", "web.zip"));
    }

    @Test
    void extractCommand_trailingSlashAndUnknown() {
        assertEquals("tar -xzf /opt/vcs/app.tar.gz -C /opt/vcs/",
                RemoteCommandBuilder.extractCommand("/opt/vcs/", "app.tar.gz"));
        assertEquals("echo 'unknown format: app.rpm'",
                RemoteCommandBuilder.extractCommand("/opt/vcs", "app.rpm"));
    }

    @Test
    void injectHttpCredentials_https_and_http() {
        assertEquals("https://u:p@git.internal/repo.git",
                RemoteCommandBuilder.injectHttpCredentials("https://git.internal/repo.git", "u", "p"));
        assertEquals("http://u:p@git.internal/repo.git",
                RemoteCommandBuilder.injectHttpCredentials("http://git.internal/repo.git", "u", "p"));
    }

    @Test
    void injectHttpCredentials_nullsReturnOriginal() {
        assertEquals("https://git.internal/repo.git",
                RemoteCommandBuilder.injectHttpCredentials("https://git.internal/repo.git", null, "p"));
        assertEquals("https://git.internal/repo.git",
                RemoteCommandBuilder.injectHttpCredentials("https://git.internal/repo.git", "u", null));
    }
}
