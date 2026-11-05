package com.haddol7.photoviewer.model;
public final class SessionInfo {
    public final Long userId;
    public final boolean canPublish;
    public final boolean canManageAll;
    public final String username, csrfToken;
    public SessionInfo(Long userId, String username, boolean canPublish, String csrfToken) {
        this(userId,username,canPublish,csrfToken,false);
    }
    public SessionInfo(Long userId, String username, boolean canPublish, String csrfToken, boolean canManageAll) {
        this.userId=userId; this.username=username; this.canPublish=canPublish; this.csrfToken=csrfToken;
        this.canManageAll=canManageAll;
    }
    public boolean isAuthenticated() { return userId != null; }
}
