package com.haddol7.photoviewer.content;

import java.text.Normalizer;
import java.util.*;

/** Curated subset of Google's published base-model indices; no custom training. */
public final class ThemeMapper {
    public static final String VERSION="theme_mapping_v1";
    public static final String[] IDS={"food","animal","nature","people","space","object","other"};
    public static final String[] NAMES={"음식","동물","자연·풍경","인물","건축·공간","사물","기타"};
    public record Label(int index,float confidence) {}
    public record Ranked(String theme,float score) {}
    public record Suggestion(String theme,List<String> tags,List<Ranked> alternatives) {}
    private record Entry(String theme,String tag) {}
    private static final Map<Integer,Entry> MAP=new HashMap<>();
    private static void group(String theme,String... entries) {
        for(String value:entries){int split=value.indexOf(':'); MAP.put(Integer.parseInt(value.substring(0,split)),new Entry(theme,value.substring(split+1)));}
    }
    static {
        // https://developers.google.com/ml-kit/vision/image-labeling/label-map
        group("food","5:도시락","10:햄버거","48:패스트푸드","50:핫도그","117:요리","119:주스","126:쿠키","162:아이스크림","181:커피","184:음식","187:과일","188:쌀국수","276:피자","300:초밥","331:카푸치노","332:빵","388:채소","393:케이크","428:식사","433:파이");
        group("animal","20:새","33:물고기","35:강아지","55:작은동물","61:곰","113:소","118:고양이","174:물새","178:강아지","183:고양이","213:말","223:곤충","268:펭귄","277:반려동물","338:오리","340:거북","341:악어","360:강아지","372:나비","400:물범","405:고양이");
        group("nature","4:빙산","22:공원","27:나뭇가지","28:꽃잎","39:절벽","49:노을","54:하늘","114:정글","145:모래언덕","150:사막","193:숲","202:빙하","205:식물","241:호수","254:달","266:식물","284:강","309:화산","333:모래","337:산","353:해변","354:무지개","357:정원","359:들판","362:꽃","378:오로라","397:안개","408:초원","417:폭포","427:협곡");
        group("people","66:사람","207:인물","218:여러사람","421:아기","439:셀카");
        group("space","18:다리","24:공장","43:경기장","63:탑","72:욕실","88:계단","110:교회","123:도시풍경","154:침실","171:기념물","208:유적","235:사원","242:등대","270:궁전","289:실내","308:고층건물","335:박물관","365:성당","366:건물","371:사찰","376:주방","377:성","441:헛간");
        group("object","8:장난감","9:조각상","42:자전거","89:컴퓨터","92:의자","93:포스터","111:시계","115:책상","125:인형","157:소파","160:화이트보드","251:악기","257:휴대전화","263:신문","265:피아노","273:종이","315:컵","317:가방","367:비행기","401:선반","410:우산","423:자동차");
    }
    public static String name(String id) { for(int i=0;i<IDS.length;i++)if(IDS[i].equals(id))return NAMES[i];return "미분류"; }
    public static Suggestion suggest(List<Label> labels) {
        Map<String,Float> scores=new HashMap<>(); Map<String,Float> tags=new HashMap<>();
        for(Label label:labels) {
            if(!Float.isFinite(label.confidence)||label.confidence<0||label.confidence>1)continue;
            Entry e=MAP.get(label.index); if(e==null)continue;
            scores.merge(e.theme,label.confidence,Math::max);
            if(label.confidence>=.60f)tags.merge(e.tag,label.confidence,Math::max);
        }
        List<Ranked> ranks=new ArrayList<>(); scores.forEach((key,value)->ranks.add(new Ranked(key,value)));
        ranks.sort(Comparator.comparingDouble((Ranked r)->-r.score).thenComparing(Ranked::theme));
        String theme=null;
        if(!ranks.isEmpty()&&ranks.get(0).score>=.65f&&(ranks.size()==1||ranks.get(0).score-ranks.get(1).score>=.12f))theme=ranks.get(0).theme;
        List<String> selected=new ArrayList<>(tags.keySet());
        selected.sort(Comparator.comparingDouble((String key)->-tags.get(key)).thenComparing(key->key));
        return new Suggestion(theme,new ArrayList<>(selected.subList(0,Math.min(5,selected.size()))),new ArrayList<>(ranks.subList(0,Math.min(3,ranks.size()))));
    }
    public static List<String> tags(String input) {
        Map<String,String> unique=new LinkedHashMap<>();
        for(String value:input.split(",")) {
            String display=value.trim().replaceAll("\\s+"," "); if(display.isEmpty())continue;
            if(display.codePointCount(0,display.length())>30||display.codePoints().anyMatch(c->Character.isISOControl(c)))throw new IllegalArgumentException("태그는 제어문자 없이 30문자 이하여야 합니다.");
            String key=Normalizer.normalize(display,Normalizer.Form.NFKC).toLowerCase(Locale.ROOT);
            unique.putIfAbsent(key,display);
        }
        if(unique.size()>10)throw new IllegalArgumentException("태그는 최대 10개입니다.");
        return new ArrayList<>(unique.values());
    }
}
