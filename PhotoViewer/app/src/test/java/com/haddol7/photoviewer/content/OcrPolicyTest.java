package com.haddol7.photoviewer.content;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;

public final class OcrPolicyTest {
    @Test public void short_noise_needs_stronger_evidence(){assertFalse(OcrPolicy.candidate("ys",.8f,false));assertFalse(OcrPolicy.candidate("a",.94f,false));assertTrue(OcrPolicy.candidate("바다라멘",.9f,false));assertFalse(OcrPolicy.candidate("} @$",.99f,false));}
    @Test public void document_fragments_are_not_sent_as_sentences(){assertFalse(OcrPolicy.candidate("bod",.8f,true));assertFalse(OcrPolicy.candidate("a b c d e f g h i j",.9f,true));assertTrue(OcrPolicy.candidate("We started with a fresh cup of coffee",.7f,true));}
    @Test public void nonfinite_confidence_and_controls_are_rejected(){assertFalse(OcrPolicy.candidate("CAFE MENU",Float.NaN,false));assertFalse(OcrPolicy.candidate("CAFE\nMENU",.99f,false));assertFalse(OcrPolicy.candidate("ㅏㅣㅜ",1,false));}
    @Test public void crop_recheck_tolerates_document_spelling_but_not_unrelated_text(){assertTrue(OcrPolicy.similarity("Coffee before heading to Odori Park","Coffee before head.ng to Odori Park")>.9);assertEquals(0,OcrPolicy.similarity("aaa","bbb"),0);assertEquals(1,OcrPolicy.similarity("ＣＡＦＥ MENU","cafe menu"),0);}
    @Test public void inverse_rotation_recovers_original_points(){
        for(int angle:new int[]{-20,-14,0,14,20}){OcrPage.Transform t=OcrPage.transform(737,934,angle,2);double a=Math.toRadians(angle),c=Math.cos(a),s=Math.sin(a);float[] original={.2f,.3f,.7f,.3f,.7f,.4f,.2f,.4f},rotated=new float[8];for(int i=0;i<8;i+=2){double x=original[i]*737-737/2.0,y=original[i+1]*934-934/2.0;rotated[i]=(float)(t.width()/2.0+2*(c*x-s*y));rotated[i+1]=(float)(t.height()/2.0+2*(s*x+c*y));}assertArrayEquals(original,t.original(rotated),.00001f);assertTrue(OcrPolicy.convex(t.original(rotated)));}
    }
    @Test public void invalid_highlight_quads_are_rejected(){assertFalse(OcrPolicy.convex(new float[]{0,0,1,1,1,0,0,1}));assertFalse(OcrPolicy.convex(new float[]{0,0,1,0,1,0,0,0}));assertTrue(OcrPolicy.convex(new float[]{.1f,.2f,.9f,.1f,.95f,.3f,.15f,.4f}));}
    @Test public void background_without_paper_does_not_trigger_deskew(){int[] pixels=new int[100*100];Arrays.fill(pixels,0xff237c31);assertNull(OcrPage.rotation(pixels,100,100));Arrays.fill(pixels,0xffffffff);assertNull(OcrPage.rotation(pixels,100,100));}
    @Test public void projected_text_lines_detect_positive_and_negative_rotation(){
        for(int angle:new int[]{-14,14}){int w=300,h=300;int[] pixels=new int[w*h];Arrays.fill(pixels,0xffffffff);double slope=-Math.tan(Math.toRadians(angle));for(int row=70;row<=230;row+=28)for(int x=40;x<260;x++){if(x%15>10)continue;int y=(int)Math.round(row+slope*(x-150));if(y>4&&y<h-5)pixels[y*w+x]=0xff222222;}OcrPage.Rotation rotation=OcrPage.rotation(pixels,w,h);assertNotNull(rotation);assertEquals(angle,rotation.angle(),2);}
    }
}
