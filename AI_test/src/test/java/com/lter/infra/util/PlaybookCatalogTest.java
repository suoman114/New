package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PlaybookCatalogTest {

    @Test
    void extractPrefixNum_parsesLeadingNumber() {
        assertEquals(0, PlaybookCatalog.extractPrefixNum("0_auto_pass.yml"));
        assertEquals(8, PlaybookCatalog.extractPrefixNum("8-1_mariaDB.yml"));
        assertEquals(10, PlaybookCatalog.extractPrefixNum("10-2_chmod_vcweb.yml"));
        assertEquals(12, PlaybookCatalog.extractPrefixNum("12_Cron_root.yml"));
    }

    @Test
    void extractPrefixNum_returnsMinusOneWhenAbsent() {
        assertEquals(-1, PlaybookCatalog.extractPrefixNum("preflight.yml"));
        assertEquals(-1, PlaybookCatalog.extractPrefixNum("readme.txt"));
        assertEquals(-1, PlaybookCatalog.extractPrefixNum(null));
    }

    @Test
    void classify_separatesOsAndPkg() {
        // OS: 0,1,2,3,4,5,12,14,15,16
        assertEquals(PlaybookCatalog.Phase.OS, PlaybookCatalog.classify("4_ntp.yml"));
        assertEquals(PlaybookCatalog.Phase.OS, PlaybookCatalog.classify("15_rclocal.yml"));
        assertEquals(PlaybookCatalog.Phase.OS, PlaybookCatalog.classify("16_watermark.yml"));
        // PKG: 6,7,8,9,10,11,13
        assertEquals(PlaybookCatalog.Phase.PKG, PlaybookCatalog.classify("6_RMQ_vcs.yml"));
        assertEquals(PlaybookCatalog.Phase.PKG, PlaybookCatalog.classify("8-2_mariaDB_chown.yml"));
        assertEquals(PlaybookCatalog.Phase.PKG, PlaybookCatalog.classify("13_service_start.yml"));
        // UNKNOWN
        assertEquals(PlaybookCatalog.Phase.UNKNOWN, PlaybookCatalog.classify("99_extra.yml"));
        assertEquals(PlaybookCatalog.Phase.UNKNOWN, PlaybookCatalog.classify("preflight.yml"));
    }

    @Test
    void isOs_isPkg_helpers() {
        assertTrue(PlaybookCatalog.isOs("3_sysctl.yml"));
        assertFalse(PlaybookCatalog.isPkg("3_sysctl.yml"));
        assertTrue(PlaybookCatalog.isPkg("7_openjdk.yml"));
        assertFalse(PlaybookCatalog.isOs("7_openjdk.yml"));
    }

    @Test
    void osAndPkgSets_areDisjoint_andMatchCanon() {
        for (Integer n : PlaybookCatalog.OS_PREFIX_NUMS) {
            assertFalse(PlaybookCatalog.PKG_PREFIX_NUMS.contains(n), "겹치는 prefix: " + n);
        }
        assertEquals(17, PlaybookCatalog.allPrefixNums().size()); // 10 OS + 7 PKG
    }

    @Test
    void sorted_ordersByPrefixThenName() {
        List<String> input = Arrays.asList(
                "13_service_start.yml", "8-2_mariaDB_chown.yml", "8-1_mariaDB.yml",
                "0_auto_pass.yml", "10-1_group_vcweb.yml", "9-1_group_vcs.yml");
        List<String> sorted = PlaybookCatalog.sorted(input);
        assertEquals(Arrays.asList(
                "0_auto_pass.yml", "8-1_mariaDB.yml", "8-2_mariaDB_chown.yml",
                "9-1_group_vcs.yml", "10-1_group_vcweb.yml", "13_service_start.yml"), sorted);
    }

    @Test
    void filterAndSort_picksOnlyRequestedPrefixes() {
        List<String> all = Arrays.asList(
                "0_auto_pass.yml", "6_RMQ_vcs.yml", "4_ntp.yml", "7_openjdk.yml", "preflight.yml");
        List<String> os = PlaybookCatalog.filterAndSort(all, PlaybookCatalog.OS_PREFIX_NUMS);
        assertEquals(Arrays.asList("0_auto_pass.yml", "4_ntp.yml"), os);
        List<String> pkg = PlaybookCatalog.filterAndSort(all, PlaybookCatalog.PKG_PREFIX_NUMS);
        assertEquals(Arrays.asList("6_RMQ_vcs.yml", "7_openjdk.yml"), pkg);
    }

    @Test
    void emptyInput_yieldsEmpty() {
        assertTrue(PlaybookCatalog.sorted(Collections.emptyList()).isEmpty());
        assertTrue(PlaybookCatalog.filterAndSort(Collections.emptyList(),
                PlaybookCatalog.OS_PREFIX_NUMS).isEmpty());
    }
}
