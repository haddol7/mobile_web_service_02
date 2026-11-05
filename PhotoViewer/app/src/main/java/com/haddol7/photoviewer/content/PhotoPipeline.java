package com.haddol7.photoviewer.content;

import android.content.Context;
import android.graphics.*;
import android.net.Uri;
import androidx.exifinterface.media.ExifInterface;
import java.io.*;
import java.security.MessageDigest;
import java.util.List;

/** All bitmap/encoding operations run on a worker, never change the picked URI. */
public final class PhotoPipeline {
    public record Encoded(byte[] bytes,Bitmap bitmap,String sha256,File file) {}
    public static Bitmap read(Context context,Uri uri) throws IOException {
        BitmapFactory.Options bounds=new BitmapFactory.Options(); bounds.inJustDecodeBounds=true;
        try(InputStream in=context.getContentResolver().openInputStream(uri)){BitmapFactory.decodeStream(in,null,bounds);}
        if(bounds.outWidth<=0||bounds.outHeight<=0||!("image/jpeg".equals(bounds.outMimeType)||"image/png".equals(bounds.outMimeType)||"image/webp".equals(bounds.outMimeType)))
            throw new IOException("JPEG, PNG, WebP 사진을 선택하세요.");
        int sample=1;
        while(Math.max(bounds.outWidth,bounds.outHeight)/sample>2048)sample*=2;
        BitmapFactory.Options options=new BitmapFactory.Options(); options.inSampleSize=sample; options.inPreferredConfig=Bitmap.Config.ARGB_8888;
        Bitmap decoded;
        try(InputStream in=context.getContentResolver().openInputStream(uri)){decoded=BitmapFactory.decodeStream(in,null,options);}
        if(decoded==null)throw new IOException("사진 파일을 읽을 수 없습니다.");
        Matrix matrix=new Matrix();
        try(InputStream in=context.getContentResolver().openInputStream(uri)) {
            ExifInterface exif=new ExifInterface(in);
            if(exif.isFlipped())matrix.postScale(-1,1);
            matrix.postRotate(exif.getRotationDegrees());
        } catch(IOException ignored) { /* A decoded image without EXIF uses its actual pixel orientation. */ }
        Bitmap oriented=Bitmap.createBitmap(decoded,0,0,decoded.getWidth(),decoded.getHeight(),matrix,true);
        if(oriented!=decoded)decoded.recycle();
        Bitmap opaque=Bitmap.createBitmap(oriented.getWidth(),oriented.getHeight(),Bitmap.Config.ARGB_8888);
        Canvas canvas=new Canvas(opaque);canvas.drawColor(Color.WHITE);canvas.drawBitmap(oriented,0,0,null);oriented.recycle();
        return opaque;
    }
    public static Bitmap render(Bitmap source,List<MosaicDraft.Region> regions) {
        Bitmap result=source.copy(Bitmap.Config.ARGB_8888,true); Canvas canvas=new Canvas(result);
        for(MosaicDraft.Region region:regions) {
            if(!region.active)continue;
            int l=Math.max(0,(int)Math.floor(region.left*source.getWidth())),t=Math.max(0,(int)Math.floor(region.top*source.getHeight()));
            int r=Math.min(source.getWidth(),(int)Math.ceil(region.right*source.getWidth())),b=Math.min(source.getHeight(),(int)Math.ceil(region.bottom*source.getHeight()));
            if(r<=l||b<=t)continue;
            Bitmap crop=Bitmap.createBitmap(source,l,t,r-l,b-t);
            float ratio=new float[]{.06f,.10f,.16f}[region.strength];
            int block=Math.max(2,Math.round(Math.max(r-l,b-t)*ratio));
            Bitmap small=Bitmap.createScaledBitmap(crop,Math.max(1,(r-l)/block),Math.max(1,(b-t)/block),false);
            Paint paint=new Paint();paint.setFilterBitmap(false);
            canvas.drawBitmap(small,null,new Rect(l,t,r,b),paint);
            if(small!=crop&&small!=source)small.recycle();if(crop!=source)crop.recycle();
        }
        return result;
    }
    public static Encoded encode(Context context,Bitmap bitmap) throws Exception {
        Bitmap working=bitmap;byte[] bytes=null;
        for(int attempt=0;attempt<8;attempt++) {
            for(int quality:new int[]{90,80,70}) {
                ByteArrayOutputStream out=new ByteArrayOutputStream();
                if(!working.compress(Bitmap.CompressFormat.JPEG,quality,out))throw new IOException("게시 사본을 만들 수 없습니다.");
                bytes=out.toByteArray();if(bytes.length<=5*1024*1024)break;
            }
            if(bytes.length<=5*1024*1024)break;
            Bitmap smaller=Bitmap.createScaledBitmap(working,Math.max(1,working.getWidth()*3/4),Math.max(1,working.getHeight()*3/4),true);
            if(working!=bitmap)working.recycle();working=smaller;
        }
        if(working!=bitmap)working.recycle();
        if(bytes==null||bytes.length>5*1024*1024)throw new IOException("사진을 5MiB 이하로 만들 수 없습니다.");
        Bitmap exact=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
        if(exact==null)throw new IOException("게시 사본을 다시 읽을 수 없습니다.");
        File file=File.createTempFile("public-photo-",".jpg",context.getCacheDir());
        try(FileOutputStream out=new FileOutputStream(file)){out.write(bytes);}
        return new Encoded(bytes,exact,sha256(bytes),file);
    }
    public static String sha256(byte[] bytes) throws Exception {
        StringBuilder result=new StringBuilder();
        for(byte b:MessageDigest.getInstance("SHA-256").digest(bytes))result.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
        return result.toString();
    }
    public static File saveWorking(Context context,Bitmap bitmap) throws IOException {
        File file=File.createTempFile("working-photo-",".png",context.getCacheDir());
        try(FileOutputStream out=new FileOutputStream(file)){if(!bitmap.compress(Bitmap.CompressFormat.PNG,100,out))throw new IOException("작업 사진을 저장하지 못했습니다.");}
        return file;
    }
}
