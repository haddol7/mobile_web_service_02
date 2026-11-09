package com.haddol7.photoviewer.ui;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
public class MonitoringTimeTest {
    @Test public void preservesTimeZoneAndDateRollover(){
        assertEquals("11.09 01:30",MonitoringTime.format("2026-11-08T16:30:00.123456+00:00"));
        assertEquals("11.09 01:30",MonitoringTime.format("2026-11-09T01:30:00+09:00"));
        assertEquals("11.09 01:30",MonitoringTime.format("2026-11-08T16:30:00Z"));
    }
    @Test public void missingDatesAreNotInvented(){assertEquals("기록 없음",MonitoringTime.format(null));assertEquals("기록 없음",MonitoringTime.format("invalid"));}
}
