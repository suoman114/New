package com.lter.infra.controller;

import com.lter.infra.common.ApiResponse;
import com.lter.infra.service.ExcelReportService;
import com.lter.infra.service.HtmlReportService;
import com.lter.infra.service.ReportService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/report")
@RequiredArgsConstructor
public class ReportController {

    private final ReportService reportService;
    private final ExcelReportService excelReportService;
    private final HtmlReportService htmlReportService;

    @GetMapping("/{serverId}")
    public ResponseEntity<ApiResponse<Map<String, Object>>> getReport(@PathVariable Long serverId) {
        return ResponseEntity.ok(ApiResponse.ok(reportService.buildReport(serverId)));
    }

    @GetMapping("/{serverId}/html/{phase}")
    public ResponseEntity<byte[]> viewOrDownloadHtml(@PathVariable Long serverId,
                                                     @PathVariable String phase,
                                                     @RequestParam(required = false) String date,
                                                     @RequestParam(defaultValue = "false") boolean download) {
        LocalDate selectedDate = (date != null && !date.isEmpty()) ? LocalDate.parse(date) : null;
        String html = htmlReportService.generateReport(serverId, phase, selectedDate);
        byte[] bytes = html.getBytes(StandardCharsets.UTF_8);

        String serverName = String.valueOf(
                reportService.buildReport(serverId).getOrDefault("serverName", "report"));
        String filename = "report_" + serverName + "_" + phase + "_" + LocalDate.now() + ".html";

        ContentDisposition disposition = download
                ? ContentDisposition.attachment().filename(filename).build()
                : ContentDisposition.inline().filename(filename).build();

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType("text/html; charset=UTF-8"));
        headers.setContentDisposition(disposition);
        return ResponseEntity.ok().headers(headers).body(bytes);
    }

    @GetMapping("/{serverId}/excel")
    public ResponseEntity<byte[]> downloadExcel(@PathVariable Long serverId) throws IOException {
        Map<String, Object> report = reportService.buildReport(serverId);
        String serverName = String.valueOf(report.getOrDefault("serverName", "report"));
        byte[] bytes = excelReportService.generateExcel(serverId);

        String filename = "report_" + serverName + "_" + LocalDate.now() + ".xlsx";
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.parseMediaType(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"));
        headers.setContentDisposition(ContentDisposition.attachment()
                .filename(filename).build());
        return ResponseEntity.ok().headers(headers).body(bytes);
    }
}
