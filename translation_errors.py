"""Safe, structured translation failures; never return raw upstream payloads."""
class TranslationError(Exception):
    def __init__(self, message, code='request_failed', retryable=False, retry_after=0):
        super().__init__(message)
        self.code=code
        self.retryable=retryable
        self.retry_after=retry_after

    def public(self):
        return {'error':str(self),'errorCode':self.code,'retryable':self.retryable}


def upstream_error(message, prefix='翻译服务'):
    """Classify transport faults without exposing raw model/account error text."""
    text=str(message).lower()
    if any(x in text for x in ('quota','exhaust','usage limit','subscription_sharing','额度')):
        return TranslationError(prefix+'额度暂不可用，请查看剩余额度或切换来源。','quota')
    if any(x in text for x in ('unauthorized','authentication','sign in','log in','login','token expired','登录')):
        return TranslationError(prefix+'登录需要更新，请在面板检查账号连接。','auth')
    if any(x in text for x in ('429','rate limit','overload','503','502','504','temporarily unavailable','capacity')):
        return TranslationError(prefix+'暂时繁忙，正在等待重试。','busy',True,8)
    if any(x in text for x in ('timeout','timed out','超时','connect','network','socket','transport','stream','eof','reset','closed','退出','断开','中断','unavailable')):
        return TranslationError(prefix+'连接暂时中断。','connection',True)
    return TranslationError(prefix+'未完成请求，请重试或切换模型。')
