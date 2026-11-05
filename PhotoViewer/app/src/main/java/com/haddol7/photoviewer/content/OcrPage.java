package com.haddol7.photoviewer.content;

import java.util.*;

/** Paper-line rotation only; published pixels are never changed. */
public final class OcrPage {
    public record Rotation(int angle,double paperRatio,double gain){}
    public record Transform(int width,int height,int sourceWidth,int sourceHeight,double angle,double scale){
        public float[] original(float[] points){
            double a=Math.toRadians(angle),c=Math.cos(a),s=Math.sin(a);float[] q=new float[8];
            for(int i=0;i<8;i+=2){double x=(points[i]-width/2.0)/scale,y=(points[i+1]-height/2.0)/scale;q[i]=(float)Math.max(0,Math.min(1,(c*x+s*y+sourceWidth/2.0)/sourceWidth));q[i+1]=(float)Math.max(0,Math.min(1,(-s*x+c*y+sourceHeight/2.0)/sourceHeight));}return q;
        }
    }
    private OcrPage(){}
    public static Transform transform(int w,int h,double angle,double scale){double a=Math.toRadians(angle),c=Math.abs(Math.cos(a)),s=Math.abs(Math.sin(a));return new Transform((int)Math.ceil(scale*(w*c+h*s)),(int)Math.ceil(scale*(w*s+h*c)),w,h,angle,scale);}
    private static double lum(int pixel){return (((pixel>>16)&255)*3+((pixel>>8)&255)*6+(pixel&255))/10.0;}
    public static Rotation rotation(int[] pixels,int w,int h){
        if(w<20||h<20||pixels.length!=w*h)return null;List<int[]> points=new ArrayList<>();int paper=0,total=0;
        for(int y=4;y<h-4;y+=2)for(int x=4;x<w-4;x+=2){int pixel=pixels[y*w+x],r=(pixel>>16)&255,g=(pixel>>8)&255,b=pixel&255;double light=lum(pixel);int chroma=Math.max(r,Math.max(g,b))-Math.min(r,Math.min(g,b));total++;if(light>140&&chroma<45)paper++;if(light<125&&chroma<60&&Math.max(Math.max(lum(pixels[y*w+x-3]),lum(pixels[y*w+x+3])),Math.max(lum(pixels[(y-3)*w+x]),lum(pixels[(y+3)*w+x])))>155)points.add(new int[]{x-w/2,y-h/2});}
        if(total==0||paper/(double)total<.35||points.size()<100)return null;double initial=score(points,0),best=initial;int angle=0;
        for(int candidate=-20;candidate<=20;candidate++){double value=score(points,candidate);if(value>best){best=value;angle=candidate;}}
        return new Rotation(best>initial*1.15?angle:0,paper/(double)total,best/initial);
    }
    private static double score(List<int[]> points,int angle){double a=Math.toRadians(angle),s=Math.sin(a),c=Math.cos(a),score=0;Map<Integer,Integer> bins=new HashMap<>();for(int[] p:points)bins.merge((int)Math.round((s*p[0]+c*p[1])/2),1,Integer::sum);for(int v:bins.values())score+=(double)v*v;return score;}
}
