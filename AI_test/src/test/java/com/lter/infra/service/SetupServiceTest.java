package com.lter.infra.service;

import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * SetupService 의 순수 목록 해석 로직(resolvePlaybooks / resolveResumeFrom) 단위테스트.
 * 이 메서드들은 주입 의존성을 쓰지 않으므로 null 생성자로 충분하다.
 */
class SetupServiceTest {

    private final SetupService service = new SetupService(null, null, null, null, null, null);

    private static final List<String> ALL = Arrays.asList(
            "0_auto_pass.yml", "4_ntp.yml", "6_RMQ_vcs.yml", "13_service_start.yml");

    @Test
    void resolvePlaybooks_nullOrEmpty_returnsAll() {
        assertEquals(ALL, service.resolvePlaybooks(null, ALL));
        assertEquals(ALL, service.resolvePlaybooks(Collections.emptyList(), ALL));
    }

    @Test
    void resolvePlaybooks_subset_preservesCanonicalOrder() {
        // 선택 순서가 뒤죽박죽이어도 ALL 의 순서를 유지하며 필터링
        List<String> selected = Arrays.asList("13_service_start.yml", "0_auto_pass.yml");
        assertEquals(Arrays.asList("0_auto_pass.yml", "13_service_start.yml"),
                service.resolvePlaybooks(selected, ALL));
    }

    @Test
    void resolvePlaybooks_unknownSelectionIgnored() {
        List<String> selected = Arrays.asList("4_ntp.yml", "99_nope.yml");
        assertEquals(Collections.singletonList("4_ntp.yml"),
                service.resolvePlaybooks(selected, ALL));
    }

    @Test
    void resolveResumeFrom_nullOrEmpty_returnsAll() {
        assertEquals(ALL, service.resolveResumeFrom(null, ALL));
        assertEquals(ALL, service.resolveResumeFrom("", ALL));
    }

    @Test
    void resolveResumeFrom_fromMiddle_returnsTail() {
        assertEquals(Arrays.asList("6_RMQ_vcs.yml", "13_service_start.yml"),
                service.resolveResumeFrom("6_RMQ_vcs.yml", ALL));
    }

    @Test
    void resolveResumeFrom_firstOrUnknown_returnsAll() {
        // 첫 번째(idx 0) 또는 미존재(idx -1) 면 전체 유지
        assertEquals(ALL, service.resolveResumeFrom("0_auto_pass.yml", ALL));
        assertEquals(ALL, service.resolveResumeFrom("nope.yml", ALL));
    }
}
