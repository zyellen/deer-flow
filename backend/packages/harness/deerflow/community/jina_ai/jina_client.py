import logging
import os

import httpx

logger = logging.getLogger(__name__)

_api_key_warned = False


class JinaClient:
    """Jina Reader 客户端：抓取网页并返回可供后续处理的文本内容。"""

    async def crawl(self, url: str, return_format: str = "html", timeout: int = 10) -> str:
        # 友好提示：未配置 API Key 时仅告警一次，避免日志重复刷屏。
        global _api_key_warned
        headers = {
            "Content-Type": "application/json",
            "X-Return-Format": return_format,
            "X-Timeout": str(timeout),
        }
        if os.getenv("JINA_API_KEY"):
            headers["Authorization"] = f"Bearer {os.getenv('JINA_API_KEY')}"
        elif not _api_key_warned:
            _api_key_warned = True
            logger.warning("Jina API key is not set. Provide your own key to access a higher rate limit. See https://jina.ai/reader for more information.")
        data = {"url": url}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("https://r.jina.ai/", headers=headers, json=data, timeout=timeout)

            if response.status_code != 200:
                error_message = f"Jina API returned status {response.status_code}: {response.text}"
                logger.error(error_message)
                return f"Error: {error_message}"

            if not response.text or not response.text.strip():
                error_message = "Jina API returned empty response"
                logger.error(error_message)
                return f"Error: {error_message}"

            return response.text
        except Exception as e:
            # 错误处理：捕获网络异常并返回可读错误，避免上层调用因未处理异常中断。
            error_message = f"Request to Jina API failed: {str(e)}"
            logger.exception(error_message)
            return f"Error: {error_message}"
