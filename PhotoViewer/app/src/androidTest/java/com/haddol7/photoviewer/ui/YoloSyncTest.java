package com.haddol7.photoviewer.ui;

import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.test.ActivityInstrumentationTestCase2;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;
import com.haddol7.photoviewer.MainActivity;
import com.haddol7.photoviewer.content.PhotoPipeline;
import com.haddol7.photoviewer.data.PhotoRepository;
import com.haddol7.photoviewer.model.PhotoPost;
import java.io.File;
import java.io.FileOutputStream;
import org.json.JSONObject;

/** Read a specific real YOLO upload, verify bytes, then capture the actual native list and detail. */
@SuppressWarnings("deprecation")
public final class YoloSyncTest extends ActivityInstrumentationTestCase2<MainActivity> {
    public YoloSyncTest(){super(MainActivity.class);}
    private String previous,server;
    private Bundle args;
    @Override protected void setUp() throws Exception {
        super.setUp();args=((android.test.InstrumentationTestRunner)getInstrumentation()).getArguments();
        server=args.getString("server","http://10.0.2.2:8020/");
        SharedPreferences prefs=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);
        previous=prefs.getString("origin",null);prefs.edit().putString("origin",server).commit();
    }
    @Override protected void tearDown() throws Exception {
        SharedPreferences.Editor edit=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0).edit();
        if(previous==null)edit.remove("origin");else edit.putString("origin",previous);edit.commit();super.tearDown();
    }
    private TextView text(View view,String value){
        if(view instanceof TextView&&((TextView)view).getText().toString().contains(value))return (TextView)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){TextView found=text(((ViewGroup)view).getChildAt(i),value);if(found!=null)return found;}
        return null;
    }
    private int photos(View view){int count=view instanceof ImageView&&((ImageView)view).getDrawable()!=null?1:0;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)count+=photos(((ViewGroup)view).getChildAt(i));return count;}
    private void capture(MainActivity activity,String filename)throws Exception{
        getInstrumentation().getUiAutomation().waitForIdle(500,5000);
        Bitmap image=getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
        File folder=new File(activity.getExternalFilesDir(null),"evidence");assertTrue(folder.isDirectory()||folder.mkdirs());
        try(FileOutputStream out=new FileOutputStream(new File(folder,filename))){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,out));}image.recycle();
    }
    public void testYoloPhotoAppearsInNativeListAndDetail()throws Exception{
        long id=Long.parseLong(args.getString("post_id"));String expected=args.getString("image_sha256");assertNotNull(expected);
        PhotoRepository api=new PhotoRepository(server);PhotoPost selected=null;
        for(PhotoPost post:api.getPosts())if(post.id==id)selected=post;
        assertNotNull("Expected YOLO post missing",selected);assertTrue(selected.title.startsWith("YOLO:"));
        assertEquals(expected,PhotoPipeline.sha256(api.downloadPhoto(selected.imageUrl)));
        MainActivity activity=getActivity();java.lang.reflect.Method listing=MainActivity.class.getDeclaredMethod("showList");listing.setAccessible(true);getInstrumentation().runOnMainSync(()->{try{listing.invoke(activity);}catch(Exception e){throw new RuntimeException(e);}});PhotoPost post=selected;boolean[] ready={false};
        long until=android.os.SystemClock.elapsedRealtime()+60000;
        while(android.os.SystemClock.elapsedRealtime()<until){
            getInstrumentation().runOnMainSync(()->{View decor=activity.getWindow().getDecorView();ready[0]=text(decor,"동기화 완료")!=null&&text(decor,post.title)!=null&&photos(decor)>0;});
            if(ready[0])break;Thread.sleep(100);
        }
        assertTrue("YOLO photo did not render in the native list",ready[0]);capture(activity,"yolo-native-list.png");
        getInstrumentation().runOnMainSync(()->assertTrue(text(activity.getWindow().getDecorView(),post.title).performClick()));
        ready[0]=false;until=android.os.SystemClock.elapsedRealtime()+30000;
        while(android.os.SystemClock.elapsedRealtime()<until){
            getInstrumentation().runOnMainSync(()->ready[0]=text(activity.getWindow().getDecorView(),"사진 상세")!=null&&text(activity.getWindow().getDecorView(),post.title)!=null);
            if(ready[0])break;Thread.sleep(100);
        }
        assertTrue("YOLO photo detail did not open",ready[0]);capture(activity,"yolo-native-detail.png");
        JSONObject record=new JSONObject().put("server",server).put("post_id",id).put("image_sha256",expected)
            .put("list_visible",true).put("detail_visible",true).put("read_only",true);
        try(FileOutputStream out=new FileOutputStream(new File(activity.getExternalFilesDir(null),"evidence/yolo-sync.json"))){out.write(record.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));}
    }
}
