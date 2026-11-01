import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from youtube_captions import CaptionStore,align_manual_chinese


def fetched(language,*rows):
 class Track(list):pass
 result=Track(SimpleNamespace(text=t,start=s,duration=d) for t,s,d in rows)
 result.language_code=language
 return result

class NativeCaptionTests(unittest.TestCase):
 def test_alignment_uses_overlap_not_array_position_and_keeps_gaps_empty(self):
  english=[{'text':'A','start':0,'duration':2},{'text':'B','start':2,'duration':2},{'text':'C','start':8,'duration':2}]
  chinese=[{'text':'第一句话','start':0,'duration':4},{'text':'间隔之后','start':12,'duration':2}]
  self.assertEqual(align_manual_chinese(english,chinese),['第一句话','第一句话',''])
 def test_target_segments_can_be_joined_without_moving_source_timestamps(self):
  en=[{'text':'One longer English sentence.','start':1,'duration':5}]
  zh=[{'text':'中文前半句','start':1,'duration':2},{'text':'后半句','start':3,'duration':3}]
  self.assertEqual(align_manual_chinese(en,zh),['中文前半句 后半句'])
 def test_manual_track_is_optional_and_generated_track_is_rejected(self):
  english=fetched('en',('Interest rose.',0,2))
  with patch('youtube_captions.YouTubeTranscriptApi') as api:
   tracks=api.return_value.list.return_value;tracks.find_transcript.return_value.fetch.return_value=english
   tracks.find_manually_created_transcript.return_value.is_generated=True
   result=CaptionStore().fetch('abcdefghijk')
   self.assertNotIn('nativeChinese',result)
   tracks.find_manually_created_transcript.return_value.fetch.assert_not_called()
 def test_manual_track_fetch_failure_does_not_fail_english(self):
  english=fetched('en',('Interest rose.',0,2))
  with patch('youtube_captions.YouTubeTranscriptApi') as api:
   tracks=api.return_value.list.return_value;tracks.find_transcript.return_value.fetch.return_value=english
   tracks.find_manually_created_transcript.side_effect=RuntimeError('not available')
   result=CaptionStore().fetch('abcdefghijk')
   self.assertEqual(result['language'],'en');self.assertEqual(result['cues'][0]['text'],'Interest rose.')
 def test_english_and_manual_chinese_share_one_listing_and_cache(self):
  english=fetched('en',('Interest rose.',0,2),('A bank.',2,2))
  chinese=fetched('zh-Hans',('利率上升。',0,2),('一家银行。',2,2))
  with patch('youtube_captions.YouTubeTranscriptApi') as api:
   tracks=api.return_value.list.return_value;tracks.find_transcript.return_value.fetch.return_value=english
   manual=tracks.find_manually_created_transcript.return_value
   manual.is_generated=False;manual.language_code='zh-Hans';manual.fetch.return_value=chinese
   store=CaptionStore();result=store.fetch('abcdefghijk');same=store.fetch('abcdefghijk')
   self.assertIs(result,same);api.return_value.list.assert_called_once_with('abcdefghijk')
   self.assertEqual(result['nativeChinese'],{'source':'manual','language':'zh-Hans','translations':['利率上升。','一家银行。'],'cues':[{'text':'利率上升。','start':0,'duration':2},{'text':'一家银行。','start':2,'duration':2}]})
   manual.translate.assert_not_called()

if __name__=='__main__':unittest.main()
