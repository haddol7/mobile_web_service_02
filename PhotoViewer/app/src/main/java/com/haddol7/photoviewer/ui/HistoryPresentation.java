package com.haddol7.photoviewer.ui;

import org.json.*;
import java.util.*;

/** Presentation groups keep every original frame and never merge person identities. */
public final class HistoryPresentation {
    private HistoryPresentation(){}
    public record Scene(JSONObject representative,JSONArray frames){}
    private static int score(JSONObject row){
        int result=row.optJSONArray("passages")==null?0:row.optJSONArray("passages").length()*10;
        JSONArray tracks=row.optJSONArray("tracks");if(tracks!=null)for(int i=0;i<tracks.length();i++){
            JSONObject track=tracks.optJSONObject(i);if(track==null)continue;
            if(!track.isNull("confirmed"))result+=4;else if(!track.isNull("candidate")&&!track.optBoolean("reviewed"))result+=2;}
        return result;
    }
    public static List<Scene> scenes(JSONArray rows)throws JSONException{
        if(rows.length()>0&&rows.getJSONObject(0).optJSONArray("frames")!=null){
            List<Scene> sessions=new ArrayList<>();for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);sessions.add(new Scene(row,row.getJSONArray("frames")));}return sessions;
        }
        Map<String,List<JSONObject>> groups=new LinkedHashMap<>();
        for(int i=0;i<rows.length();i++){
            JSONObject row=rows.getJSONObject(i);String bucket;
            if(!row.isNull("video_seconds"))bucket="video:"+(long)Math.floor(row.getDouble("video_seconds")/10);
            else if(!row.isNull("observed_at")&&row.optString("observed_at").length()>=18)bucket="time:"+row.optString("observed_at").substring(0,18);
            else bucket="frame:"+row.getString("id");
            String key=row.optString("session_id",row.getString("id"))+":"+bucket;
            groups.computeIfAbsent(key,k->new ArrayList<>()).add(row);
        }
        List<Scene> result=new ArrayList<>();
        for(List<JSONObject> frames:groups.values()){
            JSONObject representative=frames.get(0);for(JSONObject frame:frames)if(score(frame)>score(representative))representative=frame;
            frames.sort(Comparator.comparingDouble(frame->frame.optDouble("video_seconds",Double.MAX_VALUE)));
            result.add(new Scene(representative,new JSONArray(frames)));
        }
        return result;
    }
    public static String shortAnswer(String canonical){int stop=canonical.indexOf("다. ");return stop<0?canonical:canonical.substring(0,stop+2);}
}
