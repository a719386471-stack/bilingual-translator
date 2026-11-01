"""Retrieve public English captions; no browser cookies or video downloads."""
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
                transcript=YouTubeTranscriptApi(http_client=session).fetch(video_id,languages=['en','en-US','en-GB'])
                cues=[{'text':s.text,'start':s.start,'duration':s.duration} for s in transcript if s.text.strip()]
        except Exception as exc:
            kind=type(exc).__name__
            if kind in ('TranscriptsDisabled','NoTranscriptFound','VideoUnavailable','VideoUnplayable','AgeRestricted'):
                raise CaptionsError('此视频没有可公开读取的英文字幕，或当前访问受限。请尝试打开网页转录文稿。') from None
            raise CaptionsError('暂时无法读取 YouTube 英文字幕（%s），请检查网络后重试。' % kind,'connection',True) from None
        if not cues or len(cues)>15000:
            raise CaptionsError('字幕为空或超出当前支持的长度。')
        result={'cues':cues,'language':transcript.language_code}
        with self.lock:
            self.cache={k:v for k,v in self.cache.items() if v[0]>time.time()-900}
            self.cache[video_id]=(time.time(),result)
        return result
