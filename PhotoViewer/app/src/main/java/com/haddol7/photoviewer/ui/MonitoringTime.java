package com.haddol7.photoviewer.ui;

/** ISO timestamps displayed in Korea time, including on Android API 24. */
public final class MonitoringTime {
    private MonitoringTime() {}
    public static String format(String value) {
        try {
            java.text.SimpleDateFormat parser = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX",java.util.Locale.ROOT);
            parser.setLenient(false);
            java.util.Date date=parser.parse(value.replaceFirst("\\.\\d+", ""));
            java.text.SimpleDateFormat display=new java.text.SimpleDateFormat("MM.dd HH:mm",java.util.Locale.KOREA);
            display.setTimeZone(java.util.TimeZone.getTimeZone("Asia/Seoul"));
            return display.format(date);
        } catch (Exception ignored) { return "기록 없음"; }
    }
}
