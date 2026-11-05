package com.haddol7.photoviewer.content;

import java.text.Normalizer;
import java.util.*;

/** Recognition evidence is separate from the user's decision to index a line. */
public final class OcrPolicy {
    private OcrPolicy(){}
    public static String normalized(String text){return Normalizer.normalize(text,Normalizer.Form.NFKC).toLowerCase(Locale.ROOT).replaceAll("[^\\p{L}\\p{N}]","");}
    public static boolean candidate(String text,float confidence,boolean document){
        int letters=(int)text.codePoints().filter(Character::isLetterOrDigit).count();
        int length=(int)text.codePoints().filter(c->!Character.isWhitespace(c)).count();
        if(length==0||text.codePointCount(0,text.length())>200||text.codePoints().anyMatch(Character::isISOControl))return false;
        if(text.codePoints().anyMatch(c->c>=0x3130&&c<=0x318F))return false;
        if(!Float.isFinite(confidence)||confidence<0||confidence>1)return false;
        if(document)return letters>=10&&letters>=length*.75&&confidence>=.35f&&Arrays.stream(text.trim().split("\\s+")).filter(w->normalized(w).length()>=2).count()>=2;
        float threshold=letters==1?.95f:letters==2?.85f:.65f;
        return letters>=length*.6&&confidence>=threshold;
    }
    public static double similarity(String a,String b){
        int[] x=normalized(a).codePoints().toArray(),y=normalized(b).codePoints().toArray();
        if(x.length==0||y.length==0)return 0;int[] row=new int[y.length+1];for(int j=0;j<row.length;j++)row[j]=j;
        for(int i=1;i<=x.length;i++){int diagonal=row[0];row[0]=i;for(int j=1;j<=y.length;j++){int old=row[j];row[j]=Math.min(Math.min(row[j]+1,row[j-1]+1),diagonal+(x[i-1]==y[j-1]?0:1));diagonal=old;}}
        return 1-row[y.length]/(double)Math.max(x.length,y.length);
    }
    public static boolean convex(float[] q){
        if(q==null||q.length!=8)return false;
        for(int i=0;i<4;i++){int j=(i+1)%4,k=(i+2)%4;float cross=(q[j*2]-q[i*2])*(q[k*2+1]-q[j*2+1])-(q[j*2+1]-q[i*2+1])*(q[k*2]-q[j*2]);if(!Float.isFinite(q[i*2])||!Float.isFinite(q[i*2+1])||q[i*2]<0||q[i*2]>1||q[i*2+1]<0||q[i*2+1]>1||cross<=1e-10)return false;}return true;
    }
    public static float[] bounds(float[] q){float l=1,t=1,r=0,b=0;for(int i=0;i<8;i+=2){l=Math.min(l,q[i]);r=Math.max(r,q[i]);t=Math.min(t,q[i+1]);b=Math.max(b,q[i+1]);}return new float[]{l,t,r,b};}
    public static float overlap(float[] a,float[] b){float[] x=bounds(a),y=bounds(b);float intersection=Math.max(0,Math.min(x[2],y[2])-Math.max(x[0],y[0]))*Math.max(0,Math.min(x[3],y[3])-Math.max(x[1],y[1]));float area=(x[2]-x[0])*(x[3]-x[1])+(y[2]-y[0])*(y[3]-y[1])-intersection;return area>0?intersection/area:0;}
}
