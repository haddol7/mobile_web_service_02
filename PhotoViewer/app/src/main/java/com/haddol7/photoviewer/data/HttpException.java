package com.haddol7.photoviewer.data;

import java.io.IOException;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

public final class HttpException extends IOException {
    public final int status;
    public final String body;
    public final Map<String, String> fields;
    public final Long revision;
    public HttpException(int status, String message, String body, Map<String, String> fields, Long revision) {
        super(message); this.status = status; this.body = body;
        this.fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields)); this.revision = revision;
    }
}
