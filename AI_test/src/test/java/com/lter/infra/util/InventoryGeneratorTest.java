package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InventoryGeneratorTest {

    @Test
    void singleHost_noPassword() {
        String inv = InventoryGenerator.buildInventory(
                Collections.singletonList("192.168.1.10"), Collections.emptyMap());
        assertEquals("[vcs]\n192.168.1.10 ansible_user=root\n", inv);
    }

    @Test
    void multipleHosts_mixedPasswords() {
        Map<String, String> pw = new HashMap<>();
        pw.put("192.168.1.10", "secret1");
        // .11 은 비밀번호 없음
        String inv = InventoryGenerator.buildInventory(
                Arrays.asList("192.168.1.10", "192.168.1.11"), pw);

        assertEquals(
                "[vcs]\n"
                        + "192.168.1.10 ansible_user=root ansible_password=secret1\n"
                        + "192.168.1.11 ansible_user=root\n",
                inv);
    }

    @Test
    void emptyPassword_isOmitted() {
        Map<String, String> pw = new HashMap<>();
        pw.put("10.0.0.1", "");
        String inv = InventoryGenerator.buildInventory(Collections.singletonList("10.0.0.1"), pw);
        assertEquals("[vcs]\n10.0.0.1 ansible_user=root\n", inv);
    }

    @Test
    void nullPasswordMap_isHandled() {
        String inv = InventoryGenerator.buildInventory(Collections.singletonList("10.0.0.2"), null);
        assertEquals("[vcs]\n10.0.0.2 ansible_user=root\n", inv);
    }

    @Test
    void noHosts_producesGroupHeaderOnly() {
        assertEquals("[vcs]\n", InventoryGenerator.buildInventory(Collections.emptyList(), null));
        assertEquals("[vcs]\n", InventoryGenerator.buildInventory(null, null));
    }

    @Test
    void groupHeader_matchesConstant() {
        String inv = InventoryGenerator.buildInventory(Collections.emptyList(), null);
        assertTrue(inv.startsWith("[" + InventoryGenerator.HOST_GROUP + "]"));
    }
}
