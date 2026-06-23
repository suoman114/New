package com.lter.infra.controller;

import com.lter.infra.service.ValidationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * ValidationController REST 계약 테스트 (pkg-validator/backend).
 * 단건/배치 실행 검증(@Valid: scriptId NotNull, serverIds NotEmpty).
 */
@WebMvcTest(ValidationController.class)
class ValidationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ValidationService validationService;

    @Test
    void run_valid_returnsOk() throws Exception {
        mockMvc.perform(post("/api/v1/validation/run/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"scriptId\":10}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true));
        verify(validationService).runValidation(any(), any());
    }

    @Test
    void run_missingScriptId_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/validation/run/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
        verify(validationService, never()).runValidation(any(), any());
    }

    @Test
    void runBatch_valid_returnsOk() throws Exception {
        mockMvc.perform(post("/api/v1/validation/run/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[1,2],\"scriptId\":10}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true));
        verify(validationService).runValidationBatch(anyList(), any());
    }

    @Test
    void runBatch_emptyServerIds_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/validation/run/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[],\"scriptId\":10}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void runBatch_missingScriptId_returns400() throws Exception {
        mockMvc.perform(post("/api/v1/validation/run/batch")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"serverIds\":[1]}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }
}
