package com.haddol7.photoviewer.ui;

import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.*;
import android.test.ActivityInstrumentationTestCase2;
import android.view.*;
import android.webkit.*;
import android.widget.*;
import com.haddol7.photoviewer.MainActivity;
import com.haddol7.photoviewer.content.*;
import com.haddol7.photoviewer.data.PhotoRepository;
import com.haddol7.photoviewer.model.PhotoPost;
import org.json.*;
import java.io.*;
import java.lang.reflect.*;
import java.net.HttpCookie;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

/** Captures actual Android rendering on an isolated WSL fixture before and after product changes. */
@SuppressWarnings("deprecation")
public final class UiAuditTest extends ActivityInstrumentationTestCase2<MainActivity> {
    private MainActivity activity;private JSONObject config;private String previous;private PhotoRepository api;
    private final JSONArray screens=new JSONArray();private WebView web;
    public UiAuditTest(){super(MainActivity.class);}
    @Override protected void setUp()throws Exception{
        super.setUp();File f=new File(getInstrumentation().getTargetContext().getExternalFilesDir(null),"ui-audit-config.json");
        try(InputStream in=new FileInputStream(f)){config=new JSONObject(new String(in.readAllBytes(),StandardCharsets.UTF_8));}
        assertTrue(config.getString("server").startsWith("http://10.0.2.2:"));
        SharedPreferences p=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);
        previous=p.getString("origin",null);p.edit().putString("origin",config.getString("server")).commit();
        activity=getActivity();api=(PhotoRepository)field("api");
    }
    @Override protected void tearDown()throws Exception{
        File directory=new File(activity.getExternalFilesDir(null),"ui-audit");directory.mkdirs();
        try(FileOutputStream out=new FileOutputStream(new File(directory,getName()+".json"))){out.write(screens.toString(2).getBytes(StandardCharsets.UTF_8));}
        SharedPreferences.Editor p=activity.getSharedPreferences("MainActivity",0).edit();if(previous==null)p.remove("origin");else p.putString("origin",previous);p.commit();super.tearDown();
    }
    private Object field(String name)throws Exception{Field f=MainActivity.class.getDeclaredField(name);f.setAccessible(true);return f.get(activity);}
    private void set(String name,Object value)throws Exception{Field f=MainActivity.class.getDeclaredField(name);f.setAccessible(true);f.set(activity,value);}
    private void invoke(String name)throws Exception{Method m=MainActivity.class.getDeclaredMethod(name);m.setAccessible(true);getInstrumentation().runOnMainSync(()->{try{m.invoke(activity);}catch(Exception e){throw new RuntimeException(e);}});}
    private void person(String key)throws Exception{Method m=MainActivity.class.getDeclaredMethod("showPerson",String.class);m.setAccessible(true);getInstrumentation().runOnMainSync(()->{try{m.invoke(activity,key);}catch(Exception e){throw new RuntimeException(e);}});await(()->!((Boolean)field("networkBusy")));}
    private interface Check{boolean ready()throws Exception;}
    private void await(Check check)throws Exception{long end=SystemClock.elapsedRealtime()+60000;while(SystemClock.elapsedRealtime()<end){if(check.ready())return;Thread.sleep(120);}fail("Audit screen timed out");}
    private TextView text(View view,String value){if(view instanceof TextView&&value.equals(((TextView)view).getText().toString()))return (TextView)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){TextView v=text(((ViewGroup)view).getChildAt(i),value);if(v!=null)return v;}return null;}
    private EditText edit(View view,String hint){if(view instanceof EditText&&hint.contentEquals(((EditText)view).getHint()))return (EditText)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){EditText v=edit(((ViewGroup)view).getChildAt(i),hint);if(v!=null)return v;}return null;}
    private View described(View view,String description){if(description.equals(String.valueOf(view.getContentDescription())))return view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View found=described(((ViewGroup)view).getChildAt(i),description);if(found!=null)return found;}return null;}
    private android.view.accessibility.AccessibilityNodeInfo activeEditor(android.view.accessibility.AccessibilityNodeInfo node,String hint){
        if(node==null)return null;if("android.widget.EditText".contentEquals(node.getClassName())&&(hint.equals(String.valueOf(node.getHintText()))||hint.equals(String.valueOf(node.getContentDescription()))))return node;
        for(int i=0;i<node.getChildCount();i++){android.view.accessibility.AccessibilityNodeInfo found=activeEditor(node.getChild(i),hint);if(found!=null)return found;}return null;
    }
    private void click(String label)throws Exception{
        boolean[] clicked={false};getInstrumentation().runOnMainSync(()->{TextView v=text(activity.getWindow().getDecorView(),label);if(v!=null&&v.isShown()){v.performClick();clicked[0]=true;}});
        if(!clicked[0]){android.view.accessibility.AccessibilityNodeInfo root=getInstrumentation().getUiAutomation().getRootInActiveWindow();
            for(android.view.accessibility.AccessibilityNodeInfo n:root.findAccessibilityNodeInfosByText(label))if(label.equals(String.valueOf(n.getText()))){
                while(n!=null&&!n.isClickable())n=n.getParent();if(n!=null&&n.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)){clicked[0]=true;break;}}}
        assertTrue("Missing action: "+label,clicked[0]);Thread.sleep(250);
    }
    private void idle()throws Exception{Thread.sleep(650);getInstrumentation().waitForIdleSync();}
    private void listReady()throws Exception{await(()->((TextView)field("status")).getText().toString().contains("동기화 완료"));idle();}
    private void capture(String name)throws Exception{
        if(web!=null)assertTrue("Capture must show the instrumented WebView, not another app",activity.hasWindowFocus());
        idle();Bitmap b=getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(b);
        File d=new File(activity.getExternalFilesDir(null),"ui-audit");d.mkdirs();
        try(FileOutputStream out=new FileOutputStream(new File(d,name+".png"))){b.compress(Bitmap.CompressFormat.PNG,100,out);}b.recycle();
        JSONObject row=new JSONObject().put("name",name).put("width_px",activity.getResources().getDisplayMetrics().widthPixels).put("density",activity.getResources().getDisplayMetrics().density);
        if(web==null&&"after".equals(config.optString("phase"))&&(name.equals("native-compose")||name.equals("native-mosaic")||name.equals("native-story")||name.equals("native-tags")||name.startsWith("native-ocr")||name.startsWith("native-questions"))){
            int[] bounds=new int[4];getInstrumentation().runOnMainSync(()->{View decor=activity.getWindow().getDecorView(),done=described(decor,"고정 완료 버튼");assertNotNull(done);Rect visible=new Rect(),button=new Rect();decor.getWindowVisibleDisplayFrame(visible);assertTrue(done.getGlobalVisibleRect(button));assertTrue("Primary action must be fully visible",button.height()>=done.getHeight()-2);bounds[0]=button.top;bounds[1]=button.bottom;bounds[2]=visible.top;bounds[3]=visible.bottom;});
            row.put("primary_button_top_px",bounds[0]).put("primary_button_bottom_px",bounds[1]).put("viewport_bottom_px",bounds[3]);assertTrue("Primary editor action must fit",bounds[0]>=bounds[2]&&bounds[1]<=bounds[3]+2);
        }
        if(web!=null){String raw=eval("JSON.stringify({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth+1,firstPhotoTop:(document.querySelector('.history-card img,.post-thumbnail img,.hero-image')?.getBoundingClientRect().top??null),visibleCards:[...document.querySelectorAll('.history-card,.post-grid article')].filter(e=>e.getBoundingClientRect().top<innerHeight&&e.getBoundingClientRect().bottom>0).length,dialogOpen:!!document.querySelector('dialog[open]'),active:document.activeElement?.id})");row.put("web",new JSONObject(new JSONArray("["+raw+"]").getString(0)));}
        screens.put(row);
    }
    private void login()throws Exception{set("session",api.login(config.getString("username"),config.getString("password")));invoke("showList");listReady();}
    public void testNativeAllPages()throws Exception{
        listReady();capture("native-dashboard-guest");invoke("showList");listReady();capture("native-feed-guest");
        click("계정·설정");click("운영자 로그인");capture("native-login");
        if("after".equals(config.optString("phase"))){click("로그인");capture("native-login-error");}
        getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);login();capture("native-feed-owner");invoke("showHome");await(()->!((Boolean)field("networkBusy")));capture("native-dashboard-owner");invoke("showPeople");await(()->!((Boolean)field("networkBusy")));capture("native-people");nativeChatKeyboard();invoke("showList");listReady();
        assertEquals(3,((LinearLayout)field("tabs")).getChildCount());
        assertEquals("관측 기록",((Button)field("recordsTab")).getText().toString());
        assertEquals("인물 확인",((Button)field("peopleTab")).getText().toString());
        assertEquals("AI 질문",((Button)field("questionsTab")).getText().toString());
        getInstrumentation().runOnMainSync(()->{try{((Button)field("recordsTab")).performClick();}catch(Exception e){throw new RuntimeException(e);}});
        await(()->!((Boolean)field("networkBusy"))&&"history".equals(field("page")));capture("native-primary-records");
        person("showcase-v2-c");capture("native-person-timeline");click("같은 인물인지 확인 (2)");capture("native-person-comparison");
        click("같은 인물로 확인");await(()->!((Boolean)field("networkBusy"))&&api.historyPerson("showcase-v2-c").getInt("confirmed_tracks")>0);capture("native-person-confirmed");
        set("query","ui-audit-no-match");invoke("showList");listReady();capture("native-empty-search");set("query","");invoke("showList");listReady();
        click("기록 열기");idle();capture("native-post-detail");
        invoke("newPost");capture("native-compose");
        Bitmap portrait;try(InputStream in=getInstrumentation().getContext().getAssets().open("portrait.jpg")){portrait=BitmapFactory.decodeStream(in);}
        ComposerState draft=(ComposerState)field("form");draft.title="사진 기록";draft.text="사진과 함께 남기는 이야기입니다.";
        draft.theme="people";draft.tags="일상,기록";draft.analysisMessage="분석 결과를 확인해주세요.";draft.ocrStatus="ready";
        draft.lines.add(new VisionEngine.Line("ui-line","CAFE MENU",new float[]{.1f,.1f,.8f,.1f,.8f,.2f,.1f,.2f}));
        set("working",portrait);set("publicImage",portrait);draft.faceChecked=true;
        invoke("showMosaic");capture("native-mosaic");invoke("showComposer");capture("native-story");
        click("태그");capture("native-tags");click("검색 문구");capture("native-ocr");
        getInstrumentation().runOnMainSync(()->{EditText f=edit(activity.getWindow().getDecorView(),"선택한 문구 교정");if(f!=null){f.requestFocus();((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(f,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);}});
        capture("native-ocr-keyboard");getInstrumentation().runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(activity.getWindow().getDecorView().getWindowToken(),0));
        set("form",null);invoke("showHistory");await(()->!((Boolean)field("networkBusy"))&&((LinearLayout)field("historyCards")).getChildCount()>0);idle();capture("native-history");
        click("조회 조건");capture("native-history-filters");getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);
        JSONObject frames=api.historyFrames("","","",false,1);JSONObject first=frames.getJSONArray("results").getJSONObject(0);
        Method detail=MainActivity.class.getDeclaredMethod("historyDetail",JSONObject.class);detail.setAccessible(true);
        getInstrumentation().runOnMainSync(()->{try{detail.invoke(activity,first);}catch(Exception e){throw new RuntimeException(e);}});capture("native-history-detail");
        getInstrumentation().sendKeyDownUpSync(KeyEvent.KEYCODE_BACK);
        nativeChatConversation();
    }
    private int chatAnswers(View view){int count="채팅 답변".equals(String.valueOf(view.getContentDescription()))?1:0;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)count+=chatAnswers(((ViewGroup)view).getChildAt(i));return count;}
    private void chatReady()throws Exception{await(()->{boolean[] ready={false};getInstrumentation().runOnMainSync(()->{TextView send=text(activity.getWindow().getDecorView(),"보내기");ready[0]=send!=null&&send.isEnabled();});return ready[0];});}
    private void nativeChatKeyboard()throws Exception{invoke("showQuestions");chatReady();capture("native-questions-page");getInstrumentation().runOnMainSync(()->{EditText question=edit(activity.getWindow().getDecorView(),"관측 기록에 질문하세요");assertNotNull(question);question.requestFocus();((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(question,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);});capture("native-questions-keyboard");getInstrumentation().runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(activity.getWindow().getDecorView().getWindowToken(),0));}
    private void nativeChatSend(String value,int expected)throws Exception{getInstrumentation().runOnMainSync(()->edit(activity.getWindow().getDecorView(),"관측 기록에 질문하세요").setText(value));click("보내기");await(()->{int[] count={0};getInstrumentation().runOnMainSync(()->count[0]=chatAnswers(activity.getWindow().getDecorView()));return count[0]>=expected;});chatReady();}
    private void nativeChatConversation()throws Exception{click("AI 질문");chatReady();click("새 대화");nativeChatSend("몇 번 통과했어?",1);capture("native-chat-first-answer");nativeChatSend("그 영상은 언제 분석됐어?",2);capture("native-chat-followup");click("새 대화");capture("native-chat-new");click("대화 기록");await(()->!getInstrumentation().getUiAutomation().getRootInActiveWindow().findAccessibilityNodeInfosByText("몇 번 통과했어?").isEmpty());capture("native-chat-history");click("몇 번 통과했어?");await(()->{int[] count={0};getInstrumentation().runOnMainSync(()->count[0]=chatAnswers(activity.getWindow().getDecorView()));return count[0]>=2;});capture("native-chat-restored");}
    private void webChatFlows()throws Exception{
        load("/questions/?chat=new","document.querySelector('#chat-send')?.disabled===false");assertEquals("true",eval("!document.querySelector('input[type=checkbox]') && getComputedStyle(document.body).fontFamily.includes('Pretendard')"));capture("web-questions-page");double height=Double.parseDouble(eval("innerHeight"));tapWeb("#question");await(()->Double.parseDouble(eval("innerHeight"))<height-80);capture("web-questions-keyboard");assertEquals("true",eval("(()=>{const e=document.querySelector('#chat-send'),r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+2&&document.elementFromPoint(r.left+r.width/2,r.bottom-3)===e})()"));getInstrumentation().runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(web.getWindowToken(),0));eval("document.activeElement.blur()");await(()->Double.parseDouble(eval("innerHeight"))>=height-2);
        eval("document.querySelector('#question').value='몇 번 통과했어?';document.querySelector('#chat-form').requestSubmit()");await(()->"true".equals(eval("document.querySelectorAll('.chat-answer').length===1 && document.querySelector('#chat-thread').innerText.includes('선 통과')")));capture("web-chat-first-answer");eval("location.reload()");await(()->"true".equals(eval("document.querySelectorAll('.chat-turn').length===1 && !document.querySelector('#chat-send').disabled")));capture("web-chat-reloaded");eval("document.querySelector('#question').value='그 영상은 언제 분석됐어?';document.querySelector('#chat-form').requestSubmit()");await(()->"true".equals(eval("document.querySelectorAll('.chat-answer').length===2 && !document.querySelector('#chat-send').disabled")));capture("web-chat-followup");eval("document.querySelector('#chat-history-button').click()");capture("web-chat-history");eval("document.querySelector('#chat-history-dialog [data-new-chat]').click()");assertEquals("true",eval("document.querySelectorAll('.chat-turn').length===0 && !!document.querySelector('.chat-welcome')"));capture("web-chat-new");eval("document.querySelector('#chat-history-button').click();[...document.querySelectorAll('#chat-mobile-list button')].find(e=>e.innerText.startsWith('몇 번 통과했어?')).click()");await(()->"true".equals(eval("document.querySelectorAll('.chat-answer').length===2")));capture("web-chat-restored");
    }
    private String eval(String js)throws Exception{CountDownLatch latch=new CountDownLatch(1);String[] value={null};getInstrumentation().runOnMainSync(()->web.evaluateJavascript(js,r->{value[0]=r;latch.countDown();}));assertTrue(latch.await(10,TimeUnit.SECONDS));return value[0];}
    private void tapWeb(String selector)throws Exception{
        idle();
        String raw=eval("JSON.stringify((()=>{const r=document.querySelector('"+selector+"').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,viewport:innerWidth};})())");
        JSONObject point=new JSONObject(new JSONArray("["+raw+"]").getString(0));float scale=(float)(web.getWidth()/point.getDouble("viewport")),x=(float)point.getDouble("x")*scale,y=(float)point.getDouble("y")*scale;
        int[] offset=new int[2];getInstrumentation().runOnMainSync(()->{web.requestFocus();web.getLocationOnScreen(offset);});
        long now=SystemClock.uptimeMillis();MotionEvent down=MotionEvent.obtain(now,now,MotionEvent.ACTION_DOWN,x+offset[0],y+offset[1],0),up=MotionEvent.obtain(now,now+80,MotionEvent.ACTION_UP,x+offset[0],y+offset[1],0);getInstrumentation().sendPointerSync(down);getInstrumentation().sendPointerSync(up);down.recycle();up.recycle();
    }
    private void load(String path,String ready)throws Exception{getInstrumentation().runOnMainSync(()->web.loadUrl(config.optString("web_server")+path));await(()->"true".equals(eval("document.readyState==='complete' && ("+ready+")")));idle();}
    public void testWebAllPages()throws Exception{
        getInstrumentation().runOnMainSync(()->{
            FrameLayout host=new FrameLayout(activity);host.setBackgroundColor(Color.WHITE);
            host.setOnApplyWindowInsetsListener((v,insets)->{if(Build.VERSION.SDK_INT>=30){Insets s=insets.getInsets(WindowInsets.Type.systemBars()),ime=insets.getInsets(WindowInsets.Type.ime());v.setPadding(s.left,s.top,s.right,Math.max(s.bottom,ime.bottom));}return insets;});
            web=new WebView(activity);web.setWebViewClient(new WebViewClient());web.getSettings().setJavaScriptEnabled(true);web.getSettings().setDomStorageEnabled(true);host.addView(web);activity.setContentView(host);host.requestApplyInsets();
        });
        CountDownLatch cleared=new CountDownLatch(1);getInstrumentation().runOnMainSync(()->android.webkit.CookieManager.getInstance().removeAllCookies(v->cleared.countDown()));assertTrue(cleared.await(5,TimeUnit.SECONDS));
        load("/","document.querySelector('.operator-entry')!=null");capture("web-dashboard-guest");load("/photos/","document.querySelector('.post-grid article')!=null");capture("web-feed-guest");
        load("/photos/?q=ui-audit-no-match","document.querySelector('.post-grid')!=null");capture("web-empty-search");
        load("/accounts/login/","document.querySelector('[name=username]')!=null");capture("web-login");
        if("after".equals(config.optString("phase"))){eval("document.querySelector('[name=username]').value='ui-invalid';document.querySelector('[name=password]').value='not-the-fixture-password';document.querySelector('.auth-panel form').requestSubmit()");await(()->"true".equals(eval("document.querySelectorAll('.auth-panel .errorlist').length>0")));capture("web-login-error");}
        api.login(config.getString("username"),config.getString("password"));Field cookies=PhotoRepository.class.getDeclaredField("cookies");cookies.setAccessible(true);
        List<HttpCookie> jar=((java.net.CookieManager)cookies.get(api)).getCookieStore().getCookies();CountDownLatch latch=new CountDownLatch(jar.size());
        getInstrumentation().runOnMainSync(()->{for(HttpCookie c:jar)android.webkit.CookieManager.getInstance().setCookie(config.optString("web_server"),c.getName()+"="+c.getValue()+"; Path=/"+(c.isHttpOnly()?"; HttpOnly":""),ok->latch.countDown());});assertTrue(latch.await(5,TimeUnit.SECONDS));
        load("/","document.querySelector('.observation-summary')!=null && document.querySelectorAll('.history-card').length>0");capture("web-dashboard-owner");assertEquals("true",eval("[...document.querySelectorAll('.history-card')].filter(e=>e.getBoundingClientRect().bottom<=innerHeight).length>=2"));load("/people/","document.querySelector('.identity-card')!=null");capture("web-people");webChatFlows();load("/photos/","document.querySelector('.post-grid article')!=null");capture("web-feed-owner");eval("document.querySelector('.search-filter').open=true");capture("web-feed-filters");
        long id=api.getPosts().get(0).id;load("/post/"+id+"/","document.querySelector('article')!=null");capture("web-post-detail");
        load("/post/new/","!!document.querySelector('#photo-input')");capture("web-photo-picker");
        load("/post/"+id+"/edit/","document.querySelector('[data-pane=review]')?.hidden===false");capture("web-story");
        eval("document.querySelector('#tab-tags').click()");capture("web-tags");eval("document.querySelector('#tab-text').click()");capture("web-ocr");
        if("after".equals(config.optString("phase"))){
            eval("document.querySelector('#tab-tags').click()");double initial=Double.parseDouble(eval("innerHeight"));tapWeb("#photo-tags");await(()->Double.parseDouble(eval("innerHeight"))<initial-80);capture("web-tags-keyboard");
            assertEquals("true",eval("(()=>{const e=document.querySelector('#publish-photo'),r=e.getBoundingClientRect();if(!(r.top>=0&&r.bottom<=innerHeight+2))return false;return [[(r.left+r.right)/2,r.top+4],[(r.left+r.right)/2,r.bottom-4],[r.left+4,(r.top+r.bottom)/2],[r.right-4,(r.top+r.bottom)/2]].every(([x,y])=>{const target=document.elementFromPoint(x,y);return target===e||e.contains(target);})})()"));
            getInstrumentation().runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(web.getWindowToken(),0));eval("document.activeElement.blur()");await(()->Double.parseDouble(eval("innerHeight"))>=initial-2);
        }
        eval("document.querySelector('#back-to-mosaic').click()");capture("web-mosaic");
        load("/detections/","document.querySelectorAll('.history-card').length>0");capture("web-primary-records");
        assertEquals("true",eval("[...document.querySelectorAll('.section-nav a')].map(a=>a.textContent).join('|')==='관측 기록|인물 확인|AI 질문' && document.querySelector('.section-nav [aria-current]').textContent==='관측 기록' && !document.querySelector('.post-grid')"));
        load("/people/showcase-v2-c/","document.querySelector('.person-timeline')!=null");capture("web-person-timeline");eval("document.querySelector('#review').open=true");capture("web-person-comparison");load("/history/","document.querySelectorAll('.history-card').length>0");capture("web-history");
        eval("document.querySelector('#history-filter details').open=true");capture("web-history-filters");
        eval("document.querySelector('#history-filter details').open=false;document.querySelector('.history-card').click()");capture("web-history-detail");eval("document.querySelector('#detail-close').click()");
        eval("document.querySelector('#question-panel').open=true;document.querySelector('#question').value='몇 번 통과했어?'");capture("web-question");
        eval("document.querySelector('[name=generate]').checked=true;document.querySelector('#history-question').requestSubmit()");
        await(()->"true".equals(eval("document.querySelector('#history-answer').innerText.includes('선 통과')")));capture("web-answer");
        eval("document.querySelector('#history-filter [name=start]').value='2050-01-01';document.querySelector('#history-filter [name=end]').value='2050-01-01';document.querySelector('#history-filter').requestSubmit()");
        await(()->"true".equals(eval("document.querySelectorAll('.history-card').length===0")));capture("web-history-empty");
        getInstrumentation().runOnMainSync(()->{web.destroy();web=null;});
    }
}
