package com.haddol7.photoviewer.ui;

import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.test.ActivityInstrumentationTestCase2;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebView;
import android.widget.*;
import com.haddol7.photoviewer.MainActivity;
import com.haddol7.photoviewer.data.PhotoRepository;
import org.json.*;
import java.io.*;
import java.net.HttpCookie;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Uses credentials for a disposable local fixture, never production credentials. */
@SuppressWarnings("deprecation")
public final class HistorySyncTest extends ActivityInstrumentationTestCase2<MainActivity> {
    private JSONObject config;
    private String previous;
    public HistorySyncTest(){super(MainActivity.class);}
    @Override protected void setUp() throws Exception {
        super.setUp();
        File file=new File(getInstrumentation().getTargetContext().getExternalFilesDir(null),"history-test-config.json");
        try(FileInputStream in=new FileInputStream(file)){config=new JSONObject(new String(in.readAllBytes(),StandardCharsets.UTF_8));}
        assertTrue("Local test endpoint only",config.getString("server").startsWith("http://10.0.2.2:"));
        SharedPreferences prefs=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);
        previous=prefs.getString("origin",null);prefs.edit().putString("origin",config.getString("server")).commit();
    }
    @Override protected void tearDown() throws Exception {
        SharedPreferences.Editor edit=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0).edit();
        if(previous==null)edit.remove("origin");else edit.putString("origin",previous);edit.commit();super.tearDown();
    }
    private TextView text(View view,String value){
        if(view instanceof TextView&&value.equals(((TextView)view).getText().toString()))return (TextView)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){TextView found=text(((ViewGroup)view).getChildAt(i),value);if(found!=null)return found;}
        return null;
    }
    private int photos(View view){int n=view instanceof ImageView&&((ImageView)view).getDrawable()!=null?1:0;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)n+=photos(((ViewGroup)view).getChildAt(i));return n;}
    private interface Condition{boolean ready()throws Exception;}
    private void waitFor(Condition condition)throws Exception{
        long deadline=android.os.SystemClock.elapsedRealtime()+45000;
        while(android.os.SystemClock.elapsedRealtime()<deadline){if(condition.ready())return;Thread.sleep(150);}
        fail("History UI did not become ready");
    }
    private void capture(String name)throws Exception{
        Thread.sleep(700);
        getInstrumentation().getUiAutomation().waitForIdle(400,3000);
        Bitmap image=getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
        File directory=new File(getInstrumentation().getTargetContext().getExternalFilesDir(null),"evidence");
        assertTrue(directory.isDirectory()||directory.mkdirs());
        try(FileOutputStream out=new FileOutputStream(new File(directory,name))){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,out));}
        image.recycle();
    }
    public void testNativeHistoryAndGroundedQuestion()throws Exception{
        MainActivity activity=getActivity();
        java.lang.reflect.Field field=MainActivity.class.getDeclaredField("api");field.setAccessible(true);
        PhotoRepository api=(PhotoRepository)field.get(activity);
        // Let the initial anonymous list finish before signing this isolated repository in.
        Thread.sleep(1500);
        api.login(config.getString("username"),config.getString("password"));
        getInstrumentation().runOnMainSync(()->text(activity.getWindow().getDecorView(),"관측 기록").performClick());
        waitFor(()->{boolean[] ok={false};getInstrumentation().runOnMainSync(()->ok[0]=photos(activity.getWindow().getDecorView())>=2);return ok[0];});
        capture("history-native-list.png");
        JSONObject answer=api.historyQuestion(new JSONObject().put("question","몇 번 통과했어?"));
        assertEquals(config.getInt("expected_passages"),answer.getJSONObject("facts").getInt("passages"));
        assertTrue(answer.getJSONArray("evidence").length()>0);
        JSONObject conversation=api.createConversation();
        JSONObject saved=api.historyQuestion(new JSONObject().put("question","몇 번 통과했어?").put("date_basis","processed")
            .put("conversation_id",conversation.getString("id")).put("request_id",java.util.UUID.randomUUID().toString())
            .put("generate",config.optBoolean("verify_llm")).put("semantic",false));
        if(config.optBoolean("verify_llm"))assertEquals("generated",saved.getJSONObject("llm").getString("status"));
        getInstrumentation().runOnMainSync(()->text(activity.getWindow().getDecorView(),"AI 질문").performClick());
        waitFor(()->!getInstrumentation().getUiAutomation().getRootInActiveWindow().findAccessibilityNodeInfosByText("선 통과").isEmpty());
        capture("history-native-question.png");
    }
    private EditText findQuestion(View view){
        if(view instanceof EditText&&"언제 나타났어?".contentEquals(((EditText)view).getHint()))return (EditText)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){EditText found=findQuestion(((ViewGroup)view).getChildAt(i));if(found!=null)return found;}
        return null;
    }
    private android.view.accessibility.AccessibilityNodeInfo activeQuestion(android.view.accessibility.AccessibilityNodeInfo node){
        if(node==null)return null;if("android.widget.EditText".contentEquals(node.getClassName())&&"언제 나타났어?".equals(String.valueOf(node.getHintText())))return node;
        for(int i=0;i<node.getChildCount();i++){android.view.accessibility.AccessibilityNodeInfo found=activeQuestion(node.getChild(i));if(found!=null)return found;}return null;
    }
    private String eval(WebView web,String expression)throws Exception{
        CountDownLatch latch=new CountDownLatch(1);String[] value={null};
        getInstrumentation().runOnMainSync(()->web.evaluateJavascript(expression,result->{value[0]=result;latch.countDown();}));
        assertTrue("WebView evaluation timed out",latch.await(10,TimeUnit.SECONDS));return value[0];
    }
    public void testActualAndroidMobileWebHistory()throws Exception{
        MainActivity activity=getActivity();PhotoRepository api=new PhotoRepository(config.getString("server"));
        api.login(config.getString("username"),config.getString("password"));
        java.lang.reflect.Field field=PhotoRepository.class.getDeclaredField("cookies");field.setAccessible(true);
        java.net.CookieManager jar=(java.net.CookieManager)field.get(api);
        CountDownLatch cookieLatch=new CountDownLatch(jar.getCookieStore().getCookies().size());
        getInstrumentation().runOnMainSync(()->{
            android.webkit.CookieManager manager=android.webkit.CookieManager.getInstance();
            manager.setAcceptCookie(true);
            for(HttpCookie cookie:jar.getCookieStore().getCookies())manager.setCookie(config.optString("server"),
                cookie.getName()+"="+cookie.getValue()+"; Path=/"+(cookie.isHttpOnly()?"; HttpOnly":""),result->cookieLatch.countDown());
        });
        assertTrue(cookieLatch.await(10,TimeUnit.SECONDS));
        WebView[] holder={null};
        getInstrumentation().runOnMainSync(()->{WebView web=new WebView(activity);web.getSettings().setJavaScriptEnabled(true);
            if(android.os.Build.VERSION.SDK_INT>=30)activity.getWindow().setDecorFitsSystemWindows(true);
            web.getSettings().setDomStorageEnabled(true);holder[0]=web;activity.setContentView(web);web.loadUrl(config.optString("server")+"history/");});
        WebView web=holder[0];
        waitFor(()->"true".equals(eval(web,"document.querySelectorAll('.history-card').length>=2 && [...document.querySelectorAll('.history-card img')].filter(i=>i.complete&&i.naturalWidth>0).length>=2")));
        assertEquals("false",eval(web,"document.documentElement.scrollWidth>innerWidth+1"));
        assertEquals("true",eval(web,"[...document.querySelectorAll('.history-card')].filter(e=>e.getBoundingClientRect().bottom<innerHeight).length>=2"));
        capture("history-mobile-web-list.png");
        eval(web,"document.querySelector('.history-card').click()");
        assertEquals("true",eval(web,"document.querySelector('#history-detail').open && document.querySelector('#detail-confirm').getBoundingClientRect().bottom<=innerHeight"));
        capture("history-mobile-web-detail.png");
        eval(web,"document.querySelector('#detail-close').click();document.querySelector('#question-panel').open=true;document.querySelector('#question').value='몇 번 통과했어?';document.querySelector('[name=generate]').checked="+config.optBoolean("verify_llm")+";document.querySelector('#history-question').requestSubmit()");
        waitFor(()->"true".equals(eval(web,"document.querySelector('#history-answer').innerText.includes('선 통과 "+config.getInt("expected_passages")+"건')")));
        assertEquals("true",eval(web,"document.querySelectorAll('.evidence-links button').length>0"));
        if(config.optBoolean("verify_llm")){
            assertEquals("true",eval(web,"document.querySelector('#history-answer').innerText.includes('AI 설명') && !document.querySelector('#history-answer').innerText.includes('받지 못했습니다')"));
        }
        capture("history-mobile-web-question.png");
        getInstrumentation().runOnMainSync(()->{web.stopLoading();web.destroy();});
    }
}
