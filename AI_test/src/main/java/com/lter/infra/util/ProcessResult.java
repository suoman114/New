package com.lter.infra.util;

import lombok.Getter;

@Getter
public class ProcessResult {

    private final int exitCode;
    private final String stdOut;
    private final String stdErr;

    public ProcessResult(int exitCode, String stdOut, String stdErr) {
        this.exitCode = exitCode;
        this.stdOut = stdOut;
        this.stdErr = stdErr;
    }

    public boolean isSuccess() {
        return exitCode == 0;
    }
}
