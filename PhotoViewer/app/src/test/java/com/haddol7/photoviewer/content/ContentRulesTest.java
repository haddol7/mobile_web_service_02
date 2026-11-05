package com.haddol7.photoviewer.content;

import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;

public class ContentRulesTest {
    @Test public void confident_food_is_selected(){assertEquals("food",ThemeMapper.suggest(List.of(new ThemeMapper.Label(184,.95f))).theme());}
    @Test public void unknown_labels_abstain(){assertNull(ThemeMapper.suggest(List.of(new ThemeMapper.Label(999,.99f))).theme());}
    @Test public void weak_evidence_abstains(){assertNull(ThemeMapper.suggest(List.of(new ThemeMapper.Label(184,.64f))).theme());}
    @Test public void close_categories_abstain_and_show_alternatives(){var s=ThemeMapper.suggest(List.of(new ThemeMapper.Label(184,.8f),new ThemeMapper.Label(360,.75f)));assertNull(s.theme());assertEquals(2,s.alternatives().size());}
    @Test public void repeated_labels_do_not_sum_confidence(){var s=ThemeMapper.suggest(List.of(new ThemeMapper.Label(184,.6f),new ThemeMapper.Label(300,.6f),new ThemeMapper.Label(360,.9f)));assertEquals("animal",s.theme());}
    @Test public void invalid_scores_never_produce_suggestion(){assertNull(ThemeMapper.suggest(List.of(new ThemeMapper.Label(184,Float.NaN),new ThemeMapper.Label(66,Float.POSITIVE_INFINITY),new ThemeMapper.Label(20,-1))).theme());}
    @Test public void suggestions_have_at_most_five_unique_tags(){var labels=new ArrayList<ThemeMapper.Label>();for(int id:new int[]{5,10,48,50,117,126,181,184})labels.add(new ThemeMapper.Label(id,.9f));assertEquals(5,ThemeMapper.suggest(labels).tags().size());}
    @Test public void unicode_duplicate_tags_collapse_and_preserve_display(){assertEquals(List.of("ＣＡＦＥ","후기"),ThemeMapper.tags("ＣＡＦＥ, cafe, 후기,후기"));}
    @Test public void tags_allow_blank_and_limit_count(){assertTrue(ThemeMapper.tags(" , ").isEmpty());assertThrows(IllegalArgumentException.class,()->ThemeMapper.tags("0,1,2,3,4,5,6,7,8,9,10"));}
    @Test public void tag_limit_counts_code_points(){assertEquals(1,ThemeMapper.tags("😀".repeat(30)).size());assertThrows(IllegalArgumentException.class,()->ThemeMapper.tags("😀".repeat(31)));}
    @Test public void categories_keep_unclassified_distinct_from_other(){assertEquals("미분류",ThemeMapper.name(null));assertEquals("기타",ThemeMapper.name("other"));}
    @Test public void manual_rectangle_is_active_and_undo_removes_it(){MosaicDraft d=new MosaicDraft();d.add(.1f,.1f,.5f,.5f);assertTrue(d.regions().get(0).active);assertTrue(d.undo());assertTrue(d.regions().isEmpty());}
    @Test public void toggling_preserves_region_and_can_be_undone(){MosaicDraft d=new MosaicDraft();int i=d.add(.1f,.1f,.5f,.5f);d.update(i,d.regions().get(i).active(false));assertFalse(d.regions().get(i).active);d.undo();assertTrue(d.regions().get(i).active);}
    @Test public void reset_returns_to_entry_checkpoint(){MosaicDraft d=new MosaicDraft();d.add(.1f,.1f,.5f,.5f);d.checkpoint();d.remove(0);d.reset();assertEquals(1,d.regions().size());d.undo();assertTrue(d.regions().isEmpty());}
    @Test public void redetection_keeps_manual_rectangles(){MosaicDraft d=new MosaicDraft();d.add(.1f,.1f,.5f,.5f);d.detected(List.of(new MosaicDraft.Region("auto",.5f,.5f,.8f,.8f,true,true,1)));d.detected(List.of());assertEquals(1,d.regions().size());assertFalse(d.regions().get(0).automatic);}
    @Test public void exposed_regions_are_immutable_snapshots(){MosaicDraft d=new MosaicDraft();d.add(.1f,.1f,.5f,.5f);List<MosaicDraft.Region> saved=d.regions();assertThrows(UnsupportedOperationException.class,()->saved.clear());d.remove(0);assertEquals(1,saved.size());}
    @Test public void rectangle_rejects_invalid_bounds_and_strength(){assertThrows(IllegalArgumentException.class,()->new MosaicDraft.Region("x",Float.NaN,0,1,1,true,false,1));assertThrows(IllegalArgumentException.class,()->new MosaicDraft.Region("x",0,0,0,1,true,false,1));assertThrows(IllegalArgumentException.class,()->new MosaicDraft.Region("x",0,0,1,1,true,false,3));}
    @Test public void old_async_results_are_rejected_after_new_image_or_query(){GenerationGate gate=new GenerationGate();long old=gate.advance();assertTrue(gate.accepts(old));gate.advance();assertFalse(gate.accepts(old));assertTrue(gate.accepts(gate.current()));}
}
