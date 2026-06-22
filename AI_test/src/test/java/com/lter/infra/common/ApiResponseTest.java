package com.lter.infra.common;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiResponseTest {

    @Test
    void ok_withData_setsSuccessAndDefaultMessage() {
        ApiResponse<String> res = ApiResponse.ok("payload");
        assertTrue(res.isSuccess());
        assertEquals("OK", res.getMessage());
        assertEquals("payload", res.getData());
    }

    @Test
    void ok_withCustomMessage() {
        ApiResponse<Integer> res = ApiResponse.ok("생성됨", 42);
        assertTrue(res.isSuccess());
        assertEquals("생성됨", res.getMessage());
        assertEquals(42, res.getData());
    }

    @Test
    void fail_setsFailureAndNullData() {
        ApiResponse<Void> res = ApiResponse.fail("오류 발생");
        assertFalse(res.isSuccess());
        assertEquals("오류 발생", res.getMessage());
        assertNull(res.getData());
    }
}
