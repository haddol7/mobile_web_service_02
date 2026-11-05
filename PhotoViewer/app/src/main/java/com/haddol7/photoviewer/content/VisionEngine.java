package com.haddol7.photoviewer.content;

import android.graphics.*;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.face.*;
import com.google.mlkit.vision.label.*;
import com.google.mlkit.vision.label.defaults.ImageLabelerOptions;
import com.google.mlkit.vision.text.*;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Bundled models. Recognition and temporary deskewing run entirely on the device. */
public final class VisionEngine implements AutoCloseable {
    public static final class Line {
        public final String id;
        public String text,origin="auto";
        public final float[] quad;
        public boolean included=true;
        public Line(String text,float[] quad){this(UUID.randomUUID().toString(),text,quad);}
        public Line(String id,String text,float[] quad){this.id=id;this.text=text;this.quad=quad.clone();}
    }
    public record Analysis(ThemeMapper.Suggestion suggestion,String themeStatus,List<Line> lines,String ocrStatus){}
    private record Candidate(String text,float confidence,float[] quad,TextRecognizer recognizer){}
    private final FaceDetector faces=FaceDetection.getClient(new FaceDetectorOptions.Builder().setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_ACCURATE).setMinFaceSize(.05f).build());
    private final ImageLabeler labeler=ImageLabeling.getClient(new ImageLabelerOptions.Builder().setConfidenceThreshold(.4f).build());
    private final TextRecognizer korean=TextRecognition.getClient(new KoreanTextRecognizerOptions.Builder().build());
    private final TextRecognizer latin=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
    public List<MosaicDraft.Region> faces(Bitmap bitmap)throws Exception{
        List<float[]> found=facePass(bitmap,0,0,bitmap.getWidth(),bitmap.getHeight());
        boolean small=found.stream().anyMatch(q->q[2]-q[0]<.08f);
        if(Math.max(bitmap.getWidth(),bitmap.getHeight())>=900&&(found.isEmpty()||small)){
            int w=(int)(bitmap.getWidth()*.68f),h=(int)(bitmap.getHeight()*.68f);
            for(int y:new int[]{0,bitmap.getHeight()-h})for(int x:new int[]{0,bitmap.getWidth()-w}){
                for(float[] q:facePass(bitmap,x,y,w,h))if(found.stream().noneMatch(old->sameFace(old,q))&&confirmFace(bitmap,q))found.add(q);
            }
        }
        List<MosaicDraft.Region> regions=new ArrayList<>();
        for(float[] b:found){float dx=(b[2]-b[0])*.15f,dy=(b[3]-b[1])*.15f;regions.add(new MosaicDraft.Region(UUID.randomUUID().toString(),Math.max(0,b[0]-dx),Math.max(0,b[1]-dy),Math.min(1,b[2]+dx),Math.min(1,b[3]+dy),true,true,1));if(regions.size()==100)break;}
        return regions;
    }
    private List<float[]> facePass(Bitmap source,int x,int y,int w,int h)throws Exception{
        Bitmap crop=Bitmap.createBitmap(source,x,y,w,h);List<float[]> result=new ArrayList<>();
        try{for(Face face:Tasks.await(faces.process(InputImage.fromBitmap(crop,0)),30,TimeUnit.SECONDS)){Rect r=face.getBoundingBox();float l=Math.max(0,(x+r.left)/(float)source.getWidth()),t=Math.max(0,(y+r.top)/(float)source.getHeight()),right=Math.min(1,(x+r.right)/(float)source.getWidth()),bottom=Math.min(1,(y+r.bottom)/(float)source.getHeight());if(right>l&&bottom>t)result.add(new float[]{l,t,right,bottom});}}finally{if(crop!=source)crop.recycle();}return result;
    }
    private boolean confirmFace(Bitmap source,float[] q)throws Exception{
        float dx=q[2]-q[0],dy=q[3]-q[1];int l=Math.max(0,(int)((q[0]-dx)*source.getWidth())),t=Math.max(0,(int)((q[1]-dy)*source.getHeight())),r=Math.min(source.getWidth(),(int)Math.ceil((q[2]+dx)*source.getWidth())),b=Math.min(source.getHeight(),(int)Math.ceil((q[3]+dy)*source.getHeight()));
        for(float[] check:facePass(source,l,t,r-l,b-t))if(sameFace(q,check))return true;return false;
    }
    private static boolean sameFace(float[] a,float[] b){float intersection=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));float smallest=Math.min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]));return smallest>0&&intersection/smallest>.5f;}
    public Analysis analyze(Bitmap bitmap){
        ThemeMapper.Suggestion suggestion=null;String themeStatus="failed";
        try{List<ThemeMapper.Label> labels=new ArrayList<>();for(ImageLabel label:Tasks.await(labeler.process(InputImage.fromBitmap(bitmap,0)),30,TimeUnit.SECONDS))labels.add(new ThemeMapper.Label(label.getIndex(),label.getConfidence()));suggestion=ThemeMapper.suggest(labels);themeStatus="ready";}catch(Exception e){interrupted(e);}
        List<Line> lines=new ArrayList<>();boolean succeeded=false;List<Candidate> raw=new ArrayList<>();
        for(TextRecognizer recognizer:new TextRecognizer[]{latin,korean})try{raw.addAll(read(bitmap,recognizer));succeeded=true;}catch(Exception e){interrupted(e);}
        int examined=0;for(Candidate candidate:raw){if(lines.size()>=100||examined++>=100)break;if(!OcrPolicy.candidate(candidate.text,candidate.confidence,false))continue;try{Candidate confirmed=confirm(bitmap,candidate,false);if(confirmed!=null)add(lines,confirmed,false,null,bitmap.getWidth(),bitmap.getHeight());}catch(Exception e){interrupted(e);}}
        int rawLetters=raw.stream().mapToInt(c->OcrPolicy.normalized(c.text).length()).sum();
        if(rawLetters>=40){
            float ratio=Math.min(1,600f/Math.max(bitmap.getWidth(),bitmap.getHeight()));Bitmap small=Bitmap.createScaledBitmap(bitmap,Math.max(20,Math.round(bitmap.getWidth()*ratio)),Math.max(20,Math.round(bitmap.getHeight()*ratio)),true);
            int[] pixels=new int[small.getWidth()*small.getHeight()];small.getPixels(pixels,0,small.getWidth(),0,0,small.getWidth(),small.getHeight());OcrPage.Rotation rotation=OcrPage.rotation(pixels,small.getWidth(),small.getHeight());if(small!=bitmap)small.recycle();
            if(rotation!=null&&(rotation.angle()!=0||lines.size()<3))try{
                OcrPage.Transform transform=OcrPage.transform(bitmap.getWidth(),bitmap.getHeight(),rotation.angle(),Math.min(2,2200.0/Math.max(bitmap.getWidth(),bitmap.getHeight())));Bitmap page=Bitmap.createBitmap(transform.width(),transform.height(),Bitmap.Config.ARGB_8888);
                try{Canvas canvas=new Canvas(page);canvas.drawColor(Color.WHITE);canvas.translate(page.getWidth()/2f,page.getHeight()/2f);canvas.scale((float)transform.scale(),(float)transform.scale());canvas.rotate((float)transform.angle());canvas.translate(-bitmap.getWidth()/2f,-bitmap.getHeight()/2f);canvas.drawBitmap(bitmap,0,0,new Paint(Paint.FILTER_BITMAP_FLAG));
                    long hangul=raw.stream().flatMapToInt(c->c.text.codePoints()).filter(c->c>=0xAC00&&c<=0xD7A3).count();TextRecognizer recognizer=hangul/(double)Math.max(1,rawLetters)<.15?latin:korean;List<Line> document=new ArrayList<>();
                    int checked=0;for(Candidate c:read(page,recognizer)){if(!OcrPolicy.candidate(c.text,c.confidence,true)||checked++>=40)continue;Candidate confirmed=confirm(page,c,true);if(confirmed!=null)add(document,confirmed,true,transform,page.getWidth(),page.getHeight());}
                    int chars=document.stream().mapToInt(l->OcrPolicy.normalized(l.text).length()).sum(),base=lines.stream().mapToInt(l->OcrPolicy.normalized(l.text).length()).sum();
                    if(document.size()>=3&&chars>Math.max(40,base*1.05)){lines=document;}
                }finally{page.recycle();}
            }catch(Exception e){interrupted(e);}
        }
        return new Analysis(suggestion,themeStatus,lines,lines.isEmpty()?(succeeded?"no_text":"failed"):"ready");
    }
    private List<Candidate> read(Bitmap bitmap,TextRecognizer recognizer)throws Exception{
        Text text=Tasks.await(recognizer.process(InputImage.fromBitmap(bitmap,0)),30,TimeUnit.SECONDS);List<Candidate> result=new ArrayList<>();
        for(Text.TextBlock block:text.getTextBlocks())for(Text.Line line:block.getLines()){
            Point[] points=line.getCornerPoints();if(points==null||points.length!=4)continue;float[] q=new float[8];for(int i=0;i<4;i++){q[2*i]=Math.max(0,Math.min(1,points[i].x/(float)bitmap.getWidth()));q[2*i+1]=Math.max(0,Math.min(1,points[i].y/(float)bitmap.getHeight()));}if(!OcrPolicy.convex(q))continue;
            result.add(new Candidate(line.getText().trim(),line.getConfidence(),q,recognizer));
        }return result;
    }
    private Candidate confirm(Bitmap bitmap,Candidate c,boolean document)throws Exception{
        float[] b=OcrPolicy.bounds(c.quad);int pad=Math.max(4,Math.round((b[3]-b[1])*bitmap.getHeight()*.18f));int l=Math.max(0,(int)(b[0]*bitmap.getWidth())-pad),t=Math.max(0,(int)(b[1]*bitmap.getHeight())-pad),r=Math.min(bitmap.getWidth(),(int)Math.ceil(b[2]*bitmap.getWidth())+pad),bottom=Math.min(bitmap.getHeight(),(int)Math.ceil(b[3]*bitmap.getHeight())+pad);
        Bitmap crop=Bitmap.createBitmap(bitmap,l,t,r-l,bottom-t);
        try{for(Candidate check:read(crop,c.recognizer)){
            if(!OcrPolicy.candidate(check.text,check.confidence,document))continue;
            double similarity=OcrPolicy.similarity(c.text,check.text),required=document?.78:OcrPolicy.normalized(c.text).length()<10?1:.90;
            if(similarity>=required)return new Candidate(check.confidence>c.confidence?check.text:c.text,Math.min(c.confidence,check.confidence),c.quad,c.recognizer);
        }}finally{if(crop!=bitmap)crop.recycle();}return null;
    }
    private static void add(List<Line> lines,Candidate c,boolean document,OcrPage.Transform transform,int w,int h){
        float[] q=c.quad.clone();if(transform!=null){for(int i=0;i<8;i+=2){q[i]*=w;q[i+1]*=h;}q=transform.original(q);}if(!OcrPolicy.convex(q))return;
        Line line=new Line(c.text,q);line.included=!document&&c.confidence>=.85f;
        for(int i=0;i<lines.size();i++){Line old=lines.get(i);if(OcrPolicy.overlap(old.quad,line.quad)>.45f){boolean same=OcrPolicy.similarity(old.text,line.text)>.65;if(same||OcrPolicy.overlap(old.quad,line.quad)>.75f){if(!old.included&&line.included)lines.set(i,line);return;}}}
        lines.add(line);
    }
    private static void interrupted(Exception e){if(e instanceof InterruptedException)Thread.currentThread().interrupt();}
    @Override public void close(){faces.close();labeler.close();korean.close();latin.close();}
}
