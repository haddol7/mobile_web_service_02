package com.haddol7.photoviewer;

import android.app.*;
import android.content.Intent;
import android.graphics.*;
import android.net.Uri;
import android.os.*;
import android.text.*;
import android.view.*;
import android.view.inputmethod.EditorInfo;
import android.widget.*;
import com.haddol7.photoviewer.content.*;
import com.haddol7.photoviewer.data.*;
import com.haddol7.photoviewer.model.*;
import com.haddol7.photoviewer.ui.UiKit;
import com.haddol7.photoviewer.ui.ChipFlow;
import com.haddol7.photoviewer.ui.HistoryPresentation;
import com.haddol7.photoviewer.ui.MonitoringTime;
import org.json.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

/** Observation records, person review and grounded questions share one operator workspace. */
public final class MainActivity extends Activity {
    public static final String DEFAULT_SERVER="https://daejinha.pythonanywhere.com/";
    private static final int PICK=801;
    private final ExecutorService network=Executors.newSingleThreadExecutor(),cpu=Executors.newSingleThreadExecutor(),pictures=Executors.newFixedThreadPool(2);
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final GenerationGate forms=new GenerationGate(),searches=new GenerationGate(),previews=new GenerationGate(),images=new GenerationGate();
    private final VisionEngine vision=new VisionEngine();
    private PhotoRepository api;
    private SessionInfo session;
    private ComposerState form;
    private Bitmap working,publicImage;
    private LinearLayout root,body,cards,regionControls,heading,tabs,workspace;
    private int reviewTab,selectedLine;
    private PhotoCanvas reviewPhoto;
    private final List<View> keyboardExtras=new ArrayList<>();
    private final Map<String,Button> mosaicModes=new LinkedHashMap<>();
    private ScrollView scroll;
    private Button publishTab,recordsTab,peopleTab,questionsTab,authSubmit;
    private TextView authError;
    private final Map<String,JSONArray> historyScenes=new HashMap<>();


    private JSONArray historyProfiles=new JSONArray();
    private String historyProfile="",historyStart="",historyEnd="";
    private boolean historyCandidates;
    private int historyPage=1;
    private LinearLayout historyCards;
    private TextView status,summaryTheme,summaryTags,summaryAnalysis;
    private PhotoCanvas mosaicCanvas;
    private String page="home",origin,query="",theme="",tag="",cursor;
    private boolean mine,networkBusy,analyzing,uncertain;
    private int scrollY;
    private final List<JSONObject> items=new ArrayList<>();
    private Runnable pendingSearch;
    private android.window.OnBackInvokedCallback back;
    private interface Job<T>{T run()throws Exception;}
    private interface Done<T>{void accept(T value)throws Exception;}
    private record Retained(PhotoRepository repository,SessionInfo session){}

    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);if(Build.VERSION.SDK_INT>=30)getWindow().setDecorFitsSystemWindows(false);
        origin=getSharedPreferences("MainActivity",MODE_PRIVATE).getString("origin",DEFAULT_SERVER);
        Retained retained=getLastNonConfigurationInstance() instanceof Retained?(Retained)getLastNonConfigurationInstance():null;
        api=retained==null?new PhotoRepository(origin):retained.repository;session=retained==null?null:retained.session;
        root=UiKit.column(this);root.setBackgroundColor(UiKit.PAPER);root.setPadding(dp(18),0,dp(18),0);
        root.setOnApplyWindowInsetsListener((v,insets)->{if(Build.VERSION.SDK_INT>=30){android.graphics.Insets s=insets.getInsets(WindowInsets.Type.systemBars());android.graphics.Insets ime=insets.getInsets(WindowInsets.Type.ime());v.setPadding(dp(18)+s.left,s.top,dp(18)+s.right,Math.max(s.bottom,ime.bottom));}else v.setPadding(dp(18)+insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),dp(18)+insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        setContentView(root);root.requestApplyInsets();
        heading=UiKit.row(this);heading.addView(UiKit.text(this,"감시 시스템",21,true),new LinearLayout.LayoutParams(0,-2,1));heading.addView(button("계정·설정",this::account));root.addView(heading);
        status=UiKit.text(this,"사진을 불러오고 있어요…",12,false);status.setTextColor(UiKit.MUTED);status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);status.setMaxLines(1);status.setEllipsize(android.text.TextUtils.TruncateAt.END);root.addView(status);
        tabs=UiKit.row(this);recordsTab=button("관측 기록",()->navigate(()->{historyProfile=historyStart=historyEnd="";historyCandidates=false;historyPage=1;showHome();}));peopleTab=button("인물 확인",()->navigate(this::showPeople));questionsTab=button("AI 질문",()->navigate(this::showQuestions));for(Button tab:new Button[]{recordsTab,peopleTab,questionsTab}){tab.setTextSize(12);tab.setPadding(dp(3),dp(5),dp(3),dp(5));UiKit.weighted(tabs,tab);}publishTab=button("사진 추가",()->navigate(this::newPost));updateNavigation();root.addView(tabs);
        scroll=new ScrollView(this);scroll.setFillViewport(true);body=UiKit.column(this);body.setPadding(0,dp(12),0,dp(24));scroll.addView(body);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        if(Build.VERSION.SDK_INT>=33){back=this::goBack;getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,back);}
        if(saved!=null){query=saved.getString("query","");theme=saved.getString("theme","");tag=saved.getString("tag","");mine=saved.getBoolean("mine");scrollY=saved.getInt("scrollY");String json=saved.getString("composer");if(json!=null)try{form=ComposerState.restore(new JSONObject(json));}catch(Exception error){message("작성 내용을 복원하지 못했습니다.");}}
        if(form!=null)restoreImages();else if(saved!=null&&"list".equals(saved.getString("page")))showList();else showHome();
    }
    @Override public Object onRetainNonConfigurationInstance(){return new Retained(api,session);}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("query",query);out.putString("theme",theme);out.putString("tag",tag);out.putBoolean("mine",mine);out.putInt("scrollY",scroll.getScrollY());if(form!=null)try{out.putString("composer",form.save().toString());}catch(JSONException ignored){message("작성 내용 복원 정보를 저장하지 못했습니다.");}}
    @Override protected void onDestroy(){forms.advance();searches.advance();previews.advance();images.advance();handler.removeCallbacksAndMessages(null);network.shutdown();cpu.execute(vision::close);cpu.shutdown();pictures.shutdown();if(Build.VERSION.SDK_INT>=33&&back!=null)getOnBackInvokedDispatcher().unregisterOnBackInvokedCallback(back);super.onDestroy();}
    // API33+ uses the registered OnBackInvokedCallback; this override serves API24–32 only.
    @android.annotation.SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){if(Build.VERSION.SDK_INT<33)goBack();else super.onBackPressed();}
    private int dp(float v){return UiKit.dp(this,v);}
    private Button button(String text,Runnable action){Button b=UiKit.button(this,text,v->action.run());if("‹".equals(text))b.setContentDescription("뒤로");if("⋯".equals(text))b.setContentDescription("편집 메뉴");return b;}
    private void message(String text){if(status!=null)status.setText(text==null?"처리하지 못했습니다.":text);}
    private boolean signedIn(){return session!=null&&session.isAuthenticated();}
    private void clear(String next){
        hideKeyboard();page=next;images.advance();keyboardExtras.clear();mosaicModes.clear();if(workspace!=null){root.removeView(workspace);workspace=null;}
        if(scroll.getParent()==null)root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        heading.setVisibility(View.VISIBLE);tabs.setVisibility(View.VISIBLE);UiKit.selected(recordsTab,"home".equals(next)||"history".equals(next));UiKit.selected(peopleTab,"people".equals(next)||"person".equals(next));UiKit.selected(questionsTab,"questions".equals(next));body.removeAllViews();mosaicCanvas=null;regionControls=null;reviewPhoto=null;scroll.scrollTo(0,0);
    }
    private LinearLayout editor(String next,String title,Runnable backAction){
        clear(next);root.removeView(scroll);heading.setVisibility(View.GONE);tabs.setVisibility(View.GONE);
        workspace=UiKit.column(this);workspace.setContentDescription("고정 편집 화면");root.addView(workspace,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout bar=UiKit.row(this);bar.addView(button("‹",backAction),new LinearLayout.LayoutParams(dp(48),dp(48)));bar.addView(UiKit.text(this,title,20,true),new LinearLayout.LayoutParams(0,-2,1));workspace.addView(bar);
        return bar;
    }
    private Button primary(String label,Runnable action){Button b=button(label,action);b.setTextColor(Color.WHITE);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(UiKit.GREEN));b.setContentDescription("고정 완료 버튼");return b;}
    private void hideKeyboard(){((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(root.getWindowToken(),0);root.clearFocus();}
    private void updateSummary(){if(form==null)return;summaryTheme.setText("분류 · "+ThemeMapper.name(form.theme));summaryTags.setText(form.tags.isEmpty()?"태그 없음":form.tags);summaryAnalysis.setText(form.analysisMessage);}

    private void watch(EditText field,Done<String> changed){field.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int c,int a){}public void onTextChanged(CharSequence s,int st,int before,int count){try{changed.accept(s.toString());}catch(Exception error){message(error.getMessage());}}public void afterTextChanged(Editable e){}});}
    private EditText input(String hint,String value,boolean multiline){EditText e=UiKit.input(this,hint,android.text.InputType.TYPE_CLASS_TEXT|(multiline?android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE:0));e.setContentDescription(hint);e.setText(value);if(multiline){e.setSingleLine(false);e.setMinLines(3);}return e;}
    private void navigate(Runnable next){if(networkBusy){message("저장이 끝난 뒤 이동해주세요.");return;}if(form!=null)new AlertDialog.Builder(this).setTitle("작성 중인 기록")
        .setMessage("작성 내용을 버리고 이동할까요?").setNegativeButton("계속 작성",null).setPositiveButton("이동",(d,w)->{forms.advance();form=null;working=publicImage=null;analyzing=false;uncertain=false;next.run();}).show();else next.run();}
    private void goBack(){if(networkBusy){message("저장이 끝난 뒤 이동해주세요.");return;}if("mosaic".equals(page)||"review".equals(page)){showComposer();return;}if("detail".equals(page)){showList();return;}if(form!=null){navigate(this::showList);return;}if(!"home".equals(page)&&!"history".equals(page)){showHome();return;}super.onBackPressed();}
    private <T> void request(String label,Job<T> job,Done<T> done){
        if(networkBusy)return;networkBusy=true;enableTree(body,false);if(workspace!=null)enableTree(workspace,false);message(label);PhotoRepository owner=api;
        network.execute(()->{try{T result=job.run();runOnUiThread(()->{if(isDestroyed()||owner!=api)return;networkBusy=false;enableTree(body,true);if(workspace!=null)enableTree(workspace,true);try{done.accept(result);}catch(Exception error){failure(error);}});}catch(Exception error){runOnUiThread(()->{if(isDestroyed()||owner!=api)return;networkBusy=false;enableTree(body,true);if(workspace!=null)enableTree(workspace,true);failure(error);});}});
    }
    private void enableTree(View view,boolean enabled){view.setEnabled(enabled);if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)enableTree(((ViewGroup)view).getChildAt(i),enabled);}
    private void failure(Exception error){
        if(authError!=null&&authError.isShown()){authError.setText(error instanceof HttpException?"아이디 또는 비밀번호를 확인해주세요.":"연결하지 못했습니다. 다시 시도해주세요.");if(authSubmit!=null)authSubmit.setEnabled(true);message(authError.getText().toString());return;}
        if("history".equals(page)&&historyCards!=null&&historyCards.getChildCount()==0){historyCards.addView(UiKit.text(this,"기록을 불러오지 못했습니다.",15,true));historyCards.addView(button("다시 시도",this::showHistory));}
        if("committed".equals(page)){message("기록은 저장되었습니다. 상세 조회만 실패했습니다. 다시 게시하지 말고 목록을 확인해주세요.");return;}
        if(uncertain&&form!=null){message("서버 응답을 받지 못해 게시 여부 확인이 필요합니다. 내 글에서 확인해주세요.");return;}
        if(error instanceof HttpException&&((HttpException)error).status==409&&form!=null){
            message("서버 내용이 바뀌었습니다. 내 입력은 유지했습니다.");
            new AlertDialog.Builder(this).setTitle("다른 수정 내용이 있어요").setMessage("내 입력을 유지하거나 서버의 최신 내용을 불러올 수 있습니다. 최신 내용을 불러오면 현재 편집 내용은 교체됩니다.")
                .setNegativeButton("내 입력 유지",null).setPositiveButton("최신 내용 불러오기",(d,w)->reloadEditing()).show();
        }else message(error.getMessage());
    }
    private void account(){
        String[] actions=signedIn()&&session.canPublish?new String[]{"로그아웃","서버 연결 설정","사진 추가","사진 보관함"}:signedIn()?new String[]{"로그아웃","서버 연결 설정"}:new String[]{"운영자 로그인","서버 연결 설정"};
        new AlertDialog.Builder(this).setTitle("계정·설정").setItems(actions,(d,i)->{
            if(i==3)navigate(()->{mine=false;showList();});else if(i==2)navigate(this::newPost);else if(i==1)serverSettings();else if(signedIn())navigate(()->request("로그아웃 중…",()->api.logout(),value->{session=value;mine=false;showHome();}));else auth(false);
        }).show();
    }
    private void auth(boolean ignored){
        LinearLayout fields=UiKit.column(this);fields.setPadding(dp(20),0,dp(20),0);
        EditText user=input("사용자 이름","",false),password=input("비밀번호","",false);
        password.setInputType(129);user.setImeOptions(EditorInfo.IME_ACTION_NEXT);password.setImeOptions(EditorInfo.IME_ACTION_DONE);
        fields.addView(UiKit.text(this,"아이디",12,true));fields.addView(user);fields.addView(UiKit.text(this,"비밀번호",12,true));fields.addView(password);
        authError=UiKit.text(this,"",12,false);authError.setTextColor(Color.rgb(164,52,49));authError.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);fields.addView(authError);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("운영자 로그인").setView(dialogContent(fields)).setNegativeButton("취소",null).setPositiveButton("로그인",null).create();
        dialog.setOnShowListener(d->{authSubmit=dialog.getButton(-1);authSubmit.setOnClickListener(v->{if(user.getText().toString().trim().isEmpty()||password.getText().length()==0){authError.setText("아이디와 비밀번호를 입력해주세요.");return;}authSubmit.setEnabled(false);request("인증 중…",()->api.login(user.getText().toString().trim(),password.getText().toString()),value->{session=value;password.setText("");hideKeyboard();dialog.dismiss();message(value.canPublish?"운영자로 로그인되었습니다.":"열람 계정입니다. 운영자만 게시할 수 있습니다.");if(form==null)showHome();});});password.setOnEditorActionListener((v,action,event)->{if(action==EditorInfo.IME_ACTION_DONE){authSubmit.performClick();return true;}return false;});});
        dialog.setOnDismissListener(d->{authError=null;authSubmit=null;});dialog.show();
    }
    private void serverSettings(){
        EditText url=input("서버 URL",origin,false);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("서버 연결 설정").setMessage("로컬 또는 배포한 PythonAnywhere 주소를 입력하세요.").setView(url).setNegativeButton("취소",null).setPositiveButton("연결·동기화",null).create();
        dialog.setOnShowListener(d->dialog.getButton(-1).setOnClickListener(v->navigate(()->{try{PhotoRepository next=new PhotoRepository(url.getText().toString());api=next;origin=next.getBaseUrl();session=null;getSharedPreferences("MainActivity",MODE_PRIVATE).edit().putString("origin",origin).apply();dialog.dismiss();mine=false;items.clear();showList();}catch(Exception error){message(error.getMessage());}})));dialog.show();
    }
    private void updateNavigation(){
        boolean owner=signedIn()&&session.canPublish;peopleTab.setVisibility(owner?View.VISIBLE:View.GONE);questionsTab.setVisibility(owner?View.VISIBLE:View.GONE);
    }
    private String monitorTime(String value){return MonitoringTime.format(value);}
    private void showHome(){
        clear("home");
        request("관측 정보를 불러오고 있습니다.",()->api.me(),data->{
            if(!"home".equals(page))return;session=data;updateNavigation();
            if(session.canPublish){showHistory();return;}
            LinearLayout entry=UiKit.card(this);entry.addView(UiKit.text(this,"감지부터 이력 조회까지",21,true));entry.addView(UiKit.text(this,"YOLO가 전송한 장면을 확인하고 인물별 출현 기록을 조회합니다.",13,false));entry.addView(primary("운영자 로그인",()->auth(false)));entry.addView(UiKit.text(this,"관측 기록 / 인물 확인 / AI 질문",11,false));body.addView(entry);message("동기화 완료 / 운영자 로그인");
        });
    }
    private LinearLayout portrait(String url,String label,long ticket,int height){
        LinearLayout box=UiKit.column(this);ImageView image=new ImageView(this);image.setScaleType(ImageView.ScaleType.CENTER_CROP);image.setContentDescription(label);box.addView(image,new LinearLayout.LayoutParams(-1,dp(height)));if(url!=null&&!url.isEmpty()&&!"null".equals(url))loadImage(image,url,ticket);box.addView(UiKit.text(this,label,10,false));return box;
    }
    private String historyPosition(JSONObject frame){
        if("live".equals(frame.optString("source_kind")))return "실시간 카메라";
        if(frame.isNull("video_seconds"))return "저장 영상";
        return "영상 "+String.format(Locale.KOREA,"%.1f",frame.optDouble("video_seconds"))+"초";
    }
    private void showPeople(){
        if(!signedIn()||!session.canPublish){auth(false);return;}clear("people");body.addView(UiKit.text(this,"인물 확인",23,true));body.addView(UiKit.text(this,"얼굴을 선택해 서로 다른 영상의 발견 이력을 봅니다.",12,false));
        request("얼굴과 발견 이력을 불러오고 있습니다.",()->api.historyOverview(),data->{if(!"people".equals(page))return;historyProfiles=data.getJSONArray("profiles");long ticket=images.current();LinearLayout row=null;int visible=0;
            for(int i=0;i<historyProfiles.length();i++){JSONObject p=historyProfiles.getJSONObject(i);if(!p.optBoolean("active")&&!p.optBoolean("reference_available"))continue;if(visible++%2==0){row=UiKit.row(this);row.setGravity(Gravity.TOP);body.addView(row);}String key=p.getString("key");LinearLayout card=UiKit.card(this);card.setPadding(dp(9),dp(9),dp(9),dp(9));card.addView(portrait(p.optString("portrait_url"),p.optBoolean("reference_available")?"등록 얼굴":"관측 사진",ticket,125));card.addView(UiKit.text(this,p.getString("name"),18,true));card.addView(UiKit.text(this,"영상 "+p.getInt("source_count")+"개에서 발견",12,true));card.addView(UiKit.text(this,"확인 "+p.getInt("confirmed_tracks")+" / 후보 "+p.getInt("candidate_tracks"),11,false));card.addView(UiKit.text(this,"최근 분석 "+p.optString("last_analysis_label"),10,false));card.addView(button("발견 이력 보기",()->showPerson(key)));card.setOnClickListener(v->showPerson(key));UiKit.weighted(row,card);}
            if(visible==0)body.addView(UiKit.text(this,"아직 인물과 연결된 관측 장면이 없습니다.",14,false));body.addView(UiKit.text(this,"얼굴 후보는 확인 전까지 같은 인물로 확정하지 않습니다.",11,false));message("인물별 얼굴과 영상 이력");});
    }
    private void showPerson(String key){showPerson(key,false);}
    private void showPerson(String key,boolean reviewOpen){
        if(!signedIn()||!session.canPublish){auth(false);return;}clear("person");historyProfile=key;historyCandidates=true;body.addView(button("인물 목록",this::showPeople));
        request("인물의 발견 이력을 불러오고 있습니다.",()->api.historyPerson(key),data->{if(!"person".equals(page))return;long ticket=images.current();
            LinearLayout intro=UiKit.row(this);intro.addView(portrait(data.optString("portrait_url"),data.optBoolean("reference_available")?"등록 얼굴":"관측 사진",ticket,72),new LinearLayout.LayoutParams(dp(78),-2));LinearLayout copy=UiKit.column(this);copy.addView(UiKit.text(this,data.getString("name"),24,true));copy.addView(UiKit.text(this,data.getString("status"),12,true));copy.addView(UiKit.text(this,data.optString("source_summary","영상 "+data.getInt("source_count")+"개")+" / 확인 "+data.getInt("confirmed_tracks")+" / 후보 "+data.getInt("candidate_tracks"),11,false));copy.addView(UiKit.text(this,"최근 분석 "+data.optString("last_analysis_label"),11,false));intro.addView(copy,new LinearLayout.LayoutParams(0,-2,1));body.addView(intro);
            LinearLayout actions=UiKit.row(this);UiKit.weighted(actions,button("이 인물 기록에 질문",this::showQuestions));UiKit.weighted(actions,button("모든 발견 장면",()->{historyPage=1;showHistory();}));body.addView(actions);
            body.addView(UiKit.text(this,data.optString("source_notice","분석일 기준"),11,false));
            JSONArray pending=data.getJSONArray("pending");LinearLayout pendingBox=UiKit.column(this);pendingBox.setVisibility(reviewOpen?View.VISIBLE:View.GONE);body.addView(button("같은 인물인지 확인 ("+pending.length()+")",()->pendingBox.setVisibility(pendingBox.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE)));body.addView(pendingBox);
            if(pending.length()==0)pendingBox.addView(UiKit.text(this,"검토할 얼굴 후보가 없습니다.",12,false));
            for(int i=0;i<pending.length();i++){JSONObject track=pending.getJSONObject(i);LinearLayout card=UiKit.card(this),pair=UiKit.row(this);UiKit.weighted(pair,portrait(data.optString("reference_url"),"등록 얼굴",ticket,105));UiKit.weighted(pair,portrait(track.getString("image_url"),"이번 발견",ticket,105));card.addView(pair);card.addView(UiKit.text(this,track.getString("source"),13,true));card.addView(UiKit.text(this,"얼굴 후보 / 유사도 "+String.format(Locale.KOREA,"%.2f",track.getDouble("similarity")),11,false));LinearLayout decisions=UiKit.row(this);UiKit.weighted(decisions,button("같은 인물로 확인",()->request("확인 내용을 저장합니다.",()->api.reviewTrack(track.getLong("id"),track.getLong("revision"),key),review->showPerson(key,true))));UiKit.weighted(decisions,button("인물 미확인",()->request("확인 내용을 저장합니다.",()->api.reviewTrack(track.getLong("id"),track.getLong("revision"),null),review->showPerson(key,true))));card.addView(decisions);pendingBox.addView(card);}
            body.addView(UiKit.text(this,"영상별 발견 이력",18,true));JSONArray timeline=data.getJSONArray("timeline");String timelineDay="";
            for(int i=0;i<timeline.length();i++){JSONObject frame=timeline.getJSONObject(i);String day=frame.optString("date_key");if(!day.equals(timelineDay)){timelineDay=day;body.addView(UiKit.text(this,frame.optString("date_label")+" / 분석일",17,true));}JSONArray members=frame.getJSONArray("frames");for(int at=0;at<members.length();at++)historyScenes.put(members.getJSONObject(at).getString("id"),members);LinearLayout card=UiKit.card(this),line=UiKit.row(this);line.addView(portrait(frame.optString("image_url"),"발견 장면",ticket,78),new LinearLayout.LayoutParams(dp(86),-2));LinearLayout text=UiKit.column(this);text.addView(UiKit.text(this,frame.getString("source"),14,true));text.addView(UiKit.text(this,"분석 "+frame.optString("analysis_label")+" / "+historyPosition(frame),11,false));JSONArray tracks=frame.getJSONArray("tracks");String state="얼굴 후보";for(int at=0;at<tracks.length();at++)if(!tracks.getJSONObject(at).isNull("confirmed"))state="dataset".equals(tracks.getJSONObject(at).optString("review_basis"))?"시연 정답 확인":"확인됨";text.addView(UiKit.text(this,state,11,true));line.addView(text,new LinearLayout.LayoutParams(0,-2,1));card.addView(line);card.addView(button("장면 확인",()->historyDetail(frame)));body.addView(card);}message("등록 얼굴과 영상별 발견 이력");});
    }    private void showQuestions(){
        if(!signedIn()||!session.canPublish){auth(false);return;}
        String contextProfile="person".equals(page)?historyProfile:"";
        clear("questions");root.removeView(scroll);workspace=UiKit.column(this);root.addView(workspace,new LinearLayout.LayoutParams(-1,0,1));
        workspace.addView(new com.haddol7.photoviewer.ui.ChatWorkspace(this,api,session.username,origin,contextProfile,this::message),new LinearLayout.LayoutParams(-1,0,1));
        message("질문과 답변을 대화로 저장합니다.");
    }
    private void showList(){
        clear("list");if(form!=null)body.addView(button("작성 중인 기록로 돌아가기",this::showComposer));
        body.addView(UiKit.text(this,mine?"내가 추가한 사진":"사진 보관함",23,true));
        LinearLayout searchRow=UiKit.row(this);EditText search=input("사진 속 문구 검색",query,false);search.setImeOptions(EditorInfo.IME_ACTION_SEARCH);searchRow.addView(search,new LinearLayout.LayoutParams(0,dp(48),1));searchRow.addView(button("검색",()->{hideKeyboard();loadList(false);}));body.addView(searchRow);
        LinearLayout filters=UiKit.column(this);filters.setVisibility(View.GONE);
        LinearLayout filterBar=UiKit.row(this);Button toggle=button("테마·태그 필터",()->{boolean open=filters.getVisibility()!=View.VISIBLE;filters.setVisibility(open?View.VISIBLE:View.GONE);});filterBar.addView(toggle,new LinearLayout.LayoutParams(0,-2,1));filterBar.addView(button("새로고침",()->loadList(false)));body.addView(filterBar);
        Spinner filter=new Spinner(this);String[] labels=new String[ThemeMapper.NAMES.length+2];labels[0]="전체 테마";System.arraycopy(ThemeMapper.NAMES,0,labels,1,7);labels[8]="미분류";
        filter.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));int initial=0;for(int i=0;i<7;i++)if(ThemeMapper.IDS[i].equals(theme))initial=i+1;if("unclassified".equals(theme))initial=8;filter.setSelection(initial);filter.setContentDescription("테마 필터");filters.addView(filter);
        EditText tagField=input("태그로 찾기",tag,false);filters.addView(tagField);filters.addView(button("필터 적용",()->{tag=tagField.getText().toString().trim();hideKeyboard();loadList(false);}));filters.addView(button("조건 해제",()->{theme=tag="";showList();}));body.addView(filters);
        if(!theme.isEmpty()||!tag.isEmpty())body.addView(UiKit.text(this,ThemeMapper.name(theme)+(tag.isEmpty()?"":" · #"+tag),12,false));
        filter.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int position,long id){String next=position==0?"":position==8?"unclassified":ThemeMapper.IDS[position-1];if(!next.equals(theme)){theme=next;loadList(false);}}});
        watch(search,value->{query=value;if(pendingSearch!=null)handler.removeCallbacks(pendingSearch);searches.advance();pendingSearch=()->loadList(false);handler.postDelayed(pendingSearch,350);});
        search.setOnEditorActionListener((v,action,event)->{if(action==EditorInfo.IME_ACTION_SEARCH){if(pendingSearch!=null)handler.removeCallbacks(pendingSearch);hideKeyboard();loadList(false);return true;}return false;});
        cards=UiKit.column(this);body.addView(cards);loadList(false);
    }
    private void loadList(boolean more){
        if(!"list".equals(page))return;
        String q=query.trim();if(!q.isEmpty()&&q.codePointCount(0,q.length())<2){cards.removeAllViews();cards.addView(UiKit.text(this,"검색어를 두 글자 이상 입력해주세요.",16,false));return;}
        long ticket=searches.advance();PhotoRepository owner=api;String selectedTheme=theme,selectedTag=tag,next=more?cursor:null;boolean own=mine;
        message("사진을 찾고 있어요…");if(!more)items.clear();
        network.execute(()->{try{
            SessionInfo me=owner.me();List<JSONObject> found=new ArrayList<>();String after=null;
            if(q.isEmpty()&&selectedTheme.isEmpty()&&selectedTag.isEmpty()&&!own){
                List<PhotoPost> posts=owner.getPosts();
                Map<Long,JSONObject> summaries=new HashMap<>();
                int start=more&&next!=null&&next.startsWith("local:")?Integer.parseInt(next.substring(6)):0;
                int end=Math.min(start+20,posts.size());List<Long> ids=new ArrayList<>();for(int i=start;i<end;i++)ids.add(posts.get(i).id);
                if(!ids.isEmpty()){JSONArray a=owner.summaries(ids).getJSONArray("results");for(int i=0;i<a.length();i++)summaries.put(a.getJSONObject(i).getLong("post_id"),a.getJSONObject(i));}
                for(int i=start;i<end;i++){PhotoPost post=posts.get(i);found.add(new JSONObject().put("post",postJson(post)).put("content",summaries.get(post.id)));}
                if(end<posts.size())after="local:"+end;
            }else{JSONObject result=owner.browse(q,selectedTheme,selectedTag,own,next);JSONArray values=result.getJSONArray("results");for(int i=0;i<values.length();i++)found.add(values.getJSONObject(i));after=result.isNull("next_cursor")?null:result.optString("next_cursor",null);}
            String nextPage=after;runOnUiThread(()->{if(isDestroyed()||owner!=api||!searches.accepts(ticket)||!"list".equals(page))return;session=me;updateNavigation();items.addAll(found);cursor=nextPage;renderCards();message("동기화 완료 · 사진 "+items.size()+"개"+(q.isEmpty()?"":" · 사진 속 글자 검색"));});
        }catch(Exception error){runOnUiThread(()->{if(isDestroyed()||owner!=api||!searches.accepts(ticket)||!"list".equals(page))return;cards.removeAllViews();cards.addView(UiKit.text(this,"사진을 불러오지 못했어요. 연결 상태를 확인하고 다시 시도해주세요.",16,false));cards.addView(button("다시 시도",()->loadList(false)));message(error.getMessage());});}});
    }
    private JSONObject postJson(PhotoPost p)throws JSONException{return new JSONObject().put("id",p.id).put("author",p.authorId).put("title",p.title).put("text",p.text).put("image",p.imageUrl).put("created_date",p.created).put("published_date",p.published);}
    private void renderCards(){
        cards.removeAllViews();long generation=images.advance();if(items.isEmpty()){cards.addView(UiKit.text(this,query.trim().isEmpty()?"아직 사진이 없어요. 첫 기록을 남겨보세요.":"일치하는 사진이 없어요. 문구나 필터를 바꿔보세요.",16,false));return;}
        LinearLayout row=null;int index=0;
        for(JSONObject item:items)try{
            if(index++%2==0){row=UiKit.row(this);row.setGravity(Gravity.TOP);cards.addView(row);}
            PhotoPost post=JsonCodec.post(item.getJSONObject("post"));JSONObject metadata=item.optJSONObject("content");LinearLayout card=UiKit.card(this);card.setPadding(dp(8),dp(6),dp(8),dp(6));
            ImageView photo=new ImageView(this);photo.setScaleType(ImageView.ScaleType.CENTER_CROP);photo.setContentDescription(post.title);card.addView(photo,new LinearLayout.LayoutParams(-1,dp(104)));loadImage(photo,post.imageUrl,generation);
            TextView title=UiKit.text(this,post.title,14,true);title.setMaxLines(2);title.setMinLines(2);title.setEllipsize(android.text.TextUtils.TruncateAt.END);card.addView(title);
            card.addView(UiKit.text(this,metadata==null?"미분류":ThemeMapper.name(metadata.isNull("theme")?null:metadata.optString("theme")),12,false));
            JSONArray matched=item.optJSONArray("matched_lines");if(matched!=null&&matched.length()>0){TextView snippet=UiKit.text(this,"사진 속 글자: "+matched.getJSONObject(0).getString("text"),12,false);snippet.setMaxLines(1);snippet.setEllipsize(android.text.TextUtils.TruncateAt.END);card.addView(snippet);}
            if(metadata!=null){JSONArray tags=metadata.optJSONArray("tags");if(tags!=null&&tags.length()>0){String value=tags.getJSONObject(0).getString("display");TextView chip=UiKit.text(this,"#"+value,12,false);chip.setMaxLines(1);chip.setOnClickListener(v->{tag=value;showList();});card.addView(chip);}}
            Runnable open=()->{scrollY=scroll.getScrollY();hideKeyboard();openDetail(post,item);};photo.setOnClickListener(v->open.run());title.setOnClickListener(v->open.run());card.addView(button("기록 열기",open));
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(3),dp(3),dp(3),dp(6));row.addView(card,params);
        }catch(JSONException error){message("사진 응답 형식을 확인해주세요.");}
        if(index%2==1&&row!=null)row.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));
        if(cursor!=null)cards.addView(button("더 보기",()->loadList(true)));
        if(scrollY>0){int restore=scrollY;scroll.post(()->scroll.scrollTo(0,restore));scrollY=0;}
    }
    private void loadImage(ImageView target,String url,long ticket){PhotoRepository owner=api;pictures.execute(()->{if(isDestroyed()||owner!=api||!images.accepts(ticket))return;try{byte[] bytes=owner.downloadPhoto(url);BitmapFactory.Options bounds=new BitmapFactory.Options();bounds.inJustDecodeBounds=true;BitmapFactory.decodeByteArray(bytes,0,bytes.length,bounds);BitmapFactory.Options options=new BitmapFactory.Options();options.inSampleSize=Math.max(1,Math.max(bounds.outWidth,bounds.outHeight)/600);Bitmap bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.length,options);runOnUiThread(()->{if(!isDestroyed()&&images.accepts(ticket)&&owner==api)target.setImageBitmap(bitmap);});}catch(Exception error){runOnUiThread(()->{if(images.accepts(ticket))target.setContentDescription("사진을 불러오지 못했습니다. "+error.getMessage());});}});}
    private record HistoryData(JSONObject frames,JSONObject overview){}
    private void showHistory(){
        if(!signedIn()||!session.canPublish){auth(false);return;}
        clear("history");
        LinearLayout bar=UiKit.row(this);bar.addView(UiKit.text(this,"관측 기록",21,true),new LinearLayout.LayoutParams(0,-2,1));
        bar.addView(button("조회 조건",this::historyFilters));body.addView(bar);
        LinearLayout summary=UiKit.row(this);body.addView(summary);
        TextView condition=UiKit.text(this,historyProfile.isEmpty()?"전체 기록":historyName(historyProfile),12,false);condition.setMaxLines(1);condition.setEllipsize(TextUtils.TruncateAt.END);body.addView(condition);
        if(!historyStart.isEmpty()||!historyEnd.isEmpty()||historyCandidates)body.addView(UiKit.text(this,(historyStart.isEmpty()?"처음":historyStart)+" / "+(historyEnd.isEmpty()?"마지막":historyEnd)+(historyCandidates?" / 후보 포함":""),11,false));
        historyCards=UiKit.column(this);body.addView(historyCards);
        request("관측 기록을 불러오고 있습니다.",()->new HistoryData(api.historySessions(historyProfile,historyStart,historyEnd,historyCandidates,historyPage),
            api.historyOverview()),data->{
                if(!"history".equals(page))return;historyProfiles=data.overview.getJSONArray("profiles");
                JSONObject facts=data.overview.getJSONObject("facts");String[] labels={"분석한 영상","저장 사진","확인할 추적"},keys={"sessions","sampled_frames","pending_tracks"};
                for(int i=0;i<3;i++){LinearLayout metric=UiKit.card(this);metric.setPadding(dp(8),dp(6),dp(8),dp(6));metric.addView(UiKit.text(this,labels[i],10,false));metric.addView(UiKit.text(this,String.valueOf(facts.getInt(keys[i])),23,true));if(i==2)metric.setOnClickListener(v->showPeople());UiKit.weighted(summary,metric);}
                TextView received=UiKit.text(this,"전체 집계 / 마지막 분석 "+(data.overview.isNull("last_received_at")?"기록 없음":monitorTime(data.overview.getString("last_received_at"))),10,false);body.addView(received,body.indexOfChild(summary)+1);
                JSONArray rows=data.frames.getJSONArray("results");renderHistory(rows);renderHistoryDays(data.frames.optJSONArray("days"));message("동기화 완료 / 이 페이지 "+rows.length()+"개 장면 / 분석일 기준");
                LinearLayout pages=UiKit.row(this);
                if(historyPage>1)pages.addView(button("이전",()->{historyPage--;showHistory();}));
                pages.addView(UiKit.text(this,historyPage+"페이지",13,false));
                if(!data.frames.isNull("next_page"))pages.addView(button("다음",()->{historyPage++;showHistory();}));
                historyCards.addView(pages);
            });
    }
    private ScrollView dialogContent(LinearLayout box){
        box.setBackgroundColor(UiKit.WHITE);
        ScrollView result=new ScrollView(this){@Override protected void onMeasure(int width,int height){int limit=Math.max(dp(130),root.getHeight()-root.getPaddingTop()-root.getPaddingBottom()-dp(150));int given=View.MeasureSpec.getMode(height)==View.MeasureSpec.UNSPECIFIED?limit:View.MeasureSpec.getSize(height);super.onMeasure(width,View.MeasureSpec.makeMeasureSpec(Math.min(given,limit),View.MeasureSpec.AT_MOST));}};
        result.setBackgroundColor(UiKit.WHITE);if(Build.VERSION.SDK_INT>=26){result.setDefaultFocusHighlightEnabled(false);box.setDefaultFocusHighlightEnabled(false);}result.setFillViewport(false);result.addView(box);return result;
    }
    private void historyQuestion(){showQuestions();}
    private void historyAnswer(JSONObject result)throws JSONException{
        LinearLayout box=UiKit.column(this);box.setPadding(dp(18),dp(2),dp(18),dp(8));JSONObject facts=result.getJSONObject("facts"),llm=result.getJSONObject("llm");
        box.addView(UiKit.text(this,"선 통과 "+facts.getInt("passages")+"건 / 추적 "+facts.getInt("observed_tracks")+"개",15,true));
        boolean generated="generated".equals(llm.optString("status"));if(generated)box.addView(UiKit.text(this,"AI 설명",12,true));
        JSONObject retrieval=result.optJSONObject("retrieval");if(retrieval!=null&&"semantic".equals(retrieval.optString("strategy"))){String state=retrieval.optString("status");box.addView(UiKit.text(this,"ranked".equals(state)?"의미 검색으로 선택한 최대 5개 영상의 기록입니다.":"no_match".equals(state)?"질문과 유사한 영상 설명을 찾지 못했습니다.":"empty".equals(state)?"조회 조건에 맞는 기록이 없습니다.":"의미 검색을 사용할 수 없어 조건 조회 결과를 표시했습니다.",11,false));}
        box.addView(UiKit.text(this,generated?llm.getString("text"):HistoryPresentation.shortAnswer(result.getString("answer")),15,false));
        box.addView(UiKit.text(this,facts.getInt("sampled_frames")==0?"기록 없음이 실제 부재를 뜻하지는 않습니다.":"통과 건수는 사람 수나 방문 횟수와 다릅니다.",11,false));
        TextView complete=UiKit.text(this,result.getString("answer"),13,false);complete.setVisibility(View.GONE);
        box.addView(button("집계 자세히",()->complete.setVisibility(complete.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE)));box.addView(complete);
        JSONArray evidence=result.getJSONArray("evidence");List<HistoryPresentation.Scene> scenes=HistoryPresentation.scenes(evidence);
        box.addView(UiKit.text(this,"근거 사진 "+evidence.length()+"장",13,true));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("기록 기반 답변").setView(dialogContent(box)).setPositiveButton("근거 사진 확인",null).setNeutralButton("다른 질문",(d,w)->historyQuestion()).create();
        LinearLayout thumbs=UiKit.row(this);box.addView(thumbs);int shown=0;
        for(HistoryPresentation.Scene scene:scenes){if(shown++>=3)break;JSONObject row=scene.representative();for(int i=0;i<scene.frames().length();i++)historyScenes.put(scene.frames().getJSONObject(i).getString("id"),scene.frames());
            LinearLayout tile=UiKit.column(this);ImageView photo=new ImageView(this);photo.setScaleType(ImageView.ScaleType.CENTER_CROP);photo.setContentDescription("답변 근거 사진");tile.addView(photo,new LinearLayout.LayoutParams(-1,dp(68)));if(!row.isNull("image_url"))loadImage(photo,row.getString("image_url"),images.current());
            TextView caption=UiKit.text(this,historyTime(row),10,false);caption.setMaxLines(2);tile.addView(caption);tile.setOnClickListener(v->{dialog.dismiss();historyDetail(row);});UiKit.weighted(thumbs,tile);}
        if(scenes.size()>3){LinearLayout rest=UiKit.column(this);rest.setVisibility(View.GONE);for(int i=3;i<scenes.size();i++){JSONObject row=scenes.get(i).representative();rest.addView(button(historyTime(row),()->{dialog.dismiss();historyDetail(row);}));}box.addView(button("근거 사진 더 보기",()->rest.setVisibility(rest.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE)));box.addView(rest);}
        dialog.show();message("선 통과 "+facts.getInt("passages")+"건 / 추적 "+facts.getInt("observed_tracks")+"개");
    }
    private String historyName(String key){
        for(int i=0;i<historyProfiles.length();i++){JSONObject value=historyProfiles.optJSONObject(i);
            if(value!=null&&key.equals(value.optString("key")))return value.optString("name",key);}
        return key;
    }
    private String historyTime(JSONObject value){
        return "분석 "+monitorTime(value.optString("processed_at"))
            +(value.isNull("video_seconds")?"":" / 영상 "+String.format(Locale.KOREA,"%.1f",value.optDouble("video_seconds"))+"초")
            +(value.isNull("observed_at")?" / 촬영 날짜 미상":"");
    }
    private void renderHistoryDays(JSONArray days){
        if(days==null)return;HorizontalScrollView scroll=new HorizontalScrollView(this);scroll.setHorizontalScrollBarEnabled(false);LinearLayout strip=UiKit.row(this);scroll.addView(strip);
        strip.addView(button("전체 날짜",()->{historyStart=historyEnd="";historyPage=1;showHistory();}));
        for(int i=0;i<days.length();i++){JSONObject day=days.optJSONObject(i);if(day==null||day.isNull("date_key"))continue;String key=day.optString("date_key");strip.addView(button(key.substring(5).replace('-','/')+" ("+day.optInt("session_count")+")"+(key.equals(historyStart)&&key.equals(historyEnd)?" 선택됨":""),()->{historyStart=historyEnd=key;historyPage=1;showHistory();}));}
        historyCards.addView(scroll,0);
    }
    private void renderHistory(JSONArray values)throws JSONException{
        historyCards.removeAllViews();historyScenes.clear();LinearLayout row=null;long ticket=images.current();List<HistoryPresentation.Scene> scenes=HistoryPresentation.scenes(values);
        if(scenes.isEmpty()){historyCards.addView(UiKit.text(this,"조건에 맞는 기록이 없습니다.",16,true));historyCards.addView(UiKit.text(this,"분석일이나 인물 조건을 바꿔보세요.",13,false));return;}
        String lastDay="";int columns=0;
        for(int i=0;i<scenes.size();i++){
            HistoryPresentation.Scene scene=scenes.get(i);JSONObject value=scene.representative();for(int j=0;j<scene.frames().length();j++)historyScenes.put(scene.frames().getJSONObject(j).getString("id"),scene.frames());
            String day=value.optString("date_key","unknown");if(!day.equals(lastDay)){if(columns%2==1&&row!=null)row.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));columns=0;lastDay=day;historyCards.addView(UiKit.text(this,value.optString("date_label","촬영 날짜 미상")+" / 분석일",17,true));}
            if(columns++%2==0){row=UiKit.row(this);row.setGravity(Gravity.TOP);historyCards.addView(row);}
            LinearLayout card=UiKit.card(this);card.setPadding(dp(7),dp(7),dp(7),dp(9));
            LinearLayout.LayoutParams sizing=new LinearLayout.LayoutParams(0,-2,1);sizing.setMargins(dp(2),dp(2),dp(2),dp(2));row.addView(card,sizing);
            ImageView photo=new ImageView(this);photo.setScaleType(ImageView.ScaleType.CENTER_CROP);photo.setContentDescription("관측 사진");
            card.addView(photo,new LinearLayout.LayoutParams(-1,dp(108)));if(!value.isNull("image_url"))loadImage(photo,value.getString("image_url"),ticket);
            TextView title=UiKit.text(this,value.getString("source"),13,true);title.setMaxLines(1);title.setEllipsize(TextUtils.TruncateAt.END);card.addView(title);
            card.addView(UiKit.text(this,historyTime(value),11,false));
            JSONArray tracks=value.getJSONArray("tracks");String label="인물 미확인";
            for(int j=0;j<tracks.length();j++){JSONObject track=tracks.getJSONObject(j);
                if(!track.isNull("confirmed")){label="확인: "+historyName(track.getString("confirmed"));break;}
                if(!track.isNull("candidate")&&!track.optBoolean("reviewed"))label="얼굴 후보 확인 필요";}
            TextView identity=UiKit.text(this,label,12,false);identity.setMaxLines(1);card.addView(identity);
            card.addView(UiKit.text(this,"연속 사진 "+scene.frames().length()+"장",10,false));
            card.setOnClickListener(v->historyDetail(value));photo.setOnClickListener(v->historyDetail(value));
        }
        if(columns%2==1&&row!=null)row.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));
    }
    private void historyFilters(){
        LinearLayout box=UiKit.column(this);box.setPadding(dp(18),0,dp(18),0);
        EditText start=input("시작일 YYYY-MM-DD",historyStart,false),end=input("종료일 YYYY-MM-DD",historyEnd,false);
        Spinner profiles=new Spinner(this);List<String> names=new ArrayList<>();names.add("전체 추적 기록");int selected=0;
        for(int i=0;i<historyProfiles.length();i++){JSONObject value=historyProfiles.optJSONObject(i);names.add(value.optString("name"));if(historyProfile.equals(value.optString("key")))selected=i+1;}
        profiles.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));profiles.setSelection(selected);
        CheckBox candidates=new CheckBox(this);candidates.setText("미확인 얼굴 후보 포함");candidates.setChecked(historyCandidates);
        box.addView(UiKit.text(this,"인물 프로필",12,true));box.addView(profiles);box.addView(UiKit.text(this,"분석 날짜",12,true));box.addView(start);box.addView(end);box.addView(candidates);
        box.addView(UiKit.text(this,"날짜 필터는 영상을 분석한 날짜를 기준으로 조회합니다.",11,false));
        new AlertDialog.Builder(this).setTitle("조회 조건").setView(dialogContent(box)).setNegativeButton("취소",null).setNeutralButton("조건 해제",(d,w)->{historyProfile=historyStart=historyEnd="";historyCandidates=false;historyPage=1;if("questions".equals(page))showQuestions();else showHistory();}).setPositiveButton("조회",(d,w)->{
            historyProfile=profiles.getSelectedItemPosition()==0?"":historyProfiles.optJSONObject(profiles.getSelectedItemPosition()-1).optString("key");
            historyStart=start.getText().toString().trim();historyEnd=end.getText().toString().trim();historyCandidates=candidates.isChecked();historyPage=1;if("questions".equals(page))showQuestions();else showHistory();
        }).show();
    }
    private void historyDetail(JSONObject value){
        try{
            LinearLayout box=UiKit.column(this);box.setPadding(dp(16),0,dp(16),0);
            JSONArray frames=historyScenes.getOrDefault(value.getString("id"),new JSONArray().put(value));int position=0;for(int i=0;i<frames.length();i++)if(frames.getJSONObject(i).getString("id").equals(value.getString("id")))position=i;
            ImageView image=new ImageView(this);image.setScaleType(ImageView.ScaleType.FIT_CENTER);box.addView(image,new LinearLayout.LayoutParams(-1,Math.max(dp(100),Math.min(dp(170),root.getHeight()/4))));
            if(!value.isNull("image_url"))loadImage(image,value.getString("image_url"),images.current());
            box.addView(UiKit.text(this,historyTime(value),12,false));
            JSONArray tracks=value.getJSONArray("tracks");Spinner selected=new Spinner(this),profiles=new Spinner(this);List<String> ids=new ArrayList<>(),names=new ArrayList<>();
            for(int i=0;i<tracks.length();i++)ids.add("추적 "+tracks.getJSONObject(i).getInt("track_id"));
            names.add("인물 미확인");for(int i=0;i<historyProfiles.length();i++)names.add(historyProfiles.getJSONObject(i).getString("name"));
            selected.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,ids));profiles.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));
            TextView candidate=UiKit.text(this,"",12,false);box.addView(UiKit.text(this,"확인할 추적 번호",11,true));box.addView(selected);box.addView(candidate);box.addView(UiKit.text(this,"운영자가 확인할 인물",11,true));box.addView(profiles);
            selected.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){
                public void onNothingSelected(AdapterView<?> parent){}
                public void onItemSelected(AdapterView<?> parent,View v,int position,long id){
                    JSONObject track=tracks.optJSONObject(position);String key=track.optString("confirmed","");int profile=0;
                    for(int i=0;i<historyProfiles.length();i++)if(key.equals(historyProfiles.optJSONObject(i).optString("key")))profile=i+1;
                    profiles.setSelection(profile);candidate.setText(track.isNull("candidate")?"얼굴 후보 없음":"얼굴 후보: "+historyName(track.optString("candidate")));
                }});
            AlertDialog dialog=new AlertDialog.Builder(this).setTitle("기록 확인").setView(dialogContent(box)).setNegativeButton("닫기",null)
                .setPositiveButton("확인 저장",null).create();
            if(frames.length()>1){final int selectedFrame=position;LinearLayout navigation=UiKit.row(this);
                Button previous=button("이전 사진",()->{dialog.dismiss();historyDetail(frames.optJSONObject(selectedFrame-1));});previous.setEnabled(position>0);UiKit.weighted(navigation,previous);
                navigation.addView(UiKit.text(this,(position+1)+" / "+frames.length(),11,false));Button next=button("다음 사진",()->{dialog.dismiss();historyDetail(frames.optJSONObject(selectedFrame+1));});next.setEnabled(position+1<frames.length());UiKit.weighted(navigation,next);box.addView(navigation,0);}
            dialog.setOnShowListener(d->dialog.getButton(-1).setOnClickListener(v->{
                if(tracks.length()==0)return;JSONObject track=tracks.optJSONObject(selected.getSelectedItemPosition());
                String profile=profiles.getSelectedItemPosition()==0?null:historyProfiles.optJSONObject(profiles.getSelectedItemPosition()-1).optString("key");
                request("확인 내용을 저장하고 있습니다.",()->api.reviewTrack(track.optLong("id"),track.optLong("revision"),profile),
                    result->{dialog.dismiss();showHistory();});
            }));dialog.show();dialog.getButton(-1).setEnabled(tracks.length()>0);
        }catch(JSONException error){message("기록 형식을 확인해주세요.");}
    }
    private record Detail(PhotoPost post,JSONObject content,byte[] bytes){}
    private void openDetail(PhotoPost post,JSONObject searchItem){request("기록을 불러오고 있어요…",()->{JSONObject content=api.content(post.id);byte[] bytes=api.downloadPhoto(post.imageUrl);if(!content.isNull("image_sha256")&&!content.getString("image_sha256").equals(PhotoPipeline.sha256(bytes)))throw new IOException("사진이 변경되었습니다. 목록을 새로고침해주세요.");return new Detail(post,content,bytes);},detail->showDetail(detail,searchItem));}
    private void showDetail(Detail detail,JSONObject searchItem)throws Exception{
        clear("detail");PhotoPost post=detail.post;LinearLayout bar=UiKit.row(this);bar.addView(button("목록",this::showList),new LinearLayout.LayoutParams(0,-2,1));
        if(signedIn()&&session.canPublish&&(session.canManageAll||session.userId==post.authorId))bar.addView(button("관리",()->new AlertDialog.Builder(this).setTitle("사진 관리").setItems(new String[]{"기록 수정","기록 삭제"},(dialog,which)->{if(which==0)loadEditing(detail);else new AlertDialog.Builder(this).setTitle("기록 삭제").setMessage("사진과 분류 및 검색 문구를 삭제할까요?").setNegativeButton("취소",null).setPositiveButton("삭제",(d,w)->request("삭제 중…",()->{api.deletePhoto(post.id);return true;},value->showList())).show();}).show()));
        body.addView(bar);body.addView(UiKit.text(this,post.title,21,true));
        PhotoCanvas photo=new PhotoCanvas(this);Bitmap b=BitmapFactory.decodeByteArray(detail.bytes,0,detail.bytes.length);photo.bitmap(b);body.addView(photo,new LinearLayout.LayoutParams(-1,Math.min(dp(280),Math.max(dp(150),root.getHeight()/3))));body.addView(button("전체 사진 보기",photo::resetZoom));
        body.addView(UiKit.text(this,post.text,15,false));body.addView(UiKit.text(this,ThemeMapper.name(detail.content.isNull("theme")?null:detail.content.optString("theme")),13,true));
        JSONArray matched=searchItem==null?null:searchItem.optJSONArray("matched_lines");boolean same=searchItem==null||searchItem.optLong("content_revision",detail.content.optLong("revision"))==detail.content.optLong("revision");
        if(matched!=null&&!same)body.addView(UiKit.text(this,"사진 내용이 변경되어 이전 검색 표시를 지웠어요. 다시 검색해주세요.",14,false));
        if(matched!=null&&same)for(int i=0;i<matched.length();i++){JSONObject line=matched.getJSONObject(i);float[] quad=quad(line.getJSONArray("quad"));body.addView(button("일치 위치: "+line.getString("text"),()->{photo.highlights(List.of(quad));photo.focus(quad);}));if(i==0){photo.highlights(List.of(quad));photo.post(()->photo.focus(quad));}}
        if(matched!=null&&same&&searchItem.optInt("more_matches")>0)body.addView(UiKit.text(this,"일치한 문구가 "+searchItem.optInt("more_matches")+"곳 더 있어요. 검색어를 좁혀서 찾아보세요.",14,false));
        JSONArray tags=detail.content.optJSONArray("tags");if(tags!=null)for(int i=0;i<tags.length();i++){String value=tags.getJSONObject(i).getString("display");body.addView(button("#"+value+" 사진 보기",()->{tag=value;showList();}));}
        message("사진 상세");
    }
    private static float[] quad(JSONArray points)throws JSONException{float[] q=new float[8];for(int i=0;i<4;i++){q[i*2]=(float)points.getJSONArray(i).getDouble(0);q[i*2+1]=(float)points.getJSONArray(i).getDouble(1);}return q;}
    private void newPost(){if(!signedIn()){message("로그인 후 사진을 올릴 수 있어요.");auth(false);return;}if(!session.canPublish){message("운영자만 게시할 수 있습니다.");return;}forms.advance();form=new ComposerState();working=publicImage=null;uncertain=false;showComposer();}
    private void restoreImages(){long ticket=forms.advance();ComposerState state=form;message("작성 사진을 복원하고 있어요…");cpu.execute(()->{Bitmap source=BitmapFactory.decodeFile(state.workingPath),finalImage=BitmapFactory.decodeFile(state.publicPath);runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;working=source;publicImage=finalImage;if(source==null){state.faceChecked=false;state.analysisMessage="작업 사진이 없어 사진을 다시 선택해주세요.";}showComposer();});});}
    private void showComposer(){reviewTab=0;showEditor();}
    private void showReview(){reviewTab=1;showEditor();}
    private void showEditor(){
        if(form==null){showList();return;}hideKeyboard();LinearLayout bar=editor(reviewTab==0?"composer":"review",form.postId>0?"기록 수정":"게시 전 확인",()->navigate(this::showList));
        bar.addView(button("얼굴 편집",()->{hideKeyboard();if(working==null)pick();else showMosaic();}));
        LinearLayout tabRow=UiKit.row(this);String[] names={"글 작성","태그","검색 문구"};
        for(int i=0;i<3;i++){final int tab=i;Button b=button(names[i],()->{reviewTab=tab;showEditor();});if(i==reviewTab)b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(UiKit.GREEN));if(i==reviewTab)b.setTextColor(Color.WHITE);UiKit.weighted(tabRow,b);}workspace.addView(tabRow);
        reviewPhoto=new PhotoCanvas(this);reviewPhoto.bitmap(publicImage!=null?publicImage:working);reviewPhoto.setContentDescription("편집 사진 미리보기");
        int photoHeight=reviewTab==2?164:136;workspace.addView(reviewPhoto,new LinearLayout.LayoutParams(-1,dp(photoHeight)));
        PhotoCanvas responsivePhoto=reviewPhoto;root.getViewTreeObserver().addOnGlobalLayoutListener(new android.view.ViewTreeObserver.OnGlobalLayoutListener(){public void onGlobalLayout(){if(reviewPhoto!=responsivePhoto){root.getViewTreeObserver().removeOnGlobalLayoutListener(this);return;}Rect visible=new Rect();root.getWindowVisibleDisplayFrame(visible);boolean keyboard=root.getRootView().getHeight()-visible.bottom>dp(150);for(View extra:keyboardExtras)extra.setVisibility(keyboard?View.GONE:View.VISIBLE);int height=keyboard?0:Math.min(dp(photoHeight),Math.max(0,workspace.getHeight()-dp(reviewTab==2?396:390)));if(responsivePhoto.getLayoutParams().height!=height){responsivePhoto.getLayoutParams().height=height;responsivePhoto.requestLayout();}}});
        summaryTheme=UiKit.text(this,"",13,true);summaryTags=UiKit.text(this,"",12,false);summaryAnalysis=UiKit.text(this,"",12,false);updateSummary();
        if(reviewTab==2){ocrPanel();}else{
            ScrollView panelScroll=new ScrollView(this);panelScroll.setFillViewport(true);LinearLayout panel=UiKit.column(this);panelScroll.addView(panel);workspace.addView(panelScroll,new LinearLayout.LayoutParams(-1,0,1));
            if(reviewTab==0){
                LinearLayout photoActions=UiKit.row(this);UiKit.weighted(photoActions,button(working==null?"사진 파일 선택":"다른 사진 선택",this::pick));UiKit.weighted(photoActions,button(form.faceChecked?"얼굴 확인 완료":"얼굴 확인·가리기",()->{if(working==null)pick();else showMosaic();}));panel.addView(photoActions);
                EditText title=input("제목",form.title,false),text=input("기록 설명",form.text,true);text.setMinLines(2);text.setMaxLines(4);watch(title,value->form.title=value);watch(text,value->form.text=value);panel.addView(title);panel.addView(text);
                panel.addView(summaryTheme);panel.addView(summaryTags);panel.addView(summaryAnalysis);
            }else tagPanel(panel);
            if(!form.heldCorrections.isEmpty())panel.addView(button("이전 교정 문구 "+form.heldCorrections.size()+"개",()->new AlertDialog.Builder(this).setTitle("이전 교정 · 검색에는 전송하지 않음").setMessage(String.join("\n",form.heldCorrections)).setPositiveButton("닫기",null).show()));
            if(uncertain){panel.addView(UiKit.text(this,"서버 응답을 받지 못했습니다. 같은 글이 있는지 먼저 확인해주세요.",13,false));panel.addView(button("내 글에서 게시 여부 확인",()->{mine=true;showList();}));panel.addView(button("게시되지 않음을 확인했어요",()->new AlertDialog.Builder(this).setTitle("게시 다시 시도").setMessage("내 글에 같은 기록이 없는지 확인했나요?").setNegativeButton("계속 확인",null).setPositiveButton("확인했어요",(d,w)->{uncertain=false;showEditor();}).show()));}
        }
        LinearLayout footer=UiKit.row(this);if(reviewTab!=0)footer.addView(button("확인 완료",()->{try{ThemeMapper.tags(form.tags);form.needsReview=false;form.themeConfirmed=form.tagsConfirmed=true;showComposer();}catch(Exception e){message(e.getMessage());}}));
        Button publish=primary(uncertain?"게시 여부 확인 필요":form.postId>0?"수정 저장":"게시",()->{hideKeyboard();try{ThemeMapper.tags(form.tags);form.needsReview=false;form.themeConfirmed=form.tagsConfirmed=true;publish();}catch(Exception e){message(e.getMessage());}});publish.setEnabled(!uncertain);UiKit.weighted(footer,publish);workspace.addView(footer);
    }
    private void tagPanel(LinearLayout panel){
        Spinner selected=new Spinner(this);String[] labels={"미분류","음식","동물","자연·풍경","인물","건축·공간","사물","기타"};selected.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));int position=0;for(int i=0;i<7;i++)if(ThemeMapper.IDS[i].equals(form.theme))position=i+1;selected.setSelection(position);selected.setContentDescription("대표 테마");selected.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int index,long id){String value=index==0?null:ThemeMapper.IDS[index-1];if(!Objects.equals(value,form.theme)){form.theme=value;form.themeEdited=true;}}});panel.addView(selected);
        panel.addView(UiKit.text(this,"태그 · 눌러서 추가하거나 빼세요 (최대 10개)",13,true));ChipFlow chips=new ChipFlow(this);panel.addView(chips);renderTags(chips);
        LinearLayout add=UiKit.row(this);EditText field=input("태그 추가", "",false);field.setImeOptions(EditorInfo.IME_ACTION_DONE);add.addView(field,new LinearLayout.LayoutParams(0,dp(48),1));Runnable save=()->{try{List<String> values=ThemeMapper.tags(form.tags+","+field.getText());form.tags=String.join(", ",values);form.tagsEdited=true;field.setText("");renderTags(chips);hideKeyboard();}catch(Exception e){message(e.getMessage());}};add.addView(button("추가",save));field.setOnEditorActionListener((v,a,event)->{if(a==EditorInfo.IME_ACTION_DONE){save.run();return true;}return false;});panel.addView(add);
        if(!form.alternatives.isEmpty()){panel.addView(UiKit.text(this,"추천 테마",12,false));ChipFlow alternatives=new ChipFlow(this);for(String option:form.alternatives)alternatives.addView(button(ThemeMapper.name(option),()->{for(int i=0;i<7;i++)if(ThemeMapper.IDS[i].equals(option))selected.setSelection(i+1);}));panel.addView(alternatives);}
        panel.addView(summaryAnalysis);panel.addView(button("다시 분석",()->analyze(true)));
    }
    private void renderTags(ChipFlow chips){
        chips.removeAllViews();List<String> selected=ThemeMapper.tags(form.tags);LinkedHashSet<String> values=new LinkedHashSet<>(selected);values.addAll(form.tagSuggestions);
        for(String value:values){boolean on=selected.contains(value);Button chip=button((on?"✓ ":"+ ")+value,()->{try{List<String> next=ThemeMapper.tags(form.tags);if(next.contains(value))next.remove(value);else next.add(value);form.tags=String.join(", ",ThemeMapper.tags(String.join(",",next)));form.tagsEdited=true;renderTags(chips);}catch(Exception e){message(e.getMessage());}});if(on){chip.setTextColor(Color.WHITE);chip.setBackgroundTintList(android.content.res.ColorStateList.valueOf(UiKit.GREEN));}chips.addView(chip);}
    }
    private void ocrPanel(){
        LinearLayout panel=UiKit.column(this);workspace.addView(panel,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout tools=UiKit.row(this);CheckBox skip=new CheckBox(this);skip.setText("검색 안 함");skip.setChecked("skipped".equals(form.ocrStatus));tools.addView(skip,new LinearLayout.LayoutParams(0,dp(48),1));tools.addView(button("다시 읽기",()->analyze(true)));panel.addView(tools);keyboardExtras.add(tools);
        TextView count=UiKit.text(this,"",12,false);count.setMaxLines(2);Runnable updateCount=()->{long included=form.lines.stream().filter(l->l.included).count();count.setText(included+"/"+form.lines.size()+"개 포함");message("검색 문구 "+form.lines.size()+"곳 · "+included+"개 포함");};updateCount.run();
        LinearLayout all=UiKit.row(this);all.addView(count,new LinearLayout.LayoutParams(0,-2,1));ListView list=new ListView(this);list.setContentDescription("검색 문구 목록");list.setChoiceMode(ListView.CHOICE_MODE_NONE);
        EditText correction=input("선택한 문구 교정","",false);selectedLine=Math.min(selectedLine,Math.max(0,form.lines.size()-1));
        BaseAdapter adapter=new BaseAdapter(){public int getCount(){return form.lines.size();}public Object getItem(int i){return form.lines.get(i);}public long getItemId(int i){return i;}public View getView(int i,View old,ViewGroup parent){VisionEngine.Line line=form.lines.get(i);LinearLayout row=UiKit.row(MainActivity.this);CheckBox check=new CheckBox(MainActivity.this);check.setContentDescription((i+1)+"번 문구 검색 포함");check.setChecked(line.included);check.setEnabled(!skip.isChecked());check.setOnCheckedChangeListener((v,on)->{line.included=on;updateCount.run();});row.addView(check,new LinearLayout.LayoutParams(dp(48),dp(48)));TextView text=UiKit.text(MainActivity.this,(i+1)+"  "+line.text,14,false);text.setSingleLine(true);text.setEllipsize(android.text.TextUtils.TruncateAt.END);text.setMinHeight(dp(48));text.setGravity(Gravity.CENTER_VERTICAL);row.addView(text,new LinearLayout.LayoutParams(0,dp(48),1));if(i==selectedLine)row.setBackgroundColor(UiKit.SAGE);View.OnClickListener choose=v->{selectedLine=i;correction.setText(line.text);reviewPhoto.highlights(List.of(line.quad));reviewPhoto.focus(line.quad);notifyDataSetChanged();};row.setOnClickListener(choose);text.setOnClickListener(choose);return row;}};
        list.setAdapter(adapter);UiKit.weighted(all,button("모두 포함",()->{for(VisionEngine.Line l:form.lines)l.included=true;adapter.notifyDataSetChanged();updateCount.run();}));UiKit.weighted(all,button("모두 제외",()->{for(VisionEngine.Line l:form.lines)l.included=false;adapter.notifyDataSetChanged();updateCount.run();}));panel.addView(all);keyboardExtras.add(all);
        panel.addView(list,new LinearLayout.LayoutParams(-1,0,1));
        if(form.lines.isEmpty())count.setText(analyzing?"글자를 읽고 있어요…":"인식한 글자가 없어요. 다시 읽을 수 있습니다.");
        else{correction.setText(form.lines.get(selectedLine).text);reviewPhoto.highlights(List.of(form.lines.get(selectedLine).quad));}
        correction.setEnabled(!form.lines.isEmpty());watch(correction,value->{if(selectedLine<form.lines.size()){VisionEngine.Line line=form.lines.get(selectedLine);if(!line.text.equals(value)){line.text=value;line.origin="user";adapter.notifyDataSetChanged();}}});panel.addView(correction);
        skip.setOnCheckedChangeListener((v,on)->{if(on){forms.advance();analyzing=false;form.ocrStatus="skipped";}else form.ocrStatus=form.lines.isEmpty()?"not_analyzed":"ready";list.setEnabled(!on);correction.setEnabled(!on&&!form.lines.isEmpty());enableTree(all,!on);adapter.notifyDataSetChanged();});if(skip.isChecked()){list.setEnabled(false);correction.setEnabled(false);enableTree(all,false);}
        TextView note=UiKit.text(this,"체크한 문구만 검색에 포함 · 사진의 글자는 지워지지 않아요.",11,false);panel.addView(note);keyboardExtras.add(note);
    }
    private void pick(){if(networkBusy)return;Intent picker=new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);picker.putExtra(Intent.EXTRA_MIME_TYPES,new String[]{"image/jpeg","image/png","image/webp"});startActivityForResult(picker,PICK);}
    @Override protected void onActivityResult(int request,int result,Intent intent){super.onActivityResult(request,result,intent);if(request!=PICK||result!=RESULT_OK||intent==null||intent.getData()==null||form==null)return;Uri uri=intent.getData();long ticket=forms.advance();ComposerState state=form;boolean wasChecked=state.faceChecked;state.faceChecked=false;message("사진을 준비하고 얼굴을 찾고 있어요…");analyzing=true;
        cpu.execute(()->{try{Bitmap source=PhotoPipeline.read(getApplicationContext(),uri);File file=PhotoPipeline.saveWorking(getApplicationContext(),source);List<MosaicDraft.Region> detected;String note;try{detected=vision.faces(source);note=detected.isEmpty()?"자동으로 찾은 얼굴이 없어요. 직접 확인해주세요.":"얼굴 "+detected.size()+"곳을 가렸어요. 누락된 얼굴을 확인해주세요.";}catch(Exception error){detected=Collections.emptyList();note="얼굴을 찾지 못했어요. 다시 시도하거나 직접 가려주세요.";}List<MosaicDraft.Region> found=detected;String message=note;
            runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;analyzing=false;holdCorrections(state);state.mosaic.replace(Collections.emptyList());state.mosaic.detected(found);state.mosaic.checkpoint();state.workingPath=file.getAbsolutePath();state.publicPath="";state.sha="";state.faceChecked=false;state.needsReview=state.themeEdited||state.tagsEdited;working=source;publicImage=null;state.analysisMessage=message;showMosaic();message(message);});
        }catch(Exception error){runOnUiThread(()->{if(forms.accepts(ticket)){analyzing=false;state.faceChecked=wasChecked;message(error.getMessage());}});}});
    }
    private void holdCorrections(ComposerState state){for(VisionEngine.Line line:state.lines)if("user".equals(line.origin)&&!state.heldCorrections.contains(line.text))state.heldCorrections.add(line.text);while(state.heldCorrections.size()>100)state.heldCorrections.remove(0);state.lines.clear();state.ocrStatus="not_analyzed";if(!state.themeEdited)state.theme=null;if(!state.tagsEdited)state.tags="";state.themeConfirmed=state.tagsConfirmed=false;state.alternatives.clear();state.tagSuggestions.clear();}
    private void showMosaic(){
        if(working==null){showComposer();return;}hideKeyboard();LinearLayout bar=editor("mosaic","얼굴 가리기",()->{form.mosaic.reset();showComposer();});form.mosaic.checkpoint();bar.addView(button("⋯",this::mosaicMenu));
        mosaicCanvas=new PhotoCanvas(this);mosaicCanvas.edit(form.mosaic,new PhotoCanvas.Listener(){public void changed(){setMosaicMode(mosaicCanvas.mode());regionControls();renderMosaic();}public void selected(int i){regionControls();}});mosaicCanvas.mode("edit");workspace.addView(mosaicCanvas,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout modes=UiKit.row(this);String[] modeIds={"view","edit","add"},modeNames={"이동","선택","그리기"};for(int i=0;i<3;i++){String id=modeIds[i];Button b=button(modeNames[i],()->{setMosaicMode(id);message("add".equals(id)?"사진 위를 끌어 가릴 영역을 추가하세요.":"view".equals(id)?"두 손가락으로 확대 · 끌어서 이동":"영역을 선택하고 끌어 위치·크기를 바꾸세요.");});mosaicModes.put(id,b);UiKit.weighted(modes,b);}UiKit.weighted(modes,button("되돌림",()->{form.mosaic.undo();mosaicCanvas.select(-1);renderMosaic();}));workspace.addView(modes);setMosaicMode("edit");
        regionControls=UiKit.column(this);workspace.addView(regionControls);regionControls();workspace.addView(primary("게시 사본에 적용",this::applyMosaic));renderMosaic();
    }
    private void setMosaicMode(String mode){if(mosaicCanvas==null)return;mosaicCanvas.mode(mode);mosaicModes.forEach((id,b)->{boolean selected=id.equals(mode);b.setSelected(selected);b.setTextColor(selected?Color.WHITE:UiKit.INK);b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(selected?UiKit.GREEN:UiKit.SAGE));});}
    private void mosaicMenu(){new AlertDialog.Builder(this).setTitle("사진 편집").setItems(new String[]{"얼굴 다시 찾기","전체 보기","초기화","편집 취소"},(d,i)->{if(i==0)redetect();else if(i==1)mosaicCanvas.resetZoom();else if(i==2){form.mosaic.reset();mosaicCanvas.select(-1);renderMosaic();}else{form.mosaic.reset();showComposer();}}).show();}
    private void regionControls(){
        if(regionControls==null||mosaicCanvas==null)return;regionControls.removeAllViews();List<MosaicDraft.Region> regions=form.mosaic.regions();int selected=mosaicCanvas.selected();
        LinearLayout row=UiKit.row(this);Spinner chooser=new Spinner(this);List<String> labels=new ArrayList<>();labels.add("영역 "+regions.size()+"개 · 선택");for(int i=0;i<regions.size();i++)labels.add((i+1)+"번 · "+(regions.get(i).active?"가림":"표시"));chooser.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,labels));chooser.setSelection(selected+1);chooser.setContentDescription("가림 영역 선택");chooser.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> p){}public void onItemSelected(AdapterView<?> p,View v,int pos,long id){if(pos-1!=mosaicCanvas.selected())mosaicCanvas.select(pos-1);}});row.addView(chooser,new LinearLayout.LayoutParams(0,dp(48),1));
        row.addView(button("영역 설정",()->regionSettings()));regionControls.addView(row);
    }
    private void regionSettings(){
        int i=mosaicCanvas.selected();List<MosaicDraft.Region> regions=form.mosaic.regions();if(i<0||i>=regions.size()){message("사진의 영역을 먼저 선택해주세요.");return;}MosaicDraft.Region r=regions.get(i);
        String[] options={r.active?"가림 해제":"가리기","약하게","보통","강하게","영역 삭제","크기 줄이기","크기 늘리기","위로","아래로","왼쪽","오른쪽"};
        new AlertDialog.Builder(this).setTitle((i+1)+"번 영역").setItems(options,(d,which)->{if(which==0)form.mosaic.update(i,new MosaicDraft.Region(r.id,r.left,r.top,r.right,r.bottom,!r.active,r.automatic,r.strength));else if(which<=3)form.mosaic.update(i,new MosaicDraft.Region(r.id,r.left,r.top,r.right,r.bottom,r.active,r.automatic,which-1));else if(which==4){form.mosaic.remove(i);mosaicCanvas.select(-1);}else{String[] actions={"small","large","↑","↓","←","→"};nudge(actions[which-5]);}regionControls();renderMosaic();}).show();
    }
    private void nudge(String action){int i=mosaicCanvas.selected();if(i<0||i>=form.mosaic.regions().size())return;MosaicDraft.Region r=form.mosaic.regions().get(i);float dx="←".equals(action)?-.01f:"→".equals(action)?.01f:0,dy="↑".equals(action)?-.01f:"↓".equals(action)?.01f:0;MosaicDraft.Region next;
        if(action.equals("small")||action.equals("large")){float amount=action.equals("small")?-.01f:.01f;next=r.bounds(r.left,r.top,Math.max(r.left+.005f,Math.min(1,r.right+amount)),Math.max(r.top+.005f,Math.min(1,r.bottom+amount)));}else{dx=Math.max(-r.left,Math.min(1-r.right,dx));dy=Math.max(-r.top,Math.min(1-r.bottom,dy));next=r.bounds(r.left+dx,r.top+dy,r.right+dx,r.bottom+dy);}form.mosaic.update(i,next);renderMosaic();}
    private void renderMosaic(){if(mosaicCanvas==null)return;PhotoCanvas target=mosaicCanvas;long ticket=previews.advance();Bitmap source=working;List<MosaicDraft.Region> regions=form.mosaic.regions();cpu.execute(()->{if(!previews.accepts(ticket))return;Bitmap preview=PhotoPipeline.render(source,regions);runOnUiThread(()->{if(!isDestroyed()&&previews.accepts(ticket)&&mosaicCanvas==target)target.bitmap(preview);});});}
    private void redetect(){if(analyzing)return;analyzing=true;long ticket=forms.current();Bitmap source=working;message("얼굴을 다시 찾고 있어요…");cpu.execute(()->{try{List<MosaicDraft.Region> found=vision.faces(source);runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;analyzing=false;form.mosaic.detected(found);if(mosaicCanvas!=null){mosaicCanvas.select(-1);renderMosaic();}message("자동 탐지 "+found.size()+"곳 · 직접 만든 영역은 유지했어요.");});}catch(Exception error){runOnUiThread(()->{if(forms.accepts(ticket)){analyzing=false;message("얼굴 탐지 실패 · 직접 영역을 추가할 수 있어요.");}});}});}
    private void applyMosaic(){if(analyzing){message("사진 처리가 끝날 때까지 기다려주세요.");return;}long ticket=forms.advance();ComposerState state=form;Bitmap source=working;List<MosaicDraft.Region> regions=state.mosaic.regions();analyzing=true;message("실제 게시 사본을 만들고 있어요…");cpu.execute(()->{try{Bitmap rendered=PhotoPipeline.render(source,regions);PhotoPipeline.Encoded result=PhotoPipeline.encode(getApplicationContext(),rendered);rendered.recycle();runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;holdCorrections(state);state.publicPath=result.file().getAbsolutePath();state.sha=result.sha256();state.width=result.bitmap().getWidth();state.height=result.bitmap().getHeight();state.faceChecked=true;state.needsReview=state.themeEdited||state.tagsEdited||!state.heldCorrections.isEmpty();publicImage=result.bitmap();analyzing=false;state.analysisMessage="테마와 사진 속 글자를 분석하고 있어요…";showComposer();analyze(false);});}catch(Exception error){runOnUiThread(()->{if(forms.accepts(ticket)){analyzing=false;message(error.getMessage());}});}});}
    private void analyze(boolean retry){if(form==null||publicImage==null||!form.faceChecked){message("게시 사본을 먼저 확인해주세요.");return;}if(analyzing)return;analyzing=true;long ticket=forms.advance();ComposerState state=form;Bitmap source=publicImage;state.analysisMessage="테마와 글자 분석 중 · 이야기를 작성할 수 있어요.";message(state.analysisMessage);cpu.execute(()->{VisionEngine.Analysis result=vision.analyze(source);runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;analyzing=false;
            Runnable apply=()->{if(result.suggestion()!=null){if(!state.themeEdited&&!state.themeConfirmed)state.theme=result.suggestion().theme();if(!state.tagsEdited&&!state.tagsConfirmed)state.tags=String.join(", ",result.suggestion().tags());state.tagSuggestions.clear();state.tagSuggestions.addAll(result.suggestion().tags());state.alternatives.clear();for(ThemeMapper.Ranked alternative:result.suggestion().alternatives())state.alternatives.add(alternative.theme());}state.lines.clear();state.lines.addAll(result.lines());state.ocrStatus=result.ocrStatus();state.analysisMessage=(result.suggestion()==null?"분류 추천 실패 · 직접 선택 가능":state.theme==null?"테마 확인 필요":"추천 테마: "+ThemeMapper.name(state.theme))+" · "+ocrSummary(state);if("review".equals(page)&&!(root.findFocus() instanceof EditText))showEditor();else if("review".equals(page)||"composer".equals(page))updateSummary();message(state.analysisMessage);};
            if(retry&&state.lines.stream().anyMatch(l->"user".equals(l.origin)))new AlertDialog.Builder(this).setTitle("새 인식 결과 확인").setMessage("새 문구로 교체하면 현재 교정한 문구가 바뀝니다. 직접 고른 테마와 태그는 유지합니다.").setNegativeButton("현재 문구 유지",(d,w)->message("현재 교정 문구를 유지했어요.")).setPositiveButton("새 문구로 교체",(d,w)->apply.run()).show();else apply.run();
        });});}
    private String ocrSummary(ComposerState state){if("ready".equals(state.ocrStatus)){long count=state.lines.stream().filter(l->l.included).count();return "검색 문구 "+state.lines.size()+"곳 · "+count+"개 포함";}return switch(state.ocrStatus){case "no_text"->"인식한 글자 없음";case "failed"->"글자 인식 실패 · 다시 시도 가능";case "skipped"->"사진 속 글자 검색 미사용";default->"글자 분석 전";};}
    private void publish(){if(form==null||networkBusy)return;if(!signedIn()){auth(false);return;}if(!session.canPublish){message("운영자만 게시할 수 있습니다.");return;}if(form.title.trim().isEmpty()||form.text.trim().isEmpty()){message("제목과 기록 설명를 입력해주세요.");return;}if(!form.faceChecked||form.publicPath.isEmpty()){message("사진의 얼굴을 먼저 확인해주세요.");if(working!=null)showMosaic();return;}if(form.needsReview){message("사진이 바뀌었습니다. 분류와 문구를 다시 확인해주세요.");showReview();return;}
        if(analyzing){new AlertDialog.Builder(this).setTitle("사진 분석 중").setMessage("분석을 기다리거나 자동 결과 없이 게시를 준비할 수 있습니다.").setNegativeButton("기다리기",null).setPositiveButton("분석 없이 계속",(d,w)->{forms.advance();analyzing=false;form.ocrStatus="skipped";form.lines.clear();form.analysisMessage="자동 분석 없이 게시합니다.";showComposer();}).show();return;}
        ComposerState state=form;try{JSONObject packet=state.packet();request("기록을 저장하고 있어요…",()->{byte[] bytes=readLocal(state.publicPath);try{return state.postId==0?api.upload(state.title,state.text,bytes,"image/jpeg","public-photo.jpg",packet.toString()):state.sha.equals(state.originalSha)?api.updateText(state.postId,state.title,state.text,packet):api.updatePhoto(state.postId,state.title,state.text,bytes,packet.toString());}catch(IOException error){if(!(error instanceof HttpException)){runOnUiThread(()->{uncertain=true;message("서버 응답을 받지 못해 게시 여부 확인이 필요합니다. 자동으로 다시 게시하지 않습니다.");showComposer();});}throw error;}},post->{form=null;working=publicImage=null;forms.advance();uncertain=false;showCommitted(post);openDetail(post,null);});}catch(Exception error){message(error.getMessage());}
    }
    private void showCommitted(PhotoPost post){clear("committed");body.addView(UiKit.text(this,"기록 등록 완료",26,true));body.addView(UiKit.text(this,post.title,18,true));body.addView(UiKit.text(this,"게시글 "+post.id+"에 저장했습니다. 상세 조회가 실패해도 다시 게시할 필요가 없습니다.",15,false));body.addView(button("기록 다시 열기",()->openDetail(post,null)));body.addView(button("목록으로",this::showList));message("기록 등록 완료 · "+post.id);}
    private static byte[] readLocal(String path)throws IOException{try(InputStream in=new FileInputStream(path);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] buffer=new byte[8192];int count;while((count=in.read(buffer))!=-1){if(out.size()+count>5*1024*1024)throw new IOException("사진은 5MiB 이하여야 합니다.");out.write(buffer,0,count);}return out.toByteArray();}}
    private void loadEditing(Detail detail){
        if(form!=null)return;ComposerState state=new ComposerState();state.postId=detail.post.id;state.title=detail.post.title;state.text=detail.post.text;state.revision=detail.content.optLong("revision");state.theme=detail.content.isNull("theme")?null:detail.content.optString("theme");state.themeEdited="user".equals(detail.content.optString("theme_origin"));state.themeConfirmed=state.tagsConfirmed=true;state.tagsEdited=true;
        try{JSONArray tags=detail.content.optJSONArray("tags");List<String> names=new ArrayList<>();if(tags!=null)for(int i=0;i<tags.length();i++)names.add(tags.getJSONObject(i).getString("display"));state.tags=String.join(", ",names);JSONArray lines=detail.content.optJSONArray("lines");if(lines!=null)for(int i=0;i<lines.length();i++){JSONObject value=lines.getJSONObject(i);VisionEngine.Line line=new VisionEngine.Line(value.getString("line_id"),value.getString("text"),quad(value.getJSONArray("quad")));line.origin=value.optString("origin","auto");state.lines.add(line);}state.ocrStatus=detail.content.optString("ocr_status","not_analyzed");}catch(JSONException error){message(error.getMessage());return;}
        long ticket=forms.advance();message("수정할 사진을 준비하고 있어요…");cpu.execute(()->{try{File saved=File.createTempFile("public-photo-",".jpg",getCacheDir());try(FileOutputStream out=new FileOutputStream(saved)){out.write(detail.bytes);}Bitmap bitmap=BitmapFactory.decodeByteArray(detail.bytes,0,detail.bytes.length);state.publicPath=saved.getAbsolutePath();state.workingPath=PhotoPipeline.saveWorking(getApplicationContext(),bitmap).getAbsolutePath();state.sha=state.originalSha=PhotoPipeline.sha256(detail.bytes);state.width=bitmap.getWidth();state.height=bitmap.getHeight();state.faceChecked=true;state.analysisMessage=ocrSummary(state);runOnUiThread(()->{if(!forms.accepts(ticket)||isDestroyed())return;form=state;working=publicImage=bitmap;showComposer();});}catch(Exception error){runOnUiThread(()->message(error.getMessage()));}});
    }
    private void reloadEditing(){if(form==null||form.postId<=0)return;long id=form.postId;request("최신 내용을 불러오고 있어요…",()->{for(PhotoPost p:api.getPosts())if(p.id==id)return new Detail(p,api.content(id),api.downloadPhoto(p.imageUrl));throw new IOException("게시글이 삭제되었거나 보이지 않습니다.");},detail->{form=null;loadEditing(detail);});}
}


