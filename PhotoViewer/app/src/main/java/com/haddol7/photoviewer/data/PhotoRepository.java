package com.haddol7.photoviewer.data;

import com.haddol7.photoviewer.model.*;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Synchronous network boundary. The Activity owns its worker executor. */
public final class PhotoRepository {
    private static final int MAX_JSON_BYTES = 8 * 1024 * 1024;
    private final URI base;
    private final String origin;
    private final CookieManager cookies = new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    private volatile String csrfToken;

    public PhotoRepository(String baseUrl) {
        URI parsed;
        try { parsed = URI.create(baseUrl.trim()); }
        catch (RuntimeException error) { throw new IllegalArgumentException("서버 URL이 올바르지 않습니다."); }
        if ((!"http".equalsIgnoreCase(parsed.getScheme()) && !"https".equalsIgnoreCase(parsed.getScheme()))
                || parsed.getHost() == null || parsed.getUserInfo() != null || parsed.getQuery() != null
                || parsed.getFragment() != null || (parsed.getPath() != null && !parsed.getPath().isEmpty() && !"/".equals(parsed.getPath())))
            throw new IllegalArgumentException("http(s)://서버주소/ 형식으로 입력하세요.");
        origin = parsed.getScheme().toLowerCase(Locale.ROOT) + "://" + parsed.getRawAuthority();
        base = URI.create(origin + "/");
    }
    public String getBaseUrl() { return base.toString(); }
    public void clearSession() {
        synchronized (cookies) { cookies.getCookieStore().removeAll(); }
        csrfToken = null;
    }
    public SessionInfo me() throws IOException {
        SessionInfo result = decodeSession(jsonObject(api("GET", "api/v1/auth/me/", null, null, false)));
        csrfToken = result.csrfToken; return result;
    }
    public SessionInfo login(String username, String password) throws IOException {
        if (username == null || username.trim().isEmpty() || password == null || password.isEmpty())
            throw new IllegalArgumentException("아이디와 비밀번호를 입력하세요.");
        // Do not mistake a previous user's still-valid cookie for a successful login.
        clearSession(); ensureCsrf();
        String fields = "username=" + encode(username) + "&password=" + encode(password)
                + "&next=" + encode("/api/v1/auth/me/");
        Response response = execute("POST", base.resolve("accounts/login/"), utf8(fields),
                "application/x-www-form-urlencoded", true, true, MAX_JSON_BYTES);
        if (response.status != 302 && response.status != 303) {
            if (response.status >= 400) throw error(response);
            throw new HttpException(401, "아이디 또는 비밀번호를 확인하세요.", "", Collections.emptyMap(), null);
        }
        checkedRedirect(response);
        SessionInfo result = me();
        if (!result.isAuthenticated() || !username.trim().equals(result.username)) {
            clearSession(); throw new IOException("로그인 세션 확인에 실패했습니다.");
        }
        return result;
    }
    public SessionInfo logout() throws IOException {
        ensureCsrf();
        Response response = execute("POST", base.resolve("accounts/logout/"), new byte[0],
                "application/x-www-form-urlencoded", true, true, MAX_JSON_BYTES);
        if (response.status >= 300 && response.status < 400) checkedRedirect(response);
        else if (response.status < 200 || response.status >= 300) throw error(response);
        // Commit the local logout as soon as the server acknowledges it. Cookie
        // disposal also prevents an old session or CSRF token being reused if a
        // subsequent synchronization fails. me()/ensureCsrf() seeds a new
        // anonymous CSRF context only when a later request actually needs one.
        clearSession();
        return new SessionInfo(null, null, false, null);
    }
    public List<PhotoPost> getPosts() throws IOException {
        try { return JsonCodec.posts(jsonArray(api("GET", "api_root/Post/", null, null, false))); }
        catch (JSONException error) { throw invalidJson(error); }
    }
    public PhotoPost upload(String title, String text, byte[] image, String mime, String filename) throws IOException {
        return upload(title,text,image,mime,filename,null);
    }
    public PhotoPost upload(String title, String text, byte[] image, String mime, String filename,String content) throws IOException {
        MultipartBody body = MultipartBody.photo(title, text, image, mime, filename,content); ensureCsrf();
        try { return JsonCodec.post(jsonObject(api("POST", "api_root/Post/", body.bytes, body.contentType, true))); }
        catch (JSONException error) { throw invalidJson(error); }
    }
    public JSONObject content(long id) throws IOException {
        requireId(id);return jsonObject(api("GET","api/v1/posts/"+id+"/content/",null,null,false));
    }
    public JSONObject summaries(List<Long> ids) throws IOException {
        if(ids.isEmpty()||ids.size()>50)throw new IllegalArgumentException("사진 ID는 1–50개가 필요합니다.");
        StringBuilder list=new StringBuilder();for(long id:ids){requireId(id);if(list.length()>0)list.append(',');list.append(id);}
        return jsonObject(api("GET","api/v1/post-contents/?ids="+list,null,null,false));
    }
    public JSONObject browse(String query,String theme,String tag,boolean mine,String cursor) throws IOException {
        boolean search=query!=null&&!query.trim().isEmpty();
        String path="api/v1/"+(search?"photo-text-search/":"content-posts/")+"?limit=20";
        if(search)path+="&q="+encode(query);
        if(theme!=null&&!theme.isEmpty())path+="&theme="+encode(theme);
        if(tag!=null&&!tag.isEmpty())path+="&tag="+encode(tag);
        if(mine)path+="&author=me";
        if(cursor!=null&&!cursor.isEmpty())path+="&cursor="+encode(cursor);
        return jsonObject(api("GET",path,null,null,false));
    }
    public JSONObject saveContent(long id,JSONObject content) throws IOException {
        requireId(id);ensureCsrf();return jsonObject(api("PATCH","api/v1/posts/"+id+"/content/",utf8(content.toString()),"application/json",true));
    }
    public PhotoPost updatePhoto(long id,String title,String text,byte[] image,String content) throws IOException {
        requireId(id);ensureCsrf();
        MultipartBody body=MultipartBody.photo(title,text,image,"image/jpeg","public-photo.jpg",content);
        try{return JsonCodec.post(jsonObject(api("PATCH","api_root/Post/"+id+"/",body.bytes,body.contentType,true)));}
        catch(JSONException error){throw invalidJson(error);}
    }
    public PhotoPost updateText(long id,String title,String text,JSONObject content) throws IOException {
        requireId(id);ensureCsrf();
        try {
            JSONObject data=new JSONObject().put("title",title).put("text",text).put("photo_content",content);
            return JsonCodec.post(jsonObject(api("PATCH","api_root/Post/"+id+"/",utf8(data.toString()),"application/json",true)));
        } catch(JSONException error){throw invalidJson(error);}
    }
    public void deletePhoto(long id) throws IOException {requireId(id);ensureCsrf();api("DELETE","api_root/Post/"+id+"/",null,null,true);}
    public byte[] downloadPhoto(String imageUrl) throws IOException {
        URI target;
        try { target = base.resolve(imageUrl); }
        catch (RuntimeException error) { throw new IOException("사진 주소가 올바르지 않습니다."); }
        requireSameOrigin(target);
        Response response = execute("GET", target, null, null, false, true, MultipartBody.MAX_IMAGE_BYTES);
        response = followGetRedirects(response, MultipartBody.MAX_IMAGE_BYTES, true);
        if (response.status < 200 || response.status >= 300) throw error(response);
        return response.bytes;
    }
    /** Diagnostic text is deliberately separate from the JSONArray synchronization API. */
    public String captureRequest(String diagnosticBaseUrl) throws IOException {
        URI target;
        try { target = URI.create(diagnosticBaseUrl).resolve("/api_root/Post/"); }
        catch (RuntimeException error) { throw new IOException("진단 서버 주소가 올바르지 않습니다."); }
        String host = target.getHost();
        if (!"http".equals(target.getScheme()) || !("10.0.2.2".equals(host) || "127.0.0.1".equals(host) || "localhost".equals(host))
                || target.getPort() != 8002 || target.getUserInfo() != null) throw new IOException("요청 캡처는 로컬 8002 진단 서버만 사용합니다.");
        Response response = execute("GET", target, null, null, false, false, 64 * 1024);
        if (response.status != 200) throw error(response);
        return response.text();
    }
    private void ensureCsrf() throws IOException { if (csrfToken == null || csrfToken.isEmpty()) me(); }
    private Response api(String method, String path, byte[] body, String type, boolean csrf) throws IOException {
        Response response = execute(method, base.resolve(path), body, type, csrf, true, MAX_JSON_BYTES);
        if ("GET".equals(method)) response = followGetRedirects(response, MAX_JSON_BYTES, true);
        if (response.status < 200 || response.status >= 300) throw error(response);
        return response;
    }
    private Response followGetRedirects(Response response, int limit, boolean withCookies) throws IOException {
        for (int count = 0; response.status >= 300 && response.status < 400; count++) {
            if (count >= 3) throw new IOException("서버의 리디렉션 횟수가 너무 많습니다.");
            URI next = checkedRedirect(response);
            response = execute("GET", next, null, null, false, withCookies, limit);
        }
        return response;
    }
    private URI checkedRedirect(Response response) throws IOException {
        if (response.location == null) throw new IOException("서버 리디렉션 주소가 없습니다.");
        URI next;
        try { next = response.uri.resolve(response.location); }
        catch (IllegalArgumentException error) { throw new IOException("서버 리디렉션 주소가 올바르지 않습니다."); }
        requireSameOrigin(next); return next;
    }
    private void requireSameOrigin(URI uri) throws IOException {
        if (uri.getUserInfo() != null || !base.getScheme().equalsIgnoreCase(uri.getScheme())
                || !base.getHost().equalsIgnoreCase(uri.getHost()) || port(base) != port(uri))
            throw new IOException("다른 출처로 인증 정보나 사진 요청을 전송하지 않습니다.");
    }
    private static int port(URI uri) { return uri.getPort() >= 0 ? uri.getPort() : ("https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80); }
    private Response execute(String method, URI uri, byte[] body, String type, boolean csrf, boolean withCookies, int limit) throws IOException {
        if (withCookies) requireSameOrigin(uri);
        HttpURLConnection connection = (HttpURLConnection) uri.toURL().openConnection();
        connection.setConnectTimeout(10000); connection.setReadTimeout(15000);
        connection.setInstanceFollowRedirects(false); connection.setUseCaches(false);
        try {
            connection.setRequestMethod(method);
            connection.setRequestProperty("Accept", withCookies ? "application/json" : "text/plain");
            if (withCookies) {
                Map<String, List<String>> headers;
                synchronized (cookies) { headers = cookies.get(uri, Collections.emptyMap()); }
                for (Map.Entry<String, List<String>> header : headers.entrySet())
                    if (!header.getValue().isEmpty()) connection.setRequestProperty(header.getKey(), cookieValues(header.getValue()));
            }
            if (csrf) {
                if (csrfToken == null || csrfToken.isEmpty()) throw new IOException("CSRF 토큰을 먼저 받아야 합니다.");
                connection.setRequestProperty("X-CSRFToken", csrfToken); connection.setRequestProperty("Origin", origin);
            }
            if (body != null) {
                connection.setDoOutput(true); connection.setRequestProperty("Content-Type", type);
                connection.setFixedLengthStreamingMode(body.length);
                try (OutputStream output = connection.getOutputStream()) { output.write(body); }
            }
            int status = connection.getResponseCode();
            if (withCookies) synchronized (cookies) { cookies.put(uri, connection.getHeaderFields()); }
            InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            byte[] bytes = stream == null ? new byte[0] : read(stream, limit);
            return new Response(uri, status, bytes, connection.getHeaderField("Location"));
        } finally { connection.disconnect(); }
    }
    private static byte[] read(InputStream source, int limit) throws IOException {
        try (InputStream input = source; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int size;
            while ((size = input.read(buffer)) != -1) {
                if (Thread.currentThread().isInterrupted()) throw new IOException("요청이 취소되었습니다.");
                if (output.size() + size > limit) throw new IOException("서버 응답의 허용 크기를 초과했습니다.");
                output.write(buffer, 0, size);
            }
            return output.toByteArray();
        }
    }
    private static JSONObject jsonObject(Response response) throws IOException {
        try { return new JSONObject(response.text()); } catch (JSONException error) { throw invalidJson(error); }
    }
    private static JSONArray jsonArray(Response response) throws IOException {
        try { return new JSONArray(response.text()); } catch (JSONException error) { throw invalidJson(error); }
    }
    private static SessionInfo decodeSession(JSONObject value) throws IOException {
        try { return JsonCodec.session(value); } catch (JSONException error) { throw invalidJson(error); }
    }
    private static IOException invalidJson(Exception error) { return new IOException("서버 JSON 응답 형식이 계약과 다릅니다.", error); }
    private static HttpException error(Response response) {
        Map<String, String> fields = new LinkedHashMap<>(); Long revision = null;
        String message = "HTTP " + response.status + ": 서버 요청에 실패했습니다.";
        try {
            JSONObject value = new JSONObject(response.text());
            java.util.Iterator<String> keys = value.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if ("revision".equals(key)||"current_revision".equals(key)) { revision = value.getLong(key); continue; }
                Object field = value.get(key);
                String text = field instanceof JSONArray ? joinErrors((JSONArray) field) : String.valueOf(field);
                fields.put(key, text);
            }
            if (fields.containsKey("detail")) message = fields.get("detail");
            else if (!fields.isEmpty()) {
                StringBuilder combined = new StringBuilder();
                for (Map.Entry<String, String> entry : fields.entrySet()) {
                    if (combined.length() > 0) combined.append('\n');
                    combined.append(entry.getKey()).append(": ").append(entry.getValue());
                }
                message = combined.toString();
            }
        } catch (JSONException ignored) { /* Preserve status for HTML CSRF/production error responses. */ }
        return new HttpException(response.status, message, response.text(), fields, revision);
    }
    private static String joinErrors(JSONArray values) throws JSONException {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < values.length(); i++) { if (i > 0) result.append(' '); result.append(values.get(i)); }
        return result.toString();
    }
    private static void requireId(long id) { if (id < 1) throw new IllegalArgumentException("ID는 양의 정수여야 합니다."); }
    private static byte[] utf8(String value) { return value.getBytes(StandardCharsets.UTF_8); }
    private static String cookieValues(List<String> values) {
        StringBuilder combined = new StringBuilder();
        for (String value : values) { if (combined.length() > 0) combined.append("; "); combined.append(value); }
        return combined.toString();
    }
    private static String encode(String value) throws IOException { return URLEncoder.encode(value, "UTF-8"); }
    private static final class Response {
        final URI uri; final int status; final byte[] bytes; final String location;
        Response(URI uri, int status, byte[] bytes, String location) { this.uri = uri; this.status = status; this.bytes = bytes; this.location = location; }
        String text() { return new String(bytes, StandardCharsets.UTF_8); }
    }
}
