package com.haddol7.photoviewer.data;

import java.nio.charset.StandardCharsets;
import org.junit.Test;
import static org.junit.Assert.*;

public class MultipartBodyTest {
    @Test public void preservesBinaryAndKoreanFields() throws Exception {
        byte[] pixels = new byte[]{0, (byte) 255, 13, 10, 1, 2, 0};
        MultipartBody body = MultipartBody.photo("강아지 사진", "본문", pixels, "image/png", "dog.png");
        String boundary = body.contentType.substring(body.contentType.indexOf("boundary=") + 9);
        byte[] marker = "Content-Type: image/png\r\n\r\n".getBytes(StandardCharsets.UTF_8);
        int start = indexOf(body.bytes, marker) + marker.length; assertTrue(start >= marker.length);
        assertArrayEquals(pixels, java.util.Arrays.copyOfRange(body.bytes, start, start + pixels.length));
        String text = new String(body.bytes, StandardCharsets.UTF_8);
        assertTrue(text.contains("강아지 사진")); assertTrue(text.contains("name=\"title\""));
        assertTrue(text.endsWith("\r\n--" + boundary + "--\r\n"));
        assertFalse(text.contains("name=\"author\""));
    }
    @Test public void filenameCannotInjectHeadersOrPaths() throws Exception {
        MultipartBody body = MultipartBody.photo("title", "text", new byte[]{1}, "image/png", "C:\\fake\\dog\r\n\".png");
        String text = new String(body.bytes, StandardCharsets.UTF_8);
        assertTrue(text.contains("filename=\"dog_.png\"")); assertFalse(text.contains("C:"));
    }
    @Test(expected = IllegalArgumentException.class) public void imageLimitEnforced() throws Exception {
        MultipartBody.photo("title", "text", new byte[MultipartBody.MAX_IMAGE_BYTES + 1], "image/png", "dog.png");
    }
    @Test(expected = IllegalArgumentException.class) public void mimeNotArbitrary() throws Exception {
        MultipartBody.photo("title", "text", new byte[]{1}, "text/html", "dog.png");
    }
    private static int indexOf(byte[] values, byte[] needle) {
        outer: for (int i = 0; i <= values.length - needle.length; i++) {
            for (int j = 0; j < needle.length; j++) if (values[i+j] != needle[j]) continue outer;
            return i;
        }
        return -1;
    }
}
