"""Retrieve public English and optional manual Chinese captions without cookies."""
import re
import threading
import time
from urllib.request import getproxies

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from translation_errors import TranslationError


class CaptionsError(TranslationError):
    pass


class TimedSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.deadline=time.monotonic()+20
        self.proxies.update({k:v for k,v in getproxies().items() if k in ('http','https')})

    def request(self,*args,**kwargs):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:
            raise requests.Timeout('caption retrieval deadline')
        kwargs['timeout']=min(8,remaining)
        return super().request(*args,**kwargs)


def align_manual_chinese(english, chinese):
    """Pair original tracks by meaningful time overlap; uncovered English stays empty.

    Never request YouTube machine translation or fabricate a target for a gap.
    A short original fragment may overlap one complete Chinese subtitle; repeating
    that same subtitle across those fragments preserves the track's own timing.
    """
    result=[]
    left=0
    for cue in english:
        start=cue['start'];end=start+max(0.05,cue['duration'])
        while left<len(chinese) and chinese[left]['start']+chinese[left]['duration']<=start:
            left+=1
        matches=[]
        right=left
        while right<len(chinese):
            target=chinese[right]
            if target['start']>=end:break
            right+=1
            duration=max(0.05,target['duration'])
            overlap=min(end,target['start']+duration)-max(start,target['start'])
            if overlap>=min(end-start,duration)*0.35 and overlap>=0.05:
                value=target['text'].strip()
                if value and (not matches or matches[-1]!=value):matches.append(value)
        value=' '.join(matches)
        result.append(value if len(value)<=12000 else '')
    return result


class CaptionStore:
    def __init__(self):
        self.cache={}
        self.lock=threading.Lock()

    def fetch(self,video_id):
        if not isinstance(video_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):
            raise CaptionsError('YouTube 视频编号无效。')
        with self.lock:
            cached=self.cache.get(video_id)
            if cached and cached[0]>time.time()-900:
                return cached[1]
        try:
            with TimedSession() as session:
                tracks=YouTubeTranscriptApi(http_client=session).list(video_id)
                transcript=tracks.find_transcript(['en','en-US','en-GB']).fetch()
                cues=[{'text':s.text,'start':s.start,'duration':s.duration} for s in transcript if s.text.strip()]
                native=None
                try:
                    track=tracks.find_manually_created_transcript(['zh-Hans','zh-CN','zh','zh-TW','zh-Hant','zh-HK'])
                    # Defense in depth: only a direct, manually-created Chinese track.
                    if not track.is_generated and track.language_code in ('zh-Hans','zh-CN','zh','zh-TW','zh-Hant','zh-HK'):
                        raw=track.fetch()
                        chinese=[{'text':s.text,'start':s.start,'duration':s.duration} for s in raw if s.text.strip()]
                        if chinese and len(chinese)<=15000:
                            native={'language':track.language_code,'source':'manual',
                                    'translations':align_manual_chinese(cues,chinese),
                                    'cues':chinese}
                except Exception:
                    # Optional track absence/failure cannot make English retrieval fail.
                    pass
        except Exception as exc:
            kind=type(exc).__name__
            if kind in ('TranscriptsDisabled','NoTranscriptFound','VideoUnavailable','VideoUnplayable','AgeRestricted'):
                raise CaptionsError('此视频没有可公开读取的英文字幕，或当前访问受限。请尝试打开网页转录文稿。') from None
            raise CaptionsError('暂时无法读取 YouTube 英文字幕（%s），请检查网络后重试。' % kind,'connection',True) from None
        if not cues or len(cues)>15000:
            raise CaptionsError('字幕为空或超出当前支持的长度。')
        result={'cues':cues,'language':transcript.language_code}
        if native and any(native['translations']):result['nativeChinese']=native
        with self.lock:
            self.cache={k:v for k,v in self.cache.items() if v[0]>time.time()-900}
            self.cache[video_id]=(time.time(),result)
        return result
