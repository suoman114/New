package com.lter.infra.util;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Ansible playbook 분류/정렬 규약 (pkg-ansible 도메인의 단일 출처).
 *
 * <p>playbook 파일명은 {@code ^(\d+)[-_]} 형태의 번호 prefix 를 가진다.
 * 번호로 OS 셋업 / PKG 셋업을 구분하고, 번호 → 파일명 순으로 실행 순서를 정한다.
 * 이 규약은 {@code AI_test/CLAUDE.md} 의 OS/PKG 셋업 표와 동기화되어야 한다.
 *
 * <pre>
 * OS  : 0,1,2,3,4,5,12,14,15,16
 * PKG : 6,7,8,9,10,11,13
 * </pre>
 *
 * 순수 유틸(파일 IO/Spring 의존 없음) — 단위테스트 대상.
 */
public final class PlaybookCatalog {

    private PlaybookCatalog() {
    }

    /** OS 셋업 playbook 번호 prefix. */
    public static final Set<Integer> OS_PREFIX_NUMS =
            Collections.unmodifiableSet(new HashSet<>(Arrays.asList(0, 1, 2, 3, 4, 5, 12, 14, 15, 16)));

    /** PKG 셋업 playbook 번호 prefix. */
    public static final Set<Integer> PKG_PREFIX_NUMS =
            Collections.unmodifiableSet(new HashSet<>(Arrays.asList(6, 7, 8, 9, 10, 11, 13)));

    private static final Pattern PREFIX_PATTERN = Pattern.compile("^(\\d+)[-_]");

    /** playbook 분류. */
    public enum Phase {
        OS, PKG, UNKNOWN
    }

    /**
     * 파일명에서 번호 prefix 를 추출한다. prefix 가 없으면 -1.
     * 예: "8-1_mariaDB.yml" → 8, "12_Cron_root.yml" → 12, "preflight.yml" → -1.
     */
    public static int extractPrefixNum(String filename) {
        if (filename == null) {
            return -1;
        }
        Matcher m = PREFIX_PATTERN.matcher(filename);
        if (m.find()) {
            try {
                return Integer.parseInt(m.group(1));
            } catch (NumberFormatException ignored) {
                // fallthrough
            }
        }
        return -1;
    }

    /** 파일명을 OS/PKG/UNKNOWN 으로 분류한다. */
    public static Phase classify(String filename) {
        int num = extractPrefixNum(filename);
        if (OS_PREFIX_NUMS.contains(num)) {
            return Phase.OS;
        }
        if (PKG_PREFIX_NUMS.contains(num)) {
            return Phase.PKG;
        }
        return Phase.UNKNOWN;
    }

    public static boolean isOs(String filename) {
        return classify(filename) == Phase.OS;
    }

    public static boolean isPkg(String filename) {
        return classify(filename) == Phase.PKG;
    }

    /** OS+PKG 전체 prefix 집합. */
    public static Set<Integer> allPrefixNums() {
        Set<Integer> all = new HashSet<>();
        all.addAll(OS_PREFIX_NUMS);
        all.addAll(PKG_PREFIX_NUMS);
        return all;
    }

    /** 번호 prefix → 파일명 순 정렬 비교자. */
    public static Comparator<String> ordering() {
        return Comparator.comparingInt(PlaybookCatalog::extractPrefixNum)
                .thenComparing(Comparator.naturalOrder());
    }

    /** 주어진 파일명들을 실행 순서(번호 prefix → 이름)로 정렬한 새 리스트 반환. */
    public static List<String> sorted(Collection<String> filenames) {
        List<String> list = new ArrayList<>(filenames);
        list.sort(ordering());
        return list;
    }

    /** 주어진 prefix 집합에 속하는 파일명만 골라 실행 순서로 정렬해 반환. */
    public static List<String> filterAndSort(Collection<String> filenames, Set<Integer> prefixes) {
        return filenames.stream()
                .filter(name -> prefixes.contains(extractPrefixNum(name)))
                .sorted(ordering())
                .collect(Collectors.toList());
    }
}
