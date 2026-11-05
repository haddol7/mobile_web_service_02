package com.haddol7.photoviewer.content;

import android.content.Context;
import android.graphics.*;
import android.net.Uri;
import android.test.InstrumentationTestCase;
import androidx.exifinterface.media.ExifInterface;
import com.haddol7.photoviewer.data.*;
import com.haddol7.photoviewer.model.*;
import org.json.*;
import java.io.*;
import java.util.*;

/** Real bundled models, Android pixels/EXIF/JSON and HTTP; never JVM mocks. */
@SuppressWarnings("deprecation")
public final class ContentDeviceTest extends InstrumentationTestCase {
    private boolean hasPost(JSONObject page,long id)throws Exception{
        JSONArray rows=page.getJSONArray("results");
        for(int i=0;i<rows.length();i++)if(rows.getJSONObject(i).getJSONObject("post").getLong("id")==id)return true;
        return false;
    }
    private Context context(){return getInstrumentation().getTargetContext();}
    private void write(File file,byte[] bytes)throws IOException{try(FileOutputStream out=new FileOutputStream(file)){out.write(bytes);}}
    private byte[] bytes(InputStream source)throws IOException{try(InputStream in=source;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] data=new byte[8192];int n;while((n=in.read(data))!=-1)out.write(data,0,n);return out.toByteArray();}}
    private byte[] png(Bitmap bitmap){ByteArrayOutputStream out=new ByteArrayOutputStream();assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG,100,out));return out.toByteArray();}
    private File fixture()throws Exception{File f=File.createTempFile("portrait-fixture-",".jpg",context().getCacheDir());write(f,bytes(getInstrumentation().getContext().getAssets().open("portrait.jpg")));return f;}
    public void test01BundledFaceAndActualMosaicPixels()throws Exception{
        File input=fixture();String originalFile=PhotoPipeline.sha256(bytes(new FileInputStream(input)));
        Bitmap source=PhotoPipeline.read(context(),Uri.fromFile(input));String original=PhotoPipeline.sha256(png(source));
        try(VisionEngine engine=new VisionEngine()){
            List<MosaicDraft.Region> faces=engine.faces(source);assertTrue("Bundled detector did not find the known face",faces.size()>0);
            Bitmap edited=PhotoPipeline.render(source,faces);assertEquals(original,PhotoPipeline.sha256(png(source)));
            assertEquals(source.getPixel(1,1),edited.getPixel(1,1));int changes=0;
            for(MosaicDraft.Region r:faces)for(int y=(int)(r.top*source.getHeight());y<r.bottom*source.getHeight();y+=3)for(int x=(int)(r.left*source.getWidth());x<r.right*source.getWidth();x+=3)if(source.getPixel(x,y)!=edited.getPixel(x,y))changes++;
            assertTrue("Only an overlay was applied; stored pixels did not change",changes>100);
            assertEquals(originalFile,PhotoPipeline.sha256(bytes(new FileInputStream(input))));
            PhotoPipeline.Encoded encoded=PhotoPipeline.encode(context(),edited);assertEquals(encoded.sha256(),PhotoPipeline.sha256(encoded.bytes()));assertTrue(encoded.bytes().length<=5*1024*1024);
            VisionEngine.Analysis analysis=engine.analyze(encoded.bitmap());assertNotNull("Bundled image labeling failed",analysis.suggestion());
            File evidence=new File(context().getExternalFilesDir(null),"evidence");assertTrue(evidence.isDirectory()||evidence.mkdirs());write(new File(evidence,"mosaiced-public-copy.jpg"),encoded.bytes());
            android.util.Log.i("ContentDeviceTest","face_count="+faces.size()+" changed_samples="+changes+" theme="+analysis.suggestion().theme());
        }
    }
    public void test02ExifOrientationAndAlphaAreNormalized()throws Exception{
        Bitmap source=Bitmap.createBitmap(160,90,Bitmap.Config.ARGB_8888);source.eraseColor(Color.RED);File file=File.createTempFile("orientation-",".jpg",context().getCacheDir());try(FileOutputStream out=new FileOutputStream(file)){source.compress(Bitmap.CompressFormat.JPEG,95,out);}ExifInterface exif=new ExifInterface(file.getAbsolutePath());exif.setAttribute(ExifInterface.TAG_ORIENTATION,"6");exif.saveAttributes();Bitmap upright=PhotoPipeline.read(context(),Uri.fromFile(file));assertEquals(90,upright.getWidth());assertEquals(160,upright.getHeight());
        File transparent=File.createTempFile("alpha-",".png",context().getCacheDir());source.eraseColor(Color.TRANSPARENT);write(transparent,png(source));Bitmap opaque=PhotoPipeline.read(context(),Uri.fromFile(transparent));assertEquals(Color.WHITE,opaque.getPixel(2,2));
    }
    private Bitmap textPhoto(){Bitmap bitmap=Bitmap.createBitmap(1600,1000,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(bitmap);canvas.drawColor(Color.WHITE);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);paint.setColor(Color.BLACK);paint.setTypeface(Typeface.create("sans-serif",Typeface.BOLD));paint.setTextSize(120);canvas.drawText("바다라멘",120,250,paint);canvas.drawText("CAFE MENU 100",120,500,paint);paint.setColor(Color.rgb(200,90,45));canvas.drawRect(150,650,850,880,paint);return bitmap;}
    public void test03KoreanLatinOcrAndRestorablePacket()throws Exception{
        PhotoPipeline.Encoded encoded=PhotoPipeline.encode(context(),textPhoto());
        try(VisionEngine engine=new VisionEngine()){
            VisionEngine.Analysis analysis=engine.analyze(encoded.bitmap());assertEquals("ready",analysis.ocrStatus());
            StringBuilder all=new StringBuilder();for(VisionEngine.Line line:analysis.lines())all.append(line.text.replace(" ","")).append(' ');
            assertTrue("Korean OCR did not recognize the fixture",all.toString().contains("바다라멘"));assertTrue("Latin OCR did not recognize the fixture",all.toString().contains("CAFE"));
            ComposerState state=new ComposerState();state.sha=encoded.sha256();state.width=encoded.bitmap().getWidth();state.height=encoded.bitmap().getHeight();state.faceChecked=true;state.publicPath=encoded.file().getAbsolutePath();state.lines.addAll(analysis.lines());state.ocrStatus="ready";state.theme="food";state.themeEdited=true;state.tags="후기,라멘";state.title="테스트 기록";state.text="본문에는 가게 이름 없음";
            ComposerState restored=ComposerState.restore(new JSONObject(state.save().toString()));assertEquals(state.packet().toString(),restored.packet().toString());
            for(VisionEngine.Line line:state.lines)line.included=true;
            state.lines.get(0).included=false;assertEquals(analysis.lines().size()-1,state.packet().getJSONArray("lines").length());
        }
    }
    public void test04AndroidContentUploadCorrectionSearchAndConflict()throws Exception{
        String server=((android.test.InstrumentationTestRunner)getInstrumentation()).getArguments().getString("server","http://10.0.2.2:8000/");PhotoRepository api=new PhotoRepository(server);api.me();android.os.Bundle args=((android.test.InstrumentationTestRunner)getInstrumentation()).getArguments();String name=args.getString("owner"),password=args.getString("password");assertNotNull("Provision isolated test owner",name);SessionInfo session=api.login(name,password);assertTrue(session.canPublish);
        PhotoPipeline.Encoded encoded=PhotoPipeline.encode(context(),textPhoto());ComposerState state=new ComposerState();state.sha=encoded.sha256();state.width=encoded.bitmap().getWidth();state.height=encoded.bitmap().getHeight();state.theme="food";state.themeEdited=true;state.tags="라멘,후기";state.ocrStatus="ready";state.lines.add(new VisionEngine.Line("바다라멘",new float[]{.05f,.1f,.8f,.1f,.8f,.3f,.05f,.3f}));
        PhotoPost post=api.upload("기기 검증 사진","본문에는 문구 없음",encoded.bytes(),"image/jpeg","public.jpg",state.packet().toString());assertEquals(encoded.sha256(),PhotoPipeline.sha256(api.downloadPhoto(post.imageUrl)));
        JSONObject saved=api.content(post.id);assertEquals("food",saved.getString("theme"));assertEquals(1,saved.getLong("revision"));assertTrue(hasPost(api.browse("바다라멘","food","후기",true,null),post.id));
        state.postId=post.id;state.revision=1;state.lines.get(0).text="바른가게";state.lines.get(0).origin="user";assertEquals(2,api.saveContent(post.id,state.packet()).getLong("revision"));
        assertFalse(hasPost(api.browse("바다라멘","","",true,null),post.id));assertTrue(hasPost(api.browse("바른가게","","",true,null),post.id));
        try{api.saveContent(post.id,state.packet());fail("Stale correction overwrote server state");}catch(HttpException error){assertEquals(409,error.status);assertEquals(Long.valueOf(2),error.revision);}
        PhotoRepository visitor=new PhotoRepository(server);try{visitor.saveContent(post.id,state.packet());fail("Anonymous correction accepted");}catch(HttpException error){assertTrue(error.status==401||error.status==403);}
        state.revision=2;state.lines.get(0).included=false;api.saveContent(post.id,state.packet());assertFalse(hasPost(api.browse("바른가게","","",true,null),post.id));
        api.logout();assertFalse(api.me().isAuthenticated());
    }
    public void test05RealTouchCreatesMovesAndUndoesManualRegion()throws Exception{
        getInstrumentation().runOnMainSync(()->{
            Bitmap bitmap=Bitmap.createBitmap(100,100,Bitmap.Config.ARGB_8888);bitmap.eraseColor(Color.LTGRAY);
            android.widget.FrameLayout parent=new android.widget.FrameLayout(context());PhotoCanvas view=new PhotoCanvas(context());parent.addView(view);parent.layout(0,0,600,600);view.layout(0,0,600,600);view.bitmap(bitmap);MosaicDraft draft=new MosaicDraft();int[] changes={0};view.edit(draft,new PhotoCanvas.Listener(){public void changed(){changes[0]++;}public void selected(int i){}});view.mode("add");view.draw(new Canvas(Bitmap.createBitmap(600,600,Bitmap.Config.ARGB_8888)));
            touch(view,android.view.MotionEvent.ACTION_DOWN,120,120);touch(view,android.view.MotionEvent.ACTION_MOVE,360,360);touch(view,android.view.MotionEvent.ACTION_UP,360,360);
            assertEquals(1,draft.regions().size());assertEquals(.2f,draft.regions().get(0).left,.001f);assertEquals(.6f,draft.regions().get(0).right,.001f);
            touch(view,android.view.MotionEvent.ACTION_DOWN,200,200);touch(view,android.view.MotionEvent.ACTION_MOVE,540,540);touch(view,android.view.MotionEvent.ACTION_UP,540,540);
            assertEquals(1f,draft.regions().get(0).right,.001f);assertEquals(2,changes[0]);assertTrue(draft.undo());assertEquals(.2f,draft.regions().get(0).left,.001f);
        });
    }
    private void touch(PhotoCanvas view,int action,float x,float y){long now=android.os.SystemClock.uptimeMillis();android.view.MotionEvent event=android.view.MotionEvent.obtain(now,now,action,x,y,0);try{assertTrue(view.onTouchEvent(event));}finally{event.recycle();}}
    public void test06ActualPhotoProducesAnimalThemeWithoutManualSelection()throws Exception{
        Bitmap dog;try(InputStream in=getInstrumentation().getContext().getAssets().open("dog.jpg")){dog=BitmapFactory.decodeStream(in);}assertNotNull(dog);
        try(VisionEngine engine=new VisionEngine()){VisionEngine.Analysis result=engine.analyze(dog);assertNotNull(result.suggestion());android.util.Log.i("ContentDeviceTest","dog_theme="+result.suggestion().theme()+" alternatives="+result.suggestion().alternatives());assertEquals("A clear animal photo did not get the animal theme","animal",result.suggestion().theme());assertTrue(result.suggestion().tags().contains("강아지")||result.suggestion().tags().contains("반려동물"));}
    }
    public void test07BackgroundTexturesDoNotBecomeSearchText()throws Exception{
        try(VisionEngine engine=new VisionEngine()){
            for(String name:new String[]{"grass","grass-large","brick","fur","foliage-crop","fruit-crop"}){
                Bitmap bitmap;try(InputStream in=getInstrumentation().getContext().getAssets().open("ocr/"+name+".png")){bitmap=BitmapFactory.decodeStream(in);}assertNotNull(bitmap);
                VisionEngine.Analysis result=engine.analyze(bitmap);assertEquals(name+" produced spurious search phrases",0,result.lines().size());bitmap.recycle();
            }
        }
    }
    public void test08PrintedPageRetainsSentencesAndValidSourceQuads()throws Exception{
        Bitmap bitmap;try(InputStream in=getInstrumentation().getContext().getAssets().open("ocr/printed-page.png")){bitmap=BitmapFactory.decodeStream(in);}
        try(VisionEngine engine=new VisionEngine()){VisionEngine.Analysis result=engine.analyze(bitmap);assertTrue("Printed text was over-filtered",result.lines().size()>=7);for(VisionEngine.Line line:result.lines())assertTrue(OcrPolicy.convex(line.quad));}finally{bitmap.recycle();}
    }
}

