package com.lter.infra.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lter.infra.domain.dto.ServerRequest;
import com.lter.infra.domain.entity.TargetServer;
import com.lter.infra.service.ServerService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Collections;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * ServerController REST 계약 테스트 (pkg-installer-backend).
 * ApiResponse 응답 형태(success/message/data), 검증 실패 400, 라우팅을 슬라이스로 검증.
 */
@WebMvcTest(ServerController.class)
class ServerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private ServerService serverService;

    private TargetServer sampleServer() {
        TargetServer s = new TargetServer();
        s.setId(1L);
        s.setServerName("vcs-01");
        s.setIpAddress("10.0.0.10");
        s.setOsType(TargetServer.OsType.CENTOS);
        return s;
    }

    private ServerRequest validRequest() {
        ServerRequest r = new ServerRequest();
        r.setServerName("vcs-01");
        r.setIpAddress("10.0.0.10");
        r.setOsType(TargetServer.OsType.CENTOS);
        return r;
    }

    @Test
    void findAll_returnsOkWrappedList() throws Exception {
        when(serverService.findAll()).thenReturn(Collections.singletonList(sampleServer()));

        mockMvc.perform(get("/api/v1/servers"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data[0].serverName").value("vcs-01"));
    }

    @Test
    void findById_returnsOk() throws Exception {
        when(serverService.findById(1L)).thenReturn(sampleServer());

        mockMvc.perform(get("/api/v1/servers/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.ipAddress").value("10.0.0.10"));
    }

    @Test
    void register_valid_returns201WithMessage() throws Exception {
        when(serverService.register(any(ServerRequest.class))).thenReturn(sampleServer());

        mockMvc.perform(post("/api/v1/servers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.message").value("서버가 등록되었습니다."));
    }

    @Test
    void register_invalidIp_returns400Fail() throws Exception {
        ServerRequest bad = validRequest();
        bad.setIpAddress("999.1.1.1"); // 잘못된 IP

        mockMvc.perform(post("/api/v1/servers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(bad)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void register_blankName_returns400Fail() throws Exception {
        ServerRequest bad = validRequest();
        bad.setServerName("  ");

        mockMvc.perform(post("/api/v1/servers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(bad)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void registerBulk_empty_returns400Fail() throws Exception {
        mockMvc.perform(post("/api/v1/servers/bulk")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("[]"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.success").value(false));
    }

    @Test
    void delete_returnsOk() throws Exception {
        mockMvc.perform(delete("/api/v1/servers/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.message").value("서버가 삭제되었습니다."));
    }
}
