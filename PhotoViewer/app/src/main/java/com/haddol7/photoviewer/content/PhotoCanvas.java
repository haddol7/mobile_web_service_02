package com.haddol7.photoviewer.content;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import java.util.*;

/** Shared zoom/pan surface for mosaic regions and OCR source highlights. */
public final class PhotoCanvas extends View {
    public interface Listener { void changed(); void selected(int index); }
    private Bitmap bitmap;
    private MosaicDraft draft;
    private Listener listener;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private float zoom=1,panX,panY,downX,downY,startX,startY,ox,oy,scale=1;
    private int selected=-1;
    private String mode="view";
    private boolean drag,resize,gesture;
    private MosaicDraft.Region before,preview;
    private List<float[]> highlights=Collections.emptyList();
    private final ScaleGestureDetector pinch;
    public PhotoCanvas(Context context) {
        super(context);setFocusable(true);setContentDescription("사진 확대·이동 및 영역 확인");
        pinch=new ScaleGestureDetector(context,new ScaleGestureDetector.SimpleOnScaleGestureListener(){
            @Override public boolean onScale(ScaleGestureDetector detector){zoom=Math.max(1,Math.min(6,zoom*detector.getScaleFactor()));gesture=true;invalidate();return true;}
        });
        setBackgroundColor(Color.rgb(236,240,236));
    }
    public void bitmap(Bitmap value){bitmap=value;invalidate();}
    public void edit(MosaicDraft value,Listener changes){draft=value;listener=changes;}
    public String mode(){return mode;}
    public void mode(String value){mode=value;drag=false;preview=null;invalidate();}
    public void select(int value){selected=value;invalidate();if(listener!=null)listener.selected(value);}
    public int selected(){return selected;}
    public void resetZoom(){zoom=1;panX=panY=0;invalidate();}
    public void highlights(List<float[]> quads){highlights=new ArrayList<>(quads);invalidate();}
    public void focus(float[] q) {
        if(bitmap==null||getWidth()==0)return;
        float fit=Math.min(getWidth()/(float)bitmap.getWidth(),getHeight()/(float)bitmap.getHeight());
        float[] bounds=OcrPolicy.bounds(q);
        zoom=Math.max(1,Math.min(6,.65f/Math.max(.001f,Math.max(bounds[2]-bounds[0],bounds[3]-bounds[1]))));
        panX=(.5f-(bounds[0]+bounds[2])/2)*bitmap.getWidth()*fit*zoom;
        panY=(.5f-(bounds[1]+bounds[3])/2)*bitmap.getHeight()*fit*zoom;invalidate();
    }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);if(bitmap==null||bitmap.isRecycled())return;
        scale=Math.min(getWidth()/(float)bitmap.getWidth(),getHeight()/(float)bitmap.getHeight())*zoom;
        ox=(getWidth()-bitmap.getWidth()*scale)/2+panX;oy=(getHeight()-bitmap.getHeight()*scale)/2+panY;
        canvas.save();canvas.translate(ox,oy);canvas.scale(scale,scale);canvas.drawBitmap(bitmap,0,0,null);
        if(draft!=null){List<MosaicDraft.Region> regions=draft.regions();for(int i=0;i<regions.size();i++){MosaicDraft.Region r=(i==selected&&preview!=null)?preview:regions.get(i);drawRegion(canvas,r,i,i==selected);}}
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(3/scale);paint.setColor(Color.rgb(255,160,25));
        for(float[] q:highlights){Path outline=new Path();outline.moveTo(q[0]*bitmap.getWidth(),q[1]*bitmap.getHeight());for(int i=2;i<8;i+=2)outline.lineTo(q[i]*bitmap.getWidth(),q[i+1]*bitmap.getHeight());outline.close();canvas.drawPath(outline,paint);}
        if(drag&&"add".equals(mode)){paint.setColor(Color.rgb(30,120,100));canvas.drawRect(Math.min(startX,x(downX))*bitmap.getWidth(),Math.min(startY,y(downY))*bitmap.getHeight(),Math.max(startX,x(downX))*bitmap.getWidth(),Math.max(startY,y(downY))*bitmap.getHeight(),paint);}
        canvas.restore();
    }
    private void drawRegion(Canvas canvas,MosaicDraft.Region r,int index,boolean chosen){
        paint.setColor(chosen?Color.rgb(255,146,30):r.active?Color.rgb(36,133,99):Color.rgb(120,125,130));paint.setStrokeWidth((chosen?3:2)/scale);paint.setStyle(Paint.Style.STROKE);
        float l=r.left*bitmap.getWidth(),t=r.top*bitmap.getHeight(),right=r.right*bitmap.getWidth(),bottom=r.bottom*bitmap.getHeight();
        canvas.drawRect(l,t,right,bottom,paint);paint.setStyle(Paint.Style.FILL);paint.setTextSize(16/scale);canvas.drawText(String.valueOf(index+1),l+3/scale,t+18/scale,paint);
        if(chosen)canvas.drawCircle(right,bottom,7/scale,paint);
    }
    private float x(float value){return Math.max(0,Math.min(1,(value-ox)/scale/bitmap.getWidth()));}
    private float y(float value){return Math.max(0,Math.min(1,(value-oy)/scale/bitmap.getHeight()));}
    @Override public boolean onTouchEvent(android.view.MotionEvent event){
        if(bitmap==null)return false;
        getParent().requestDisallowInterceptTouchEvent(true);pinch.onTouchEvent(event);
        if(event.getPointerCount()>1){gesture=true;return true;}
        float px=event.getX(),py=event.getY();
        switch(event.getActionMasked()){
            case MotionEvent.ACTION_DOWN:
                gesture=false;downX=px;downY=py;startX=x(px);startY=y(py);drag=true;before=preview=null;
                if(draft!=null&&"edit".equals(mode)) {
                    List<MosaicDraft.Region> regions=draft.regions();int found=-1;
                    for(int i=regions.size()-1;i>=0;i--){MosaicDraft.Region r=regions.get(i);if(startX>=r.left&&startX<=r.right&&startY>=r.top&&startY<=r.bottom){found=i;break;}}
                    if(selected>=0&&selected<regions.size()){
                        MosaicDraft.Region r=regions.get(selected);float sx=ox+r.right*bitmap.getWidth()*scale,sy=oy+r.bottom*bitmap.getHeight()*scale;
                        if(Math.hypot(px-sx,py-sy)<30*getResources().getDisplayMetrics().density){found=selected;resize=true;}else resize=false;
                    }
                    select(found);if(found>=0)before=regions.get(found);
                }
                return true;
            case MotionEvent.ACTION_MOVE:
                if(gesture)return true;
                if("view".equals(mode)){panX+=px-downX;panY+=py-downY;downX=px;downY=py;}
                else if(before!=null&&"edit".equals(mode)){
                    float dx=x(px)-startX,dy=y(py)-startY;
                    if(resize)preview=before.bounds(before.left,before.top,Math.max(before.left+.005f,Math.min(1,before.right+dx)),Math.max(before.top+.005f,Math.min(1,before.bottom+dy)));
                    else {dx=Math.max(-before.left,Math.min(1-before.right,dx));dy=Math.max(-before.top,Math.min(1-before.bottom,dy));preview=before.bounds(before.left+dx,before.top+dy,before.right+dx,before.bottom+dy);}
                }else{downX=px;downY=py;}
                invalidate();return true;
            case MotionEvent.ACTION_UP:
                if(!gesture&&draft!=null){
                    if("add".equals(mode)){float l=Math.min(startX,x(px)),t=Math.min(startY,y(py)),r=Math.max(startX,x(px)),b=Math.max(startY,y(py));if(r-l>.005f&&b-t>.005f){select(draft.add(l,t,r,b));mode="edit";if(listener!=null)listener.changed();}}
                    else if(preview!=null&&before!=null){draft.update(selected,preview);if(listener!=null)listener.changed();}
                }
                drag=false;preview=null;performClick();invalidate();getParent().requestDisallowInterceptTouchEvent(false);return true;
            case MotionEvent.ACTION_CANCEL:drag=false;preview=null;getParent().requestDisallowInterceptTouchEvent(false);invalidate();return true;
            default:return true;
        }
    }
    @Override public boolean performClick(){super.performClick();return true;}
}
