package com.lter.infra.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Consumer;

/**
 * 실행 중인 Job의 로그를 SSE로 브라우저에 스트리밍한다.
 * key: jobKey (ex. "job-123" or "pipeline-5")
 */
@Slf4j
@Service
public class SseLogService {

    private final Map<String, SseEmitter> emitters = new ConcurrentHashMap<>();

    public SseEmitter subscribe(String key) {
        SseEmitter emitter = new SseEmitter(30 * 60 * 1000L); // 30분
        emitter.onCompletion(() -> emitters.remove(key));
        emitter.onTimeout(() -> emitters.remove(key));
        emitter.onError(e -> emitters.remove(key));
        emitters.put(key, emitter);
        send(key, "[CONNECTED]");
        return emitter;
    }

    public void send(String key, String message) {
        SseEmitter emitter = emitters.get(key);
        if (emitter == null) return;
        try {
            emitter.send(SseEmitter.event().data(message));
        } catch (IOException e) {
            emitters.remove(key);
        }
    }

    public void complete(String key) {
        SseEmitter emitter = emitters.remove(key);
        if (emitter != null) {
            try {
                emitter.send(SseEmitter.event().data("[DONE]"));
                emitter.complete();
            } catch (IOException ignored) {}
        }
    }

    /** 특정 key에 대한 Consumer<String> 반환 - Executor 콜백으로 사용 */
    public Consumer<String> logConsumer(String key) {
        return line -> send(key, line);
    }

    public boolean hasSubscriber(String key) {
        return emitters.containsKey(key);
    }
}
