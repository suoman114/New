package com.lter.infra.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 설치 후 검증(pkg-validator) 출력 파서 단위테스트.
 * os_audit / verify_vcs_install 스크립트의 [OK]/[WARN]/[MISS]/[FAIL] 태그 집계 검증.
 */
class ScriptExecutorTest {

    private final ScriptExecutor exec = new ScriptExecutor();

    @Test
    void counts_eachTag() {
        String out = String.join("\n",
                "[OK] java 1.8 확인",
                "[OK] vcs 계정 존재",
                "[WARN] RabbitMQ 버전 상이",
                "[FAIL] MariaDB 미설치");
        ScriptExecutor.ValidationSummary s = exec.parseValidationResult(out);
        assertEquals(2, s.getOk());
        assertEquals(1, s.getWarn());
        assertEquals(1, s.getFail());
        assertFalse(s.isPassed()); // FAIL 존재
    }

    @Test
    void missTag_countsAsWarn() {
        String out = "[OK] a\n[MISS] b\n[MISS] c";
        ScriptExecutor.ValidationSummary s = exec.parseValidationResult(out);
        assertEquals(1, s.getOk());
        assertEquals(2, s.getWarn());
        assertEquals(0, s.getFail());
        assertTrue(s.isPassed()); // FAIL 없음 → 통과
    }

    @Test
    void passed_whenNoFail() {
        ScriptExecutor.ValidationSummary s = exec.parseValidationResult("[OK] x\n[WARN] y");
        assertTrue(s.isPassed());
    }

    @Test
    void firstTagPerLineWins_dueToElseIf() {
        // 한 줄에 [OK] 와 [FAIL] 이 함께 있으면 else-if 순서상 [OK] 로만 집계된다
        ScriptExecutor.ValidationSummary s = exec.parseValidationResult("[OK] also has [FAIL] text");
        assertEquals(1, s.getOk());
        assertEquals(0, s.getFail());
        assertTrue(s.isPassed());
    }

    @Test
    void emptyOrUntagged_yieldsZeros() {
        ScriptExecutor.ValidationSummary s = exec.parseValidationResult("");
        assertEquals(0, s.getOk());
        assertEquals(0, s.getWarn());
        assertEquals(0, s.getFail());
        assertTrue(s.isPassed());

        ScriptExecutor.ValidationSummary s2 = exec.parseValidationResult("그냥 로그\n진행중...");
        assertEquals(0, s2.getOk());
        assertTrue(s2.isPassed());
    }
}
