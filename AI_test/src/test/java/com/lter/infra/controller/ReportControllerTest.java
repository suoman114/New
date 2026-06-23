package com.lter.infra.controller;

import com.lter.infra.service.ExcelReportService;
import com.lter.infra.service.HtmlReportService;
import com.lter.infra.service.ReportService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * ReportController REST 계약 테스트 (pkg-report).
 * JSON 보고서, HTML 인라인/다운로드, Excel 다운로드 헤더/콘텐츠타입 검증.
 */
@WebMvcTest(ReportController.class)
class ReportControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ReportService reportService;
    @MockBean
    private ExcelReportService excelReportService;
    @MockBean
    private HtmlReportService htmlReportService;

    private Map<String, Object> sampleReport() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("serverId", 1L);
        m.put("serverName", "vcs-01");
        return m;
    }

    @Test
    void getReport_returnsJson() throws Exception {
        when(reportService.buildReport(1L)).thenReturn(sampleReport());
        mockMvc.perform(get("/api/v1/report/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.serverName").value("vcs-01"));
    }

    @Test
    void html_inline_byDefault() throws Exception {
        when(reportService.buildReport(anyLong())).thenReturn(sampleReport());
        when(htmlReportService.generateReport(eq(1L), eq("platform"), any()))
                .thenReturn("<html>OK</html>");

        mockMvc.perform(get("/api/v1/report/1/html/platform"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("text/html"))
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("inline")))
                .andExpect(content().string("<html>OK</html>"));
    }

    @Test
    void html_download_setsAttachment() throws Exception {
        when(reportService.buildReport(anyLong())).thenReturn(sampleReport());
        when(htmlReportService.generateReport(anyLong(), any(), any()))
                .thenReturn("<html>OK</html>");

        mockMvc.perform(get("/api/v1/report/1/html/postsetup").param("download", "true"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("attachment")));
    }

    @Test
    void excel_download_setsXlsxContentType() throws Exception {
        when(reportService.buildReport(anyLong())).thenReturn(sampleReport());
        when(excelReportService.generateExcel(1L)).thenReturn(new byte[]{1, 2, 3});

        mockMvc.perform(get("/api/v1/report/1/excel"))
                .andExpect(status().isOk())
                .andExpect(header().string("Content-Type",
                        org.hamcrest.Matchers.containsString("spreadsheetml.sheet")))
                .andExpect(header().string("Content-Disposition",
                        org.hamcrest.Matchers.containsString("attachment")));
    }
}
