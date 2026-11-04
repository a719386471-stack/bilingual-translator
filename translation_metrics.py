"""Local timing only; never records prompts, translations, URLs or accounts."""
from contextlib import contextmanager
import time


@contextmanager
def timed_translation(lock, callback=None):
    started=time.monotonic()
    with lock:
        acquired=time.monotonic();generation=None
        def generating():
            nonlocal generation
            generation=time.monotonic()
        try:
            yield generating
        finally:
            ended=time.monotonic()
            if callback:
                callback({'queue_ms':round((acquired-started)*1000),
                          'setup_ms':round(((generation or ended)-acquired)*1000),
                          'generation_ms':round((ended-generation)*1000) if generation else 0})
