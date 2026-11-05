package com.haddol7.photoviewer.ui;

import android.content.*;
import android.graphics.Bitmap;
import android.test.ActivityInstrumentationTestCase2;
import android.view.*;
import android.widget.*;
import com.haddol7.photoviewer.MainActivity;
import com.haddol7.photoviewer.content.PhotoPipeline;
import com.haddol7.photoviewer.data.PhotoRepository;
import com.haddol7.photoviewer.model.PhotoPost;
import org.json.*;
import java.io.*;
import java.util.*;

/** Production verification is strictly read-only; mutation suites use an isolated WSL server. */
@SuppressWarnings("deprecation")
public final class CloudSyncTest extends ActivityInstrumentationTestCase2<MainActivity>{
    public CloudSyncTest(){super(MainActivity.class);}
    private String previous;
    @Override protected void setUp()throws Exception{super.setUp();SharedPreferences p=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);previous=p.getString("origin",null);p.edit().putString("origin",MainActivity.DEFAULT_SERVER).commit();}
    @Override protected void tearDown()throws Exception{SharedPreferences.Editor e=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0).edit();if(previous==null)e.remove("origin");else e.putString("origin",previous);e.commit();super.tearDown();}
    private boolean text(View v,String value){if(v instanceof TextView&&((TextView)v).getText().toString().contains(value))return true;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)if(text(((ViewGroup)v).getChildAt(i),value))return true;return false;}
    private int photos(View v){int n=v instanceof ImageView&&((ImageView)v).getDrawable()!=null?1:0;if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)n+=photos(((ViewGroup)v).getChildAt(i));return n;}
    public void testDeployedServerAndNativeList()throws Exception{
        PhotoRepository api=new PhotoRepository(MainActivity.DEFAULT_SERVER);assertFalse(api.me().canPublish);List<PhotoPost> posts=api.getPosts();assertFalse("No public photo available for synchronization",posts.isEmpty());
        PhotoPost post=posts.get(0);byte[] bytes=api.downloadPhoto(post.imageUrl);JSONObject content=api.content(post.id);if(!content.isNull("image_sha256"))assertEquals(content.getString("image_sha256"),PhotoPipeline.sha256(bytes));
        int expected=Math.min(20,posts.size());for(int i=1;i<expected;i++){PhotoPost p=posts.get(i);byte[] image=api.downloadPhoto(p.imageUrl);JSONObject c=api.content(p.id);if(!c.isNull("image_sha256"))assertEquals(c.getString("image_sha256"),PhotoPipeline.sha256(image));}
        MainActivity activity=getActivity();long deadline=android.os.SystemClock.elapsedRealtime()+60000;boolean[] ready={false};while(android.os.SystemClock.elapsedRealtime()<deadline){getInstrumentation().runOnMainSync(()->{View v=activity.getWindow().getDecorView();ready[0]=text(v,"동기화 완료")&&text(v,post.title)&&photos(v)>=expected;});if(ready[0])break;Thread.sleep(100);}assertTrue("Production photos did not all appear in the native UI",ready[0]);
        File folder=new File(activity.getExternalFilesDir(null),"evidence");assertTrue(folder.isDirectory()||folder.mkdirs());getInstrumentation().getUiAutomation().waitForIdle(500,5000);Bitmap image=getInstrumentation().getUiAutomation().takeScreenshot();try(FileOutputStream out=new FileOutputStream(new File(folder,"content-cloud-sync.png"))){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,out));}image.recycle();
        JSONObject result=new JSONObject().put("url",MainActivity.DEFAULT_SERVER).put("read_only",true).put("posts",posts.size()).put("image_sha256",PhotoPipeline.sha256(bytes)).put("native_image_visible",true).put("images_hash_checked",expected).put("images_rendered",expected);
        try(FileOutputStream out=new FileOutputStream(new File(folder,"cloud-sync.json"))){out.write(result.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));}
    }
}
