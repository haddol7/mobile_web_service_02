package com.haddol7.photoviewer.data;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Fixed-length binary-safe body also understood by the raw socket capture tool. */
public final class MultipartBody {
    public static final int MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    public final String contentType;
    public final byte[] bytes;
    private MultipartBody(String boundary, byte[] bytes) { contentType = "multipart/form-data; boundary=" + boundary; this.bytes = bytes; }
    public static MultipartBody photo(String title, String text, byte[] image, String mime, String filename) throws IOException {
        return photo(title,text,image,mime,filename,null);
    }
    public static MultipartBody photo(String title, String text, byte[] image, String mime, String filename, String content) throws IOException {
        if (title == null || title.trim().isEmpty()) throw new IllegalArgumentException("제목을 입력하세요.");
        if (text == null || text.trim().isEmpty()) throw new IllegalArgumentException("본문을 입력하세요.");
        if (image == null || image.length == 0 || image.length > MAX_IMAGE_BYTES) throw new IllegalArgumentException("사진은 5 MiB 이하여야 합니다.");
        if (!"image/jpeg".equals(mime) && !"image/png".equals(mime) && !"image/webp".equals(mime))
            throw new IllegalArgumentException("JPEG, PNG, WebP 사진만 지원합니다.");
        if (filename == null) throw new IllegalArgumentException("사진 파일 이름이 필요합니다.");
        String safeName = filename.replace('\\', '/'); safeName = safeName.substring(safeName.lastIndexOf('/') + 1);
        safeName = safeName.replace("\r", "").replace("\n", "").replace("\"", "_").replace("\u0000", "");
        if (safeName.isEmpty()) throw new IllegalArgumentException("사진 파일 이름이 필요합니다.");
        String boundary = "PhotoViewer-" + UUID.randomUUID();
        ByteArrayOutputStream output = new ByteArrayOutputStream(image.length + 2048);
        field(output, boundary, "title", title); field(output, boundary, "text", text);
        if(content!=null) {
            if(content.getBytes(StandardCharsets.UTF_8).length>64*1024)throw new IllegalArgumentException("분석 결과는 64KiB 이하여야 합니다.");
            field(output,boundary,"photo_content",content);
        }
        write(output, "--" + boundary + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"" + safeName
                + "\"\r\nContent-Type: " + mime + "\r\n\r\n");
        output.write(image); write(output, "\r\n--" + boundary + "--\r\n");
        return new MultipartBody(boundary, output.toByteArray());
    }
    private static void field(ByteArrayOutputStream output, String boundary, String key, String value) throws IOException {
        write(output, "--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + key + "\"\r\n\r\n" + value + "\r\n");
    }
    private static void write(ByteArrayOutputStream output, String value) throws IOException { output.write(value.getBytes(StandardCharsets.UTF_8)); }
}
