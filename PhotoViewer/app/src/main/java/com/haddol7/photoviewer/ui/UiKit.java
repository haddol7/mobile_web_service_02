package com.haddol7.photoviewer.ui;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Native views share a small visual vocabulary; no browser or HTML renderer. */
public final class UiKit {
    public static final int INK = Color.rgb(23, 43, 66), GREEN = Color.rgb(23, 107, 113);
    public static final int PAPER = Color.rgb(243, 246, 249), WHITE = Color.WHITE;
    public static final int SAGE = Color.rgb(232, 238, 244), MUTED = Color.rgb(94, 112, 131);
    private UiKit() {}
    private static Typeface regular,semibold;
    public static synchronized Typeface font(Context context,boolean bold){
        if(regular==null){try{regular=Typeface.createFromAsset(context.getAssets(),"fonts/PretendardVariable.ttf");semibold=android.os.Build.VERSION.SDK_INT>=28?Typeface.create(regular,600,false):Typeface.create(regular,Typeface.BOLD);}catch(RuntimeException error){regular=Typeface.DEFAULT;semibold=Typeface.DEFAULT_BOLD;}}
        return bold?semibold:regular;
    }
    public static int dp(Context context, float value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }
    public static LinearLayout column(Context context) {
        LinearLayout result = new LinearLayout(context);
        result.setOrientation(LinearLayout.VERTICAL);
        return result;
    }
    public static LinearLayout row(Context context) {
        LinearLayout result = new LinearLayout(context);
        result.setOrientation(LinearLayout.HORIZONTAL);
        result.setGravity(android.view.Gravity.CENTER_VERTICAL);
        return result;
    }
    public static TextView text(Context context, String value, float size, boolean bold) {
        TextView result = new TextView(context);
        result.setText(value); result.setTextSize(size); result.setTextColor(INK);
        result.setTypeface(font(context,bold));
        result.setPadding(0, dp(context, 3), 0, dp(context, 3));
        return result;
    }
    public static Button button(Context context, String value, View.OnClickListener action) {
        Button result = new Button(context);
        result.setText(value); result.setAllCaps(false); result.setTextColor(INK);
        result.setTypeface(font(context,true));
        result.setTextSize(13); result.setMinHeight(dp(context, 44));result.setMinimumHeight(dp(context,44));
        result.setPadding(dp(context,10),dp(context,6),dp(context,10),dp(context,6));
        GradientDrawable shape=new GradientDrawable();shape.setColor(SAGE);shape.setCornerRadius(dp(context,10));
        result.setBackground(shape);result.setStateListAnimator(null);result.setElevation(0);
        if(android.os.Build.VERSION.SDK_INT>=26)result.setDefaultFocusHighlightEnabled(false);
        selected(result,false);
        result.setOnClickListener(action); return result;
    }
    public static EditText input(Context context, String hint, int inputType) {
        EditText result = new EditText(context); result.setHint(hint); result.setTextSize(15);
        result.setTextColor(INK); result.setSingleLine(true); result.setInputType(inputType);
        result.setTypeface(font(context,false));
        result.setPadding(dp(context, 10), dp(context, 8), dp(context, 10), dp(context, 8));
        result.setMinHeight(dp(context,44));GradientDrawable shape=new GradientDrawable();shape.setColor(WHITE);
        shape.setCornerRadius(dp(context,10));shape.setStroke(dp(context,1),Color.rgb(182,197,184));result.setBackground(shape);
        return result;
    }
    public static LinearLayout card(Context context) {
        LinearLayout result = column(context);
        result.setPadding(dp(context, 16), dp(context, 12), dp(context, 16), dp(context, 12));
        GradientDrawable background = new GradientDrawable(); background.setColor(WHITE);
        background.setCornerRadius(dp(context, 12)); background.setStroke(dp(context, 1), SAGE);
        result.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(context, 12); result.setLayoutParams(params); return result;
    }
    public static void weighted(LinearLayout parent, View child) {
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,-2,1);params.setMargins(dp(parent.getContext(),2),dp(parent.getContext(),2),dp(parent.getContext(),2),dp(parent.getContext(),2));parent.addView(child,params);
    }
    public static void selected(Button button,boolean selected){button.setSelected(selected);int base=selected?GREEN:SAGE,focus=selected?Color.rgb(18,83,91):Color.rgb(219,230,239);button.setBackgroundTintList(new android.content.res.ColorStateList(new int[][]{{android.R.attr.state_focused},{android.R.attr.state_pressed},{}},new int[]{focus,focus,base}));button.setTextColor(selected?WHITE:INK);}
}
