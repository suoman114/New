package com.lter.infra.util;

/**
 * 설치 완료 보고서(pkg-report) 포맷 유틸 (순수 함수).
 *
 * <p>검증 집계 → 상태 코드 변환, HTML 이스케이프 등 IO 없는 표현 로직을 한 곳에 모은다.
 */
public final class ReportFormat {

    private ReportFormat() {
    }

    /**
     * 검증 집계(ok/warn/miss/fail)를 보고서 상태 코드로 환산한다.
     * 우선순위: 실패 &gt; 경고/누락 &gt; 정상 &gt; 미수행.
     *
     * <ul>
     *   <li>{@code fail > 0} → "NOK"</li>
     *   <li>{@code warn > 0 || miss > 0} → "COK" (조건부 OK)</li>
     *   <li>{@code ok > 0} → "OK"</li>
     *   <li>그 외 → "SKIP"</li>
     * </ul>
     */
    public static String auditStatus(int ok, int warn, int miss, int fail) {
        if (fail > 0) {
            return "NOK";
        }
        if (warn > 0 || miss > 0) {
            return "COK";
        }
        if (ok > 0) {
            return "OK";
        }
        return "SKIP";
    }

    /** HTML 특수문자 이스케이프(&amp; &lt; &gt; &quot;). null 은 빈 문자열. */
    public static String escapeHtml(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }
}
