package com.haddol7.photoviewer.ui;

import android.content.Context;
import android.view.*;

/** Wraps touch targets instead of squeezing a long row off screen. */
public final class ChipFlow extends ViewGroup {
    public ChipFlow(Context context){super(context);}
    @Override protected void onMeasure(int widthSpec,int heightSpec){
        int width=MeasureSpec.getSize(widthSpec),x=0,y=0,row=0,gap=UiKit.dp(getContext(),4);
        for(int i=0;i<getChildCount();i++){View child=getChildAt(i);measureChild(child,widthSpec,heightSpec);int w=child.getMeasuredWidth(),h=child.getMeasuredHeight();if(x>0&&x+w>width){x=0;y+=row+gap;row=0;}x+=w+gap;row=Math.max(row,h);}
        setMeasuredDimension(resolveSize(width,widthSpec),resolveSize(y+row,heightSpec));
    }
    @Override protected void onLayout(boolean changed,int l,int t,int r,int b){
        int x=0,y=0,row=0,gap=UiKit.dp(getContext(),4),width=r-l;
        for(int i=0;i<getChildCount();i++){View child=getChildAt(i);int w=child.getMeasuredWidth(),h=child.getMeasuredHeight();if(x>0&&x+w>width){x=0;y+=row+gap;row=0;}child.layout(x,y,x+w,y+h);x+=w+gap;row=Math.max(row,h);}
    }
    @Override protected LayoutParams generateDefaultLayoutParams(){return new LayoutParams(LayoutParams.WRAP_CONTENT,LayoutParams.WRAP_CONTENT);}
}
