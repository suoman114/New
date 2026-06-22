package com.lter.infra.service;

import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SseLogService 의 구독/전송 가드 동작 단위테스트.
 * (실제 HTTP 스트리밍은 통합 영역이므로, 구독 관리/없는 키 처리만 검증한다.)
 */
class SseLogServiceTest {

    private final SseLogService service = new SseLogService();

    @Test
    void noSubscriber_initially() {
        assertFalse(service.hasSubscriber("job-1"));
    }

    @Test
    void send_toMissingKey_isNoop() {
        // 예외 없이 무시되어야 한다
        service.send("job-missing", "hello");
        assertFalse(service.hasSubscriber("job-missing"));
    }

    @Test
    void complete_missingKey_isNoop() {
        service.complete("job-missing");
        assertFalse(service.hasSubscriber("job-missing"));
    }

    @Test
    void subscribe_registersEmitter_andLogConsumerWorks() {
        SseEmitter emitter = service.subscribe("job-7");
        assertNotNull(emitter);
        assertTrue(service.hasSubscriber("job-7"));
        // logConsumer 는 해당 키로 전송하는 콜백
        assertNotNull(service.logConsumer("job-7"));
        service.logConsumer("job-7").accept("line-1");
        // complete 후 구독 해제
        service.complete("job-7");
        assertFalse(service.hasSubscriber("job-7"));
    }
}
