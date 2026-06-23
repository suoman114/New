package com.lter.infra.controller;

import com.lter.infra.service.SetupService;
import com.lter.infra.service.SseLogService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Arrays;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * SetupController REST 계약 테스트 (pkg-installer-backend).
 * serverIds 가드(400), jobKey 반환, playbook 목록 라우팅 검증.
 */
@WebMvcTest(SetupController.class)
class SetupControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private SetupService setupService;

    @MockBean
    private SseLogService sseLogService;

    @Test
    void runSetupAll_withoutBody_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/setup/all"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
        verify(setupService, never()).runSetupAllBatch(anyList(), any(), anyString());
    }

    @Test
    void runSetupAll_emptyServerIds_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/setup/all")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void runSetupAll_valid_returnsJobKeyAndInvokesService() throws Exception {
        mockMvc.perform(post("/api/v1/setup/all")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[1,2]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data").value(org.hamcrest.Matchers.startsWith("setup-all-")));
        verify(setupService, times(1)).runSetupAllBatch(anyList(), any(), anyString());
    }

    @Test
    void runOsSetup_valid_returnsOk() throws Exception {
        mockMvc.perform(post("/api/v1/setup/os")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[1]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data").value(org.hamcrest.Matchers.startsWith("setup-os-")));
        verify(setupService).runOsSetupBatch(anyList(), any(), anyString());
    }

    @Test
    void runPkgSetup_emptyIds_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/setup/package")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void allPlaybooks_returnsList() throws Exception {
        when(setupService.listAllPlaybooks())
                .thenReturn(Arrays.asList("0_auto_pass.yml", "6_RMQ_vcs.yml"));
        mockMvc.perform(get("/api/v1/setup/playbooks/all"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data[0]").value("0_auto_pass.yml"));
    }
}
