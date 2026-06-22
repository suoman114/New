package com.lter.infra.util;

import java.util.ArrayList;
import java.util.List;

/**
 * 폐쇄망 패키지 배포(pkg-offline-repo)에서 쓰는 원격 명령/URL 빌더 (순수 함수).
 *
 * <p>SCP 전송, SSH 원격 실행, 압축 해제 명령, Git 인증 URL 조합을 한 곳에서 구성한다.
 * 외부 프로세스 실행이나 IO 는 하지 않으므로 단위테스트 대상이다.
 * 폐쇄망 전제로 {@code StrictHostKeyChecking=no} 등 known_hosts 확인을 건너뛴다.
 */
public final class RemoteCommandBuilder {

    private RemoteCommandBuilder() {
    }

    /** 비밀번호가 있으면 sshpass 로 감싼다. */
    private static boolean hasPassword(String password) {
        return password != null && !password.trim().isEmpty();
    }

    /** SCP 전송 명령: 로컬 파일 → root@ip:remotePath. */
    public static List<String> scp(String localPath, String ip, int port,
                                   String password, String remotePath) {
        List<String> cmd = new ArrayList<>();
        if (hasPassword(password)) {
            cmd.add("sshpass");
            cmd.add("-p");
            cmd.add(password);
        }
        cmd.add("scp");
        cmd.add("-P");
        cmd.add(String.valueOf(port));
        cmd.add("-o");
        cmd.add("StrictHostKeyChecking=no");
        cmd.add("-o");
        cmd.add("ConnectTimeout=10");
        cmd.add(localPath);
        cmd.add("root@" + ip + ":" + remotePath);
        return cmd;
    }

    /** SSH 원격 명령 실행. 비밀번호 인증을 강제(PubkeyAuthentication=no)한다. */
    public static List<String> ssh(String ip, int port, String password, String remoteCmd) {
        List<String> cmd = new ArrayList<>();
        if (hasPassword(password)) {
            cmd.add("sshpass");
            cmd.add("-p");
            cmd.add(password);
        }
        cmd.add("ssh");
        cmd.add("-p");
        cmd.add(String.valueOf(port));
        cmd.add("-o");
        cmd.add("StrictHostKeyChecking=no");
        cmd.add("-o");
        cmd.add("ConnectTimeout=10");
        cmd.add("-o");
        cmd.add("PubkeyAuthentication=no");
        cmd.add("-o");
        cmd.add("PreferredAuthentications=password");
        cmd.add("root@" + ip);
        cmd.add(remoteCmd);
        return cmd;
    }

    /**
     * 파일 확장자에 따른 원격 압축 해제 명령.
     * 지원: .tar.gz/.tgz(tar), .gz(gunzip), .zip(unzip). 그 외는 안내 echo.
     */
    public static String extractCommand(String remotePath, String fileName) {
        String filePath = remotePath.endsWith("/")
                ? remotePath + fileName : remotePath + "/" + fileName;
        if (fileName.endsWith(".tar.gz") || fileName.endsWith(".tgz")) {
            return "tar -xzf " + filePath + " -C " + remotePath;
        } else if (fileName.endsWith(".gz")) {
            return "gunzip -f " + filePath;
        } else if (fileName.endsWith(".zip")) {
            return "unzip -o " + filePath + " -d " + remotePath;
        }
        return "echo 'unknown format: " + fileName + "'";
    }

    /**
     * PASSWORD 인증 Git URL 에 자격증명을 주입한다.
     * {@code http(s)://host/repo} → {@code http(s)://user:pass@host/repo}.
     * user/pass 가 없으면 원본 URL 을 그대로 반환.
     */
    public static String injectHttpCredentials(String repoUrl, String username, String password) {
        if (repoUrl == null || username == null || password == null) {
            return repoUrl;
        }
        String protocol = repoUrl.startsWith("https") ? "https" : "http";
        String rest = repoUrl.replaceFirst("https?://", "");
        return protocol + "://" + username + ":" + password + "@" + rest;
    }
}
