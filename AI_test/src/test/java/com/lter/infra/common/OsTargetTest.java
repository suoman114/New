package com.lter.infra.common;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OsTargetTest {

    @Test
    void code_and_packageManager_areCorrect() {
        assertEquals("centos7", OsTarget.CENTOS7.code());
        assertEquals("rhel8", OsTarget.RHEL8.code());
        assertEquals(OsTarget.PackageManager.YUM, OsTarget.CENTOS7.packageManager());
        assertEquals(OsTarget.PackageManager.DNF, OsTarget.RHEL8.packageManager());
        assertEquals("yum", OsTarget.CENTOS7.packageManager().command());
        assertEquals("dnf", OsTarget.RHEL8.packageManager().command());
    }

    @Test
    void moduleStreams_onlyForRhel8() {
        assertFalse(OsTarget.CENTOS7.usesModuleStreams());
        assertTrue(OsTarget.RHEL8.usesModuleStreams());
    }

    @Test
    void fromString_parsesVariousFormats() {
        assertEquals(OsTarget.CENTOS7, OsTarget.fromString("centos7"));
        assertEquals(OsTarget.CENTOS7, OsTarget.fromString("CentOS 7"));
        assertEquals(OsTarget.CENTOS7, OsTarget.fromString("CENTOS-7"));
        assertEquals(OsTarget.RHEL8, OsTarget.fromString("rhel8"));
        assertEquals(OsTarget.RHEL8, OsTarget.fromString("RHEL_8"));
        assertEquals(OsTarget.RHEL8, OsTarget.fromString("  RHEL 8 "));
    }

    @Test
    void fromString_rejectsUnsupported() {
        assertThrows(IllegalArgumentException.class, () -> OsTarget.fromString("ubuntu"));
        assertThrows(IllegalArgumentException.class, () -> OsTarget.fromString("centos6"));
        assertThrows(IllegalArgumentException.class, () -> OsTarget.fromString(""));
        assertThrows(IllegalArgumentException.class, () -> OsTarget.fromString(null));
    }

    @Test
    void kernelMinVersion_isSet() {
        assertEquals("3.10.0-1160", OsTarget.CENTOS7.kernelMinVersion());
        assertEquals("4.18.0-348", OsTarget.RHEL8.kernelMinVersion());
    }
}
