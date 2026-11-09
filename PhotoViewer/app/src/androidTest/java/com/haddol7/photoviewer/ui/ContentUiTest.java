package com.haddol7.photoviewer.ui;

import android.app.Instrumentation;
import android.content.*;
import android.graphics.*;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.test.ActivityInstrumentationTestCase2;
import android.view.*;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import com.haddol7.photoviewer.MainActivity;
import com.haddol7.photoviewer.data.PhotoRepository;
import com.haddol7.photoviewer.model.PhotoPost;
import org.json.JSONObject;
import java.io.*;
import java.util.*;

/** Actual new UI -> OS document picker -> bundled ML -> live WSL HTTP -> search. */
@SuppressWarnings("deprecation")
public final class ContentUiTest extends ActivityInstrumentationTestCase2<MainActivity> {
    public ContentUiTest(){super(MainActivity.class);}
    private MainActivity activity;
    private String photoName;
    private String previousOrigin;
    @Override protected void setUp() throws Exception {
        super.setUp();
        Bundle args=((android.test.InstrumentationTestRunner)getInstrumentation()).getArguments();
        android.content.SharedPreferences prefs=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);
        previousOrigin=prefs.getString("origin",null);
        prefs.edit().putString("origin",args.getString("server","http://10.0.2.2:8000/")).commit();
    }
    @Override protected void tearDown() throws Exception {
        android.content.SharedPreferences.Editor edit=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0).edit();
        if(previousOrigin==null)edit.remove("origin");else edit.putString("origin",previousOrigin);
        edit.commit();super.tearDown();
    }
    private interface Check{boolean ok()throws Exception;}
    private void await(Check check,String failure)throws Exception{long until=android.os.SystemClock.elapsedRealtime()+60000;while(android.os.SystemClock.elapsedRealtime()<until){if(check.ok())return;Thread.sleep(100);}fail(failure);}
    private AccessibilityNodeInfo root(){return getInstrumentation().getUiAutomation().getRootInActiveWindow();}
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node,String value,boolean edit){
        if(node==null)return null;boolean text=value.contentEquals(node.getText()==null?"":node.getText()),description=value.contentEquals(node.getContentDescription()==null?"":node.getContentDescription()),hint=android.os.Build.VERSION.SDK_INT>=26&&value.contentEquals(node.getHintText()==null?"":node.getHintText());
        if((text||description||hint)&&(!edit||"android.widget.EditText".contentEquals(node.getClassName())))return node;
        for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=find(node.getChild(i),value,edit);if(found!=null)return found;}return null;
    }
    private boolean contains(AccessibilityNodeInfo node,String text){if(node==null)return false;if(!"android.widget.EditText".contentEquals(node.getClassName())&&node.getText()!=null&&node.getText().toString().contains(text))return true;for(int i=0;i<node.getChildCount();i++)if(contains(node.getChild(i),text))return true;return false;}
    private AccessibilityNodeInfo scrollNode(AccessibilityNodeInfo node){if(node==null)return null;if(node.isScrollable())return node;for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=scrollNode(node.getChild(i));if(found!=null)return found;}return null;}
    private AccessibilityNodeInfo actionNode(AccessibilityNodeInfo node,String label){if(node==null)return null;if(label.contentEquals(node.getText()==null?"":node.getText())&&node.isClickable())return node;for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=actionNode(node.getChild(i),label);if(found!=null)return found;}return null;}
    private void click(String label)throws Exception{
        for(int attempt=0;attempt<20;attempt++){AccessibilityNodeInfo node=actionNode(root(),label);if(node!=null&&node.performAction(AccessibilityNodeInfo.ACTION_CLICK))return;
            AccessibilityNodeInfo scroll=scrollNode(root());if(scroll!=null)scroll.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);Thread.sleep(150);
        }fail("화면의 버튼을 누르지 못했습니다: "+label);
    }
    private void enter(String hint,String text)throws Exception{await(()->find(root(),hint,true)!=null,"입력란 없음: "+hint);Bundle args=new Bundle();args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,text);assertTrue(find(root(),hint,true).performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args));}
    private View nativeView(View view,String description){if(description.contentEquals(view.getContentDescription()==null?"":view.getContentDescription()))return view;if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){View found=nativeView(((ViewGroup)view).getChildAt(i),description);if(found!=null)return found;}return null;}
    private void capture(String name)throws Exception{
        await(()->root()!=null&&activity.getPackageName().contentEquals(root().getPackageName()),"앱 화면으로 복귀하지 못함");getInstrumentation().getUiAutomation().waitForIdle(500,5000);Bitmap bitmap=getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(bitmap);File folder=new File(activity.getExternalFilesDir(null),"evidence");assertTrue(folder.isDirectory()||folder.mkdirs());try(FileOutputStream out=new FileOutputStream(new File(folder,name))){assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,out));}bitmap.recycle();
    }
    private void fixedEditor(boolean photoVisible)throws Exception{
        getInstrumentation().getUiAutomation().waitForIdle(500,5000);
        getInstrumentation().waitForIdleSync();
        int[] measured=new int[6];
        getInstrumentation().runOnMainSync(()->{
            View decor=activity.getWindow().getDecorView(),done=nativeView(decor,"고정 완료 버튼"),host=nativeView(decor,"고정 편집 화면"),photo=nativeView(decor,"편집 사진 미리보기");
            assertNotNull(host);assertNotNull(done);Rect visible=new Rect();decor.getWindowVisibleDisplayFrame(visible);int[] location=new int[2];done.getLocationOnScreen(location);
            measured[0]=location[1];measured[1]=location[1]+done.getHeight();measured[2]=visible.top;measured[3]=visible.bottom;measured[4]=done.getHeight();measured[5]=photo==null?0:photo.getHeight();
        });
        assertTrue("완료 버튼이 화면 아래로 밀렸습니다: "+Arrays.toString(measured),measured[0]>=measured[2]&&measured[1]<=measured[3]+2);
        assertTrue("완료 버튼 터치 영역이 너무 작습니다.",measured[4]>=Math.round(44*activity.getResources().getDisplayMetrics().density));
        if(photoVisible)assertTrue("사진이 보이지 않습니다.",measured[5]>=Math.round(78*activity.getResources().getDisplayMetrics().density));
    }
    private Uri seedPhoto()throws Exception{
        photoName="content-ui-"+UUID.randomUUID().toString().substring(0,8)+".png";ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,photoName);values.put(MediaStore.Images.Media.MIME_TYPE,"image/png");if(android.os.Build.VERSION.SDK_INT>=29){values.put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/PhotoBlogTests");values.put(MediaStore.Images.Media.IS_PENDING,1);}Uri uri=activity.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);assertNotNull(uri);
        Bitmap bitmap=Bitmap.createBitmap(1600,1200,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(bitmap);canvas.drawColor(Color.WHITE);try(InputStream in=getInstrumentation().getContext().getAssets().open("portrait.jpg")){Bitmap face=BitmapFactory.decodeStream(in);canvas.drawBitmap(face,null,new Rect(0,0,700,900),null);face.recycle();}Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setTypeface(Typeface.create("sans-serif",Typeface.BOLD));paint.setColor(Color.BLACK);paint.setTextSize(120);canvas.drawText("바다라멘",780,250,paint);canvas.drawText("CAFE MENU",760,500,paint);paint.setColor(Color.rgb(210,130,80));canvas.drawRect(850,650,1450,900,paint);
        try(OutputStream out=activity.getContentResolver().openOutputStream(uri)){assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,out));}bitmap.recycle();if(android.os.Build.VERSION.SDK_INT>=29){ContentValues ready=new ContentValues();ready.put(MediaStore.Images.Media.IS_PENDING,0);activity.getContentResolver().update(uri,ready,null,null);}return uri;
    }
    private AccessibilityNodeInfo document(AccessibilityNodeInfo node){if(node==null)return null;if((node.getText()!=null&&node.getText().toString().contains(photoName))||(node.getContentDescription()!=null&&node.getContentDescription().toString().contains(photoName)))return node;for(int i=0;i<node.getChildCount();i++){AccessibilityNodeInfo found=document(node.getChild(i));if(found!=null)return found;}return null;}
    private void pickDocument()throws Exception{
        await(()->document(root())!=null,"OS 문서 선택기에 테스트 사진이 없습니다.");
        for(int i=0;i<4;i++){if(contains(root(),"게시 사본에 적용"))return;getInstrumentation().getUiAutomation().waitForIdle(500,5000);AccessibilityNodeInfo node=document(root());if(node==null)break;Rect bounds=new Rect();node.getBoundsInScreen(bounds);assertFalse(bounds.isEmpty());try(android.os.ParcelFileDescriptor ignored=getInstrumentation().getUiAutomation().executeShellCommand("input touchscreen tap "+(bounds.left+bounds.width()/4)+" "+(bounds.top+bounds.height()*3/4))){Thread.sleep(700);}}
        await(()->contains(root(),"게시 사본에 적용"),"OS에서 선택한 사진이 얼굴 확인 화면으로 전달되지 않았습니다.");
    }
    public void testNewComposerPickerMosaicCorrectionRotationUploadAndSearch()throws Exception{
        activity=getActivity();await(()->contains(root(),"동기화 완료"),"초기 서버 동기화 실패");capture("content-start.png");
        Bundle args=((android.test.InstrumentationTestRunner)getInstrumentation()).getArguments();PhotoRepository owner=new PhotoRepository(args.getString("server","http://10.0.2.2:8000/"));owner.me();String user=args.getString("owner"),password=args.getString("password");assertNotNull("Provision isolated test owner",user);assertTrue(owner.login(user,password).canPublish);
        click("계정·설정");click("운영자 로그인");enter("사용자 이름",user);enter("비밀번호",password);click("로그인");await(()->find(root(),"비밀번호",true)==null&&contains(root(),"동기화 완료"),"새 계정 로그인 실패");
        seedPhoto();click("계정·설정");click("사진 추가");String title="후기-"+UUID.randomUUID().toString().substring(0,8);enter("제목",title);enter("기록 설명","제목과 본문에는 가게 이름을 적지 않았습니다.");fixedEditor(true);click("사진 파일 선택");pickDocument();fixedEditor(false);capture("content-face-preview.png");
        click("게시 사본에 적용");await(()->contains(root(),"추천 테마:")||contains(root(),"분류 추천 실패")||contains(root(),"테마 확인 필요"),"공개 사본 내용 분석이 끝나지 않음");click("태그");fixedEditor(true);capture("content-tags.png");
        getInstrumentation().runOnMainSync(()->{Spinner spinner=(Spinner)nativeView(activity.getWindow().getDecorView(),"대표 테마");assertNotNull(spinner);spinner.setSelection(1);});enter("태그 추가","후기,라멘");click("추가");await(()->contains(root(),"✓ 후기"),"사용자 태그 추가 실패");click("✓ 후기");await(()->!contains(root(),"✓ 후기"),"태그 선택 해제 실패");enter("태그 추가","후기");click("추가");
        click("검색 문구");click("모두 포함");fixedEditor(true);capture("content-classification-ocr.png");
        getInstrumentation().runOnMainSync(()->{EditText field=(EditText)nativeView(activity.getWindow().getDecorView(),"선택한 문구 교정");field.requestFocus();((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).showSoftInput(field,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);});
        await(()->{View decor=activity.getWindow().getDecorView();Rect visible=new Rect();decor.getWindowVisibleDisplayFrame(visible);return decor.getHeight()-visible.bottom>100;},"키보드가 열리지 않았습니다.");capture("content-ocr-keyboard.png");fixedEditor(false);
        getInstrumentation().runOnMainSync(()->((android.view.inputmethod.InputMethodManager)activity.getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(activity.getWindow().getDecorView().getWindowToken(),0));
        click("확인 완료");Instrumentation.ActivityMonitor monitor=getInstrumentation().addMonitor(MainActivity.class.getName(),null,false);getInstrumentation().runOnMainSync(activity::recreate);MainActivity restored=(MainActivity)getInstrumentation().waitForMonitorWithTimeout(monitor,15000);getInstrumentation().removeMonitor(monitor);assertNotNull("작성 화면 재생성 실패",restored);activity=restored;await(()->find(root(),"제목",true)!=null,"작성 내용 복원 실패");assertEquals(title,find(root(),"제목",true).getText().toString());
        getInstrumentation().runOnMainSync(()->{ViewGroup host=activity.findViewById(android.R.id.content);assertTrue("재생성 뒤 화면 여백이 소실되었습니다.",host.getChildAt(0).getPaddingLeft()>=Math.round(18*activity.getResources().getDisplayMetrics().density));});
        click("게시");await(()->contains(root(),"사진 상세"),"새 작성 화면의 실제 업로드 실패");capture("content-published.png");
        PhotoPost posted=null;for(PhotoPost post:owner.getPosts())if(post.title.equals(title))posted=post;assertNotNull(posted);JSONObject metadata=owner.content(posted.id);assertEquals("food",metadata.getString("theme"));assertTrue(metadata.getJSONArray("lines").length()>0);
        assertTrue("실제 사진의 가게 글자를 OCR로 찾지 못했습니다.",owner.browse("바다라멘","food","후기",true,null).getJSONArray("results").length()>0);
        click("목록");enter("사진 속 문구 검색","바다라멘");await(()->contains(root(),"사진 속 글자:"),"사진 속 문구 검색 결과 표시 실패");capture("content-search-results.png");click("기록 열기");await(()->contains(root(),"일치 위치:"),"일치 영역으로 이동할 행동이 없음");capture("content-match-highlight.png");
        assertFalse("전체 문구 목록을 다시 노출했습니다.",contains(root(),"사진 속 문구 전체 보기"));
    }
}
