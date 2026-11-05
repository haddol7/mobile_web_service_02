package com.haddol7.photoviewer.content;

import org.json.*;
import java.util.*;

/** Recoverable form metadata; large images stay in app-private files. */
public final class ComposerState {
    public String title="",text="",workingPath="",publicPath="",sha="",theme=null,tags="",ocrStatus="not_analyzed";
    public String analysisMessage="사진을 선택해주세요.";
    public String originalSha="";
    public boolean needsReview,themeConfirmed,tagsConfirmed;
    public final List<String> alternatives=new ArrayList<>();
    public final List<String> tagSuggestions=new ArrayList<>();
    public final List<String> heldCorrections=new ArrayList<>();
    public boolean faceChecked,themeEdited,tagsEdited;
    public int width,height;
    public long postId,revision;
    public final MosaicDraft mosaic=new MosaicDraft();
    public final List<VisionEngine.Line> lines=new ArrayList<>();
    public JSONObject packet() throws JSONException {
        if(sha.isEmpty()||width<=0||height<=0)throw new IllegalArgumentException("게시할 사진을 먼저 확인하세요.");
        JSONObject result=new JSONObject().put("schema_version",1).put("image_sha256",sha).put("width",width).put("height",height)
            .put("model_versions",new JSONObject().put("label","17.0.9").put("ocr_ko","16.0.1").put("ocr_latin","16.0.1"))
            .put("mapping_version",ThemeMapper.VERSION).put("theme_status",theme==null?"unclassified":"classified")
            .put("theme",theme==null?JSONObject.NULL:theme).put("theme_origin",theme==null?"unclassified":themeEdited?"user":"auto");
        JSONArray tagArray=new JSONArray();for(String tag:ThemeMapper.tags(tags))tagArray.put(new JSONObject().put("display",tag).put("origin",tagsEdited?"user":"auto"));
        JSONArray lineArray=new JSONArray();int total=0;
        if("ready".equals(ocrStatus))for(VisionEngine.Line line:lines)if(line.included) {
            String value=line.text.trim();int count=value.codePointCount(0,value.length());
            if(count==0||count>200||value.codePoints().anyMatch(Character::isISOControl))throw new IllegalArgumentException("사진 속 문구는 제어문자 없이 줄마다 1–200문자여야 합니다.");
            total+=count;JSONArray quad=new JSONArray();for(int i=0;i<8;i+=2)quad.put(new JSONArray().put(line.quad[i]).put(line.quad[i+1]));
            lineArray.put(new JSONObject().put("line_id",line.id).put("text",value).put("quad",quad).put("origin",line.origin));
        }
        if(lineArray.length()>100||total>8192)throw new IllegalArgumentException("검색 문구는 최대 100줄·전체 8192문자입니다. 포함할 문구를 줄여주세요.");
        result.put("tags",tagArray).put("ocr_status",ocrStatus).put("lines",lineArray);
        if(postId>0)result.put("expected_revision",revision);
        if(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length>64*1024)throw new IllegalArgumentException("분석 결과가 너무 큽니다. 검색 문구를 줄여주세요.");
        return result;
    }
    public JSONObject save() throws JSONException {
        JSONObject value=new JSONObject().put("title",title).put("text",text).put("workingPath",workingPath).put("publicPath",publicPath)
            .put("sha",sha).put("theme",theme==null?JSONObject.NULL:theme).put("tags",tags).put("ocrStatus",ocrStatus)
            .put("faceChecked",faceChecked).put("themeEdited",themeEdited).put("tagsEdited",tagsEdited).put("width",width).put("height",height)
            .put("postId",postId).put("revision",revision).put("analysisMessage",analysisMessage);
        JSONArray regions=new JSONArray();for(MosaicDraft.Region r:mosaic.regions())regions.put(new JSONObject().put("id",r.id).put("l",r.left).put("t",r.top).put("r",r.right).put("b",r.bottom).put("active",r.active).put("auto",r.automatic).put("strength",r.strength));
        JSONArray all=new JSONArray();for(VisionEngine.Line line:lines){JSONArray q=new JSONArray();for(float f:line.quad)q.put(f);all.put(new JSONObject().put("id",line.id).put("text",line.text).put("quad",q).put("origin",line.origin).put("included",line.included));}
        return value.put("regions",regions).put("allLines",all).put("originalSha",originalSha).put("needsReview",needsReview).put("heldCorrections",new JSONArray(heldCorrections)).put("themeConfirmed",themeConfirmed).put("tagsConfirmed",tagsConfirmed).put("alternatives",new JSONArray(alternatives)).put("tagSuggestions",new JSONArray(tagSuggestions));
    }
    public static ComposerState restore(JSONObject v) throws JSONException {
        ComposerState s=new ComposerState();s.title=v.optString("title");s.text=v.optString("text");s.workingPath=v.optString("workingPath");s.publicPath=v.optString("publicPath");s.sha=v.optString("sha");s.theme=v.isNull("theme")?null:v.optString("theme",null);s.tags=v.optString("tags");s.ocrStatus=v.optString("ocrStatus","not_analyzed");s.faceChecked=v.optBoolean("faceChecked");s.themeEdited=v.optBoolean("themeEdited");s.tagsEdited=v.optBoolean("tagsEdited");s.width=v.optInt("width");s.height=v.optInt("height");s.postId=v.optLong("postId");s.revision=v.optLong("revision");s.analysisMessage=v.optString("analysisMessage");
        List<MosaicDraft.Region> regions=new ArrayList<>();JSONArray a=v.optJSONArray("regions");if(a!=null)for(int i=0;i<a.length();i++){JSONObject r=a.getJSONObject(i);regions.add(new MosaicDraft.Region(r.getString("id"),(float)r.getDouble("l"),(float)r.getDouble("t"),(float)r.getDouble("r"),(float)r.getDouble("b"),r.getBoolean("active"),r.getBoolean("auto"),r.getInt("strength")));}s.mosaic.replace(regions);s.mosaic.checkpoint();
        a=v.optJSONArray("allLines");if(a!=null)for(int i=0;i<a.length();i++){JSONObject l=a.getJSONObject(i);float[] q=new float[8];for(int j=0;j<8;j++)q[j]=(float)l.getJSONArray("quad").getDouble(j);VisionEngine.Line line=new VisionEngine.Line(l.getString("id"),l.getString("text"),q);line.origin=l.optString("origin","auto");line.included=l.optBoolean("included",true);s.lines.add(line);}s.themeConfirmed=v.optBoolean("themeConfirmed");s.tagsConfirmed=v.optBoolean("tagsConfirmed");JSONArray alternatives=v.optJSONArray("alternatives");if(alternatives!=null)for(int i=0;i<alternatives.length();i++)s.alternatives.add(alternatives.getString(i));JSONArray suggestions=v.optJSONArray("tagSuggestions");if(suggestions!=null)for(int i=0;i<suggestions.length();i++)s.tagSuggestions.add(suggestions.getString(i));s.originalSha=v.optString("originalSha");s.needsReview=v.optBoolean("needsReview");a=v.optJSONArray("heldCorrections");if(a!=null)for(int i=0;i<a.length();i++)s.heldCorrections.add(a.getString(i));return s;
    }
}
