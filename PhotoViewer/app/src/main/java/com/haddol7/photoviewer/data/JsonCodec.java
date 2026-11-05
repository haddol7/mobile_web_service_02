package com.haddol7.photoviewer.data;

import com.haddol7.photoviewer.model.*;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Android's real org.json is tested on-device, not mocked android.jar JVM stubs. */
public final class JsonCodec {
    private JsonCodec() {}
    public static PhotoPost post(JSONObject value) throws JSONException {
        return new PhotoPost(value.getLong("id"), value.getLong("author"), value.getString("title"),
                value.getString("text"), nullableString(value, "image"), value.getString("created_date"),
                nullableString(value, "published_date"));
    }
    public static List<PhotoPost> posts(JSONArray values) throws JSONException {
        List<PhotoPost> result = new ArrayList<>();
        for (int i = 0; i < values.length(); i++) result.add(post(values.getJSONObject(i)));
        return Collections.unmodifiableList(result);
    }
    public static SessionInfo session(JSONObject value) throws JSONException {
        JSONObject user = value.isNull("user") ? null : value.getJSONObject("user");
        return new SessionInfo(user == null ? null : user.getLong("id"), user == null ? null : user.getString("username"),
                value.optBoolean("can_publish", false), value.getString("csrf_token"),value.optBoolean("can_manage_all",false));
    }
    private static Long nullableLong(JSONObject value, String key) throws JSONException { return value.isNull(key) ? null : value.getLong(key); }
    private static String nullableString(JSONObject value, String key) throws JSONException { return value.isNull(key) ? null : value.getString(key); }
}
