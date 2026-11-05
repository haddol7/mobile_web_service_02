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
    public static final int INK = Color.rgb(40, 60, 48), GREEN = Color.rgb(69, 107, 80);
    public static final int PAPER = Color.rgb(247, 244, 235), WHITE = Color.rgb(255, 254, 248);
    public static final int SAGE = Color.rgb(227, 235, 216), MUTED = Color.rgb(87, 105, 90);
    private UiKit() {}
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
        if (bold) result.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        result.setPadding(0, dp(context, 5), 0, dp(context, 5));
        return result;
    }
    public static Button button(Context context, String value, View.OnClickListener action) {
        Button result = new Button(context);
        result.setText(value); result.setAllCaps(false); result.setTextColor(INK);
        result.setTextSize(13); result.setMinHeight(dp(context, 48));
        result.setBackgroundTintList(android.content.res.ColorStateList.valueOf(SAGE));
        result.setOnClickListener(action); return result;
    }
    public static EditText input(Context context, String hint, int inputType) {
        EditText result = new EditText(context); result.setHint(hint); result.setTextSize(15);
        result.setTextColor(INK); result.setSingleLine(true); result.setInputType(inputType);
        result.setPadding(dp(context, 10), dp(context, 8), dp(context, 10), dp(context, 8));
        return result;
    }
    public static LinearLayout card(Context context) {
        LinearLayout result = column(context);
        result.setPadding(dp(context, 16), dp(context, 12), dp(context, 16), dp(context, 12));
        GradientDrawable background = new GradientDrawable(); background.setColor(WHITE);
        background.setCornerRadius(dp(context, 18)); background.setStroke(dp(context, 1), SAGE);
        result.setBackground(background);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.bottomMargin = dp(context, 12); result.setLayoutParams(params); return result;
    }
    public static void weighted(LinearLayout parent, View child) {
        parent.addView(child, new LinearLayout.LayoutParams(0, -2, 1));
    }
}
