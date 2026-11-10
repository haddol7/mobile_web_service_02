package com.haddol7.photoviewer.ui;

import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.os.SystemClock;
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
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import org.json.JSONArray;
import org.json.JSONObject;

/** Read the real webcam uploads with a shared request gate; never create or edit server data. */
@SuppressWarnings("deprecation")
public final class SelfWebcamSyncTest extends ActivityInstrumentationTestCase2<MainActivity> {
    public SelfWebcamSyncTest() { super(MainActivity.class); }
    private String previous;
    private final List<JSONObject> requests = new ArrayList<>();
    private long nextRequest;
    private synchronized void gate(String method, java.net.URI uri) {
        assertEquals("GET", method);
        assertEquals("daejinha.pythonanywhere.com", uri.getHost());
        SystemClock.sleep(Math.max(0, nextRequest - SystemClock.elapsedRealtime()));
        long now = SystemClock.elapsedRealtime();
        nextRequest = now + 5200;
        try { requests.add(new JSONObject().put("method", method).put("path", uri.getPath()).put("started_elapsed_ms", now)); }
        catch (Exception error) { throw new AssertionError(error); }
    }
    @Override protected void setUp() throws Exception {
        super.setUp();
        SharedPreferences prefs=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0);
        previous=prefs.getString("origin",null);
        // Startup uses an unreachable loopback origin. All real production calls use the gated repository below.
        prefs.edit().putString("origin","http://127.0.0.1:9/").commit();
    }
    @Override protected void tearDown() throws Exception {
        SharedPreferences.Editor edit=getInstrumentation().getTargetContext().getSharedPreferences("MainActivity",0).edit();
        if(previous==null)edit.remove("origin");else edit.putString("origin",previous);edit.commit();super.tearDown();
    }
    private void field(Object object,String name,Object value)throws Exception {
        Field f=MainActivity.class.getDeclaredField(name);f.setAccessible(true);f.set(object,value);
    }
    private String status(MainActivity activity)throws Exception {
        Field f=MainActivity.class.getDeclaredField("status");f.setAccessible(true);return ((TextView)f.get(activity)).getText().toString();
    }
    private int photos(View view) {
        int count=view instanceof ImageView && ((ImageView)view).getDrawable()!=null ? 1:0;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)count+=photos(((ViewGroup)view).getChildAt(i));
        return count;
    }
    private void ready(MainActivity activity,String expected,int minPhotos,long timeout)throws Exception {
        long until=SystemClock.elapsedRealtime()+timeout;boolean[] visible={false};
        while(SystemClock.elapsedRealtime()<until){
            getInstrumentation().runOnMainSync(()->{try{visible[0]=status(activity).contains(expected)&&photos(activity.getWindow().getDecorView())>=minPhotos;}catch(Exception error){throw new RuntimeException(error);}});
            if(visible[0])return;SystemClock.sleep(250);
        }
        fail("Native state did not render: "+expected);
    }
    private void capture(MainActivity activity,String name)throws Exception {
        getInstrumentation().getUiAutomation().waitForIdle(500,5000);
        Bitmap image=getInstrumentation().getUiAutomation().takeScreenshot();assertNotNull(image);
        File dir=new File(activity.getExternalFilesDir(null),"evidence/self-webcam");assertTrue(dir.isDirectory()||dir.mkdirs());
        try(FileOutputStream out=new FileOutputStream(new File(dir,name))){assertTrue(image.compress(Bitmap.CompressFormat.PNG,100,out));}image.recycle();
    }
    public void testRealWebcamPostsInNativeListAndDetail()throws Exception {
        String origin="https://daejinha.pythonanywhere.com/";
        PhotoRepository repository=new PhotoRepository(origin,this::gate);
        List<PhotoPost> all=repository.getPosts();PhotoPost first=null,reentry=null;
        for(PhotoPost post:all){if(post.id==9)first=post;if(post.id==14)reentry=post;}
        assertNotNull(first);assertNotNull(reentry);
        assertEquals("65c4316956c9273fc36a71567a8c8c394d74a3256c62de6bea3d821db9506d0d",PhotoPipeline.sha256(repository.downloadPhoto(first.imageUrl)));
        assertEquals("3487bf4c5e8a3a6e166e77d0bb9cc60d0e1fa70aa6656b930559c2dc847e0947",PhotoPipeline.sha256(repository.downloadPhoto(reentry.imageUrl)));
        MainActivity activity=getActivity();SystemClock.sleep(500);
        Method listing=MainActivity.class.getDeclaredMethod("showList");listing.setAccessible(true);
        getInstrumentation().runOnMainSync(()->{try{field(activity,"api",repository);field(activity,"origin",origin);listing.invoke(activity);}catch(Exception e){throw new RuntimeException(e);}});
        ready(activity,"동기화 완료",all.size(),200000);capture(activity,"native-list.png");
        Method detail=MainActivity.class.getDeclaredMethod("openDetail",PhotoPost.class,JSONObject.class);detail.setAccessible(true);
        for(PhotoPost post:new PhotoPost[]{first,reentry}){
            getInstrumentation().runOnMainSync(()->{try{detail.invoke(activity,post,null);}catch(Exception e){throw new RuntimeException(e);}});
            ready(activity,"사진 상세",0,60000);capture(activity,"native-post-"+post.id+".png");
        }
        long minimum=Long.MAX_VALUE;
        for(int i=1;i<requests.size();i++)minimum=Math.min(minimum,requests.get(i).getLong("started_elapsed_ms")-requests.get(i-1).getLong("started_elapsed_ms"));
        assertTrue(minimum>=5000);
        JSONObject result=new JSONObject().put("pass",true).put("server",origin).put("post_ids",new JSONArray().put(9).put(14))
            .put("real_server_read_only",true).put("image_hashes_match_transmitted_webcam_photos",true)
            .put("native_list_and_details_rendered",true).put("minimum_request_spacing_ms",minimum)
            .put("requests",new JSONArray(requests)).put("paid_api_calls",0);
        File out=new File(activity.getExternalFilesDir(null),"evidence/self-webcam/verification.json");
        try(FileOutputStream stream=new FileOutputStream(out)){stream.write(result.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));}
    }
}
