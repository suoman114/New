package com.lter.infra.domain.dto;

import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
public class ApprovalRequest {
    /** true = 승인(다음 단계 진행), false = 취소 */
    private boolean approved;
}
