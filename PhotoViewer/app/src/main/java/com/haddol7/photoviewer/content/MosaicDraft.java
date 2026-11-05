package com.haddol7.photoviewer.content;

import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

/** Immutable normalized regions; history never contains image pixels. */
public final class MosaicDraft {
    public static final class Region {
        public final String id;
        public final float left, top, right, bottom;
        public final boolean active, automatic;
        public final int strength;
        public Region(String id, float left, float top, float right, float bottom, boolean active, boolean automatic, int strength) {
            if (id == null || !Float.isFinite(left) || !Float.isFinite(top) || !Float.isFinite(right) || !Float.isFinite(bottom)
                    || left < 0 || top < 0 || right > 1 || bottom > 1 || right <= left || bottom <= top || strength < 0 || strength > 2)
                throw new IllegalArgumentException("가릴 영역의 범위를 확인하세요.");
            this.id=id; this.left=left; this.top=top; this.right=right; this.bottom=bottom;
            this.active=active; this.automatic=automatic; this.strength=strength;
        }
        public Region bounds(float l,float t,float r,float b) { return new Region(id,l,t,r,b,active,automatic,strength); }
        public Region active(boolean value) { return new Region(id,left,top,right,bottom,value,automatic,strength); }
        public Region strength(int value) { return new Region(id,left,top,right,bottom,active,automatic,value); }
    }
    private List<Region> regions=new ArrayList<>(), baseline=new ArrayList<>();
    private final ArrayDeque<List<Region>> undo=new ArrayDeque<>();
    public List<Region> regions() { return Collections.unmodifiableList(new ArrayList<>(regions)); }
    private void remember() { undo.push(new ArrayList<>(regions)); while(undo.size()>40)undo.removeLast(); }
    public void replace(List<Region> value) { remember(); regions=new ArrayList<>(value); }
    public void checkpoint() { baseline=new ArrayList<>(regions); undo.clear(); }
    public void reset() { remember(); regions=new ArrayList<>(baseline); }
    public boolean undo() { if(undo.isEmpty())return false; regions=undo.pop(); return true; }
    public int add(float l,float t,float r,float b) {
        Region region=new Region(UUID.randomUUID().toString(),l,t,r,b,true,false,1);
        if(regions.size()>=100)throw new IllegalArgumentException("가리기 영역은 최대 100개입니다.");
        remember(); regions.add(region); return regions.size()-1;
    }
    public void update(int index,Region region) { if(index<0||index>=regions.size())return; remember(); regions.set(index,region); }
    public void remove(int index) { if(index<0||index>=regions.size())return; remember(); regions.remove(index); }
    public void detected(List<Region> faces) {
        List<Region> result=new ArrayList<>();
        for(Region r:regions)if(!r.automatic)result.add(r);
        for(Region r:faces)if(result.size()<100)result.add(r);
        replace(result);
    }
}
