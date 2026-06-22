package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProcessResultTest {

    @Test
    void exitCodeZero_isSuccess() {
        ProcessResult r = new ProcessResult(0, "done", "");
        assertTrue(r.isSuccess());
        assertEquals("done", r.getStdOut());
        assertEquals("", r.getStdErr());
        assertEquals(0, r.getExitCode());
    }

    @Test
    void nonZeroExitCode_isFailure() {
        ProcessResult r = new ProcessResult(2, "", "boom");
        assertFalse(r.isSuccess());
        assertEquals(2, r.getExitCode());
        assertEquals("boom", r.getStdErr());
    }

    @Test
    void negativeExitCode_isFailure() {
        assertFalse(new ProcessResult(-1, "", "").isSuccess());
    }
}
