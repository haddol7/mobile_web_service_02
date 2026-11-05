package com.haddol7.photoviewer.content;

import android.graphics.*;
import android.test.InstrumentationTestCase;
import java.io.*;
import java.util.*;
import org.json.*;

/** Optional real-image diagnostic. Input and recognized private text stay in app-private cache. */
@SuppressWarnings("deprecation")
public final class RecognitionQualityTest extends InstrumentationTestCase {
    public void testCorpus() throws Exception {
        File folder=new File(getInstrumentation().getTargetContext().getCacheDir(),"quality");
        assertTrue("Copy consented fixtures to the private quality cache first",folder.isDirectory());
        JSONArray rows=new JSONArray();
        try(VisionEngine engine=new VisionEngine()){
            File[] files=folder.listFiles((dir,name)->name.endsWith(".jpg")||name.endsWith(".png"));
            assertNotNull(files);Arrays.sort(files);
            for(File file:files){
                Bitmap bitmap=BitmapFactory.decodeFile(file.getAbsolutePath());assertNotNull(bitmap);
                long start=android.os.SystemClock.elapsedRealtime();
                VisionEngine.Analysis result=engine.analyze(bitmap);JSONArray lines=new JSONArray();
                for(VisionEngine.Line line:result.lines()){
                    JSONArray q=new JSONArray();for(float coordinate:line.quad)q.put(coordinate);
                    lines.put(new JSONObject().put("text",line.text).put("included",line.included).put("quad",q));
                }
                JSONArray faces=new JSONArray();for(MosaicDraft.Region r:engine.faces(bitmap))faces.put(new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom));
                rows.put(new JSONObject().put("file",file.getName()).put("lines",lines).put("faces",faces).put("milliseconds",android.os.SystemClock.elapsedRealtime()-start));
                bitmap.recycle();
            }
        }
        try(FileOutputStream out=new FileOutputStream(new File(folder,"results.json"))){out.write(rows.toString(2).getBytes(java.nio.charset.StandardCharsets.UTF_8));}
        assertTrue(rows.length()>0);
    }
}
