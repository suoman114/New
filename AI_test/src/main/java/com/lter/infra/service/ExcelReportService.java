package com.lter.infra.service;

import lombok.RequiredArgsConstructor;
import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.*;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class ExcelReportService {

    private final ReportService reportService;

    public byte[] generateExcel(Long serverId) throws IOException {
        Map<String, Object> report = reportService.buildReport(serverId);
        try (XSSFWorkbook wb = new XSSFWorkbook()) {
            Styles s = new Styles(wb);
            buildOsSetupSheet(wb, s, report);
            buildPkgSetupSheet(wb, s, report);
            buildValidationSheet(wb, s, report);
            buildOsAuditSheet(wb, s, report);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            wb.write(out);
            return out.toByteArray();
        }
    }

    // ── OS 셋업 시트 ─────────────────────────────────────────────────────────
    @SuppressWarnings("unchecked")
    private void buildOsSetupSheet(XSSFWorkbook wb, Styles s, Map<String, Object> report) {
        XSSFSheet sheet = wb.createSheet("OS 셋업");
        sheet.setColumnWidth(0, 8000); // Playbook
        sheet.setColumnWidth(1, 9000); // 설명
        sheet.setColumnWidth(2, 3000); // 상태
        sheet.setColumnWidth(3, 5500); // 시작시간
        sheet.setColumnWidth(4, 5500); // 종료시간

        int row = 0;
        row = writeInfoRow(sheet, s, row, report);
        row = writeSetupTable(sheet, s, row,
                (List<Map<String, Object>>) report.getOrDefault("osSetup", java.util.Collections.emptyList()));
    }

    // ── PKG 셋업 시트 ────────────────────────────────────────────────────────
    @SuppressWarnings("unchecked")
    private void buildPkgSetupSheet(XSSFWorkbook wb, Styles s, Map<String, Object> report) {
        XSSFSheet sheet = wb.createSheet("PKG 셋업");
        sheet.setColumnWidth(0, 8000);
        sheet.setColumnWidth(1, 9000);
        sheet.setColumnWidth(2, 3000);
        sheet.setColumnWidth(3, 5500);
        sheet.setColumnWidth(4, 5500);

        int row = 0;
        row = writeInfoRow(sheet, s, row, report);
        row = writeSetupTable(sheet, s, row,
                (List<Map<String, Object>>) report.getOrDefault("pkgSetup", java.util.Collections.emptyList()));
    }

    // ── Validation 시트 ──────────────────────────────────────────────────────
    @SuppressWarnings("unchecked")
    private void buildValidationSheet(XSSFWorkbook wb, Styles s, Map<String, Object> report) {
        XSSFSheet sheet = wb.createSheet("Validation");
        sheet.setColumnWidth(0, 3000); // 상태
        sheet.setColumnWidth(1, 18000); // 항목

        int row = 0;
        row = writeInfoRow(sheet, s, row, report);

        Map<String, Object> val = (Map<String, Object>) report.getOrDefault("validation", java.util.Collections.emptyMap());

        // VCS 설치 검증
        Map<String, Object> vcs = (Map<String, Object>) val.get("vcsVerify");
        if (vcs != null) {
            row++;
            row = writeSectionHeader(sheet, s, row, "VCS 설치 검증", "실행일시: " + str(vcs.get("executedAt")));
            row = writeCheckTable(sheet, s, row, (List<Map<String, Object>>) vcs.get("items"));
        }

        // VCS Link 스크립트 결과 (원문 텍스트)
        Map<String, Object> vcsLink = (Map<String, Object>) val.get("vcsLink");
        if (vcsLink != null && vcsLink.get("rawOutput") != null) {
            row++;
            row = writeSectionHeader(sheet, s, row, "VCS Link 실행 결과", "실행일시: " + str(vcsLink.get("executedAt")));
            String raw = str(vcsLink.get("rawOutput"));
            for (String line : raw.split("\n")) {
                XSSFRow lineRow = sheet.createRow(row++);
                createCell(lineRow, 0, line.trim(), s.normal);
            }
        }

        if (val.isEmpty() || (vcs == null && vcsLink == null)) {
            XSSFRow r = sheet.createRow(row);
            createCell(r, 0, "Validation 이력 없음", s.normal);
        }
    }

    // ── OS Audit 상세 시트 ───────────────────────────────────────────────────
    @SuppressWarnings("unchecked")
    private void buildOsAuditSheet(XSSFWorkbook wb, Styles s, Map<String, Object> report) {
        Map<String, Object> val = (Map<String, Object>) report.getOrDefault("validation", java.util.Collections.emptyMap());
        Map<String, Object> audit = (Map<String, Object>) val.get("osAudit");
        if (audit == null) return;

        Map<String, List<String>> sections = (Map<String, List<String>>) audit.get("sections");
        if (sections == null || sections.isEmpty()) return;

        XSSFSheet sheet = wb.createSheet("OS Audit 상세");
        sheet.setColumnWidth(0, 3000);  // 상태
        sheet.setColumnWidth(1, 18000); // 항목/내용

        int row = 0;
        row = writeInfoRow(sheet, s, row, report);

        XSSFRow execRow = sheet.createRow(row++);
        createCell(execRow, 0, "실행일시: " + str(audit.get("executedAt")), s.normal);
        row++;

        // OK/WARN/FAIL 항목 테이블
        List<Map<String, Object>> items = (List<Map<String, Object>>) audit.get("items");
        if (items != null && !items.isEmpty()) {
            row = writeSectionHeader(sheet, s, row, "OS Audit 검증 항목", "");
            row = writeCheckTable(sheet, s, row, items);
            row++;
        }

        // 섹션 구분 타이틀
        XSSFRow secTitleRow = sheet.createRow(row++);
        XSSFCell secTitleCell = secTitleRow.createCell(0);
        secTitleCell.setCellValue("[ OS Audit 원문 섹션 ]");
        secTitleCell.setCellStyle(s.tableHeader);
        row++;

        for (Map.Entry<String, List<String>> entry : sections.entrySet()) {
            // 섹션 헤더
            XSSFRow secRow = sheet.createRow(row++);
            XSSFCell secCell = secRow.createCell(0);
            secCell.setCellValue("[ " + entry.getKey() + " ]");
            secCell.setCellStyle(s.sectionHeader);

            // 섹션 내용
            List<String> lines = entry.getValue();
            if (lines != null) {
                for (String line : lines) {
                    XSSFRow lineRow = sheet.createRow(row++);
                    createCell(lineRow, 0, line, s.normal);
                }
            }
            row++; // 섹션 간 빈 줄
        }
    }

    // ── 공통: 서버 정보 행 ───────────────────────────────────────────────────
    private int writeInfoRow(XSSFSheet sheet, Styles s, int rowIdx, Map<String, Object> report) {
        XSSFRow row = sheet.createRow(rowIdx);
        row.setHeight((short) 500);
        createCell(row, 0, "서버명", s.infoLabel);
        createCell(row, 1, str(report.get("serverName")), s.infoValue);
        createCell(row, 2, "IP", s.infoLabel);
        createCell(row, 3, str(report.get("ipAddress")), s.infoValue);
        createCell(row, 4, "생성일시", s.infoLabel);
        createCell(row, 5, str(report.get("generatedAt")), s.infoValue);
        return rowIdx + 2; // 빈 줄 한 칸
    }

    // ── 공통: 셋업 결과 테이블 ────────────────────────────────────────────────
    private int writeSetupTable(XSSFSheet sheet, Styles s, int rowIdx, List<Map<String, Object>> items) {
        // 헤더
        XSSFRow header = sheet.createRow(rowIdx++);
        header.setHeight((short) 450);
        String[] heads = {"Playbook", "설명", "상태", "시작 시간", "종료 시간"};
        for (int i = 0; i < heads.length; i++) createCell(header, i, heads[i], s.tableHeader);

        if (items == null || items.isEmpty()) {
            createCell(sheet.createRow(rowIdx++), 0, "데이터 없음", s.normal);
            return rowIdx;
        }

        for (Map<String, Object> item : items) {
            XSSFRow row = sheet.createRow(rowIdx++);
            row.setHeight((short) 380);
            String status = str(item.get("status"));
            createCell(row, 0, str(item.get("playbookName")), s.normal);
            createCell(row, 1, playbookDesc(str(item.get("playbookName"))), s.normal);
            createCell(row, 2, status, statusStyle(s, status));
            createCell(row, 3, str(item.get("startedAt")), s.normal);
            createCell(row, 4, str(item.get("finishedAt")), s.normal);
        }
        return rowIdx;
    }

    // ── 공통: 섹션 제목 행 ───────────────────────────────────────────────────
    private int writeSectionHeader(XSSFSheet sheet, Styles s, int rowIdx, String title, String sub) {
        XSSFRow r1 = sheet.createRow(rowIdx++);
        r1.setHeight((short) 500);
        XSSFCell c = r1.createCell(0);
        c.setCellValue(title);
        c.setCellStyle(s.sectionHeader);
        createCell(r1, 1, sub, s.normal);

        XSSFRow header = sheet.createRow(rowIdx++);
        header.setHeight((short) 420);
        createCell(header, 0, "상태", s.tableHeader);
        createCell(header, 1, "항목", s.tableHeader);
        return rowIdx;
    }

    // ── 공통: OK/WARN/FAIL 체크 테이블 ──────────────────────────────────────
    private int writeCheckTable(XSSFSheet sheet, Styles s, int rowIdx, List<Map<String, Object>> items) {
        if (items == null || items.isEmpty()) return rowIdx;
        for (Map<String, Object> item : items) {
            XSSFRow row = sheet.createRow(rowIdx++);
            String st = str(item.get("status"));
            createCell(row, 0, st, statusStyle(s, st));
            createCell(row, 1, str(item.get("detail")), s.normal);
        }
        return rowIdx;
    }

    // ── 헬퍼 ──────────────────────────────────────────────────────────────────
    private void createCell(XSSFRow row, int col, String value, XSSFCellStyle style) {
        XSSFCell cell = row.createCell(col);
        cell.setCellValue(value != null ? value : "");
        if (style != null) cell.setCellStyle(style);
    }

    private XSSFCellStyle statusStyle(Styles s, String status) {
        if (status == null) return s.normal;
        switch (status) {
            case "SUCCESS": case "OK": return s.ok;
            case "FAIL":   return s.fail;
            case "WARN":   return s.warn;
            default:       return s.normal;
        }
    }

    private String str(Object o) {
        if (o == null) return "-";
        String v = o.toString();
        // LocalDateTime 문자열 보기 좋게 자르기
        if (v.length() > 19 && v.contains("T")) v = v.substring(0, 19).replace("T", " ");
        return v;
    }

    private String playbookDesc(String name) {
        if (name == null || name.startsWith("deploy:")) return name != null ? name : "-";
        java.util.Map<String, String> desc = new java.util.LinkedHashMap<>();
        desc.put("0_auto_pass.yml",       "SSH 키 교환, SELinux 비활성화");
        desc.put("1_PAM_limits.yml",      "PAM limits 설정");
        desc.put("2_systemctl_stop.yml",  "불필요 서비스 중지");
        desc.put("3_sysctl.yml",          "커널 파라미터 튜닝");
        desc.put("4_ntp.yml",             "NTP 설치 및 설정");
        desc.put("5_visudo_vcs.yml",      "vcs 그룹 sudo 권한 부여");
        desc.put("6_RMQ_vcs.yml",         "RabbitMQ 설치 및 설정");
        desc.put("7_openjdk.yml",         "OpenJDK 1.8 설치");
        desc.put("8-1_mariaDB.yml",       "MariaDB 설치, DB/계정 생성");
        desc.put("8-2_mariaDB_chown.yml", "MariaDB 디렉토리 권한 설정");
        desc.put("9-1_group_vcs.yml",     "vcs 계정/그룹 생성");
        desc.put("9-2_chmod_vcs.yml",     "vcs 디렉토리 권한 설정");
        desc.put("10-1_group_vcweb.yml",  "vcweb 계정/그룹 생성");
        desc.put("10-2_chmod_vcweb.yml",  "vcweb 디렉토리 권한 설정");
        desc.put("11_vcs_dic.yml",        "VCS 패키지 배포 및 RPM 설치");
        desc.put("12_Cron_root.yml",      "헬스체크 Cron 등록");
        desc.put("13_service_start.yml",  "서비스 init.d 등록 및 활성화");
        desc.put("14_ramdisk.yml",        "Ramdisk 마운트 설정");
        desc.put("15_ldconf.yml",         "ld.so 설정");
        desc.put("15_rclocal.yml",        "rc.local ring buffer, iptables 설정");
        desc.put("16_watermark.yml",      "Watermark 파일 복사");
        return desc.getOrDefault(name, "-");
    }

    // ── 스타일 모음 ────────────────────────────────────────────────────────────
    static class Styles {
        final XSSFCellStyle tableHeader, infoLabel, infoValue, sectionHeader;
        final XSSFCellStyle normal, ok, fail, warn;

        Styles(XSSFWorkbook wb) {
            XSSFFont boldWhite = wb.createFont();
            boldWhite.setBold(true);
            boldWhite.setColor(new XSSFColor(new byte[]{(byte)0xFF,(byte)0xFF,(byte)0xFF}, null));

            XSSFFont bold = wb.createFont();
            bold.setBold(true);

            XSSFFont boldGreen = wb.createFont();
            boldGreen.setBold(true);
            boldGreen.setColor(new XSSFColor(new byte[]{(byte)0x16,(byte)0x65,(byte)0x34}, null));

            XSSFFont boldRed = wb.createFont();
            boldRed.setBold(true);
            boldRed.setColor(new XSSFColor(new byte[]{(byte)0x99,(byte)0x1B,(byte)0x1B}, null));

            XSSFFont boldAmber = wb.createFont();
            boldAmber.setBold(true);
            boldAmber.setColor(new XSSFColor(new byte[]{(byte)0x92,(byte)0x40,(byte)0x0E}, null));

            tableHeader  = style(wb, new byte[]{(byte)0x25,(byte)0x63,(byte)0xEB}, boldWhite, true);
            infoLabel    = style(wb, new byte[]{(byte)0x1E,(byte)0x40,(byte)0xAF}, boldWhite, true);
            infoValue    = style(wb, new byte[]{(byte)0xDB,(byte)0xEA,(byte)0xFE}, bold,      false);
            sectionHeader= style(wb, new byte[]{(byte)0xE8,(byte)0xF0,(byte)0xFE}, bold,      false);
            normal       = style(wb, null,                                           null,      false);
            ok           = style(wb, new byte[]{(byte)0xDC,(byte)0xFC,(byte)0xE7}, boldGreen, true);
            fail         = style(wb, new byte[]{(byte)0xFE,(byte)0xE2,(byte)0xE2}, boldRed,   true);
            warn         = style(wb, new byte[]{(byte)0xFE,(byte)0xF3,(byte)0xC7}, boldAmber, true);
        }

        private XSSFCellStyle style(XSSFWorkbook wb, byte[] bgRgb, XSSFFont font, boolean center) {
            XSSFCellStyle cs = wb.createCellStyle();
            if (bgRgb != null) {
                cs.setFillForegroundColor(new XSSFColor(bgRgb, null));
                cs.setFillPattern(FillPatternType.SOLID_FOREGROUND);
            }
            if (font != null) cs.setFont(font);
            if (center) cs.setAlignment(HorizontalAlignment.CENTER);
            cs.setVerticalAlignment(VerticalAlignment.CENTER);
            setBorder(cs);
            cs.setWrapText(false);
            return cs;
        }

        private void setBorder(XSSFCellStyle cs) {
            cs.setBorderTop(BorderStyle.THIN);
            cs.setBorderBottom(BorderStyle.THIN);
            cs.setBorderLeft(BorderStyle.THIN);
            cs.setBorderRight(BorderStyle.THIN);
        }
    }
}
