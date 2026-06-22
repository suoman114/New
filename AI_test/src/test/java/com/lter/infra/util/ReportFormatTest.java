package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportFormatTest {

    @Test
    void auditStatus_failTakesPriority() {
        assertEquals("NOK", ReportFormat.auditStatus(5, 2, 1, 1));
        assertEquals("NOK", ReportFormat.auditStatus(0, 0, 0, 3));
    }

    @Test
    void auditStatus_warnOrMiss_isConditionalOk() {
        assertEquals("COK", ReportFormat.auditStatus(3, 1, 0, 0));
        assertEquals("COK", ReportFormat.auditStatus(3, 0, 1, 0));
        assertEquals("COK", ReportFormat.auditStatus(0, 2, 2, 0));
    }

    @Test
    void auditStatus_allOk() {
        assertEquals("OK", ReportFormat.auditStatus(4, 0, 0, 0));
    }

    @Test
    void auditStatus_nothing_isSkip() {
        assertEquals("SKIP", ReportFormat.auditStatus(0, 0, 0, 0));
    }

    @Test
    void escapeHtml_replacesSpecialChars() {
        assertEquals("&lt;b&gt;x&amp;y&quot;z&quot;&lt;/b&gt;",
                ReportFormat.escapeHtml("<b>x&y\"z\"</b>"));
    }

    @Test
    void escapeHtml_nullToEmpty_andPlainUnchanged() {
        assertEquals("", ReportFormat.escapeHtml(null));
        assertEquals("plain text 123", ReportFormat.escapeHtml("plain text 123"));
    }
}
