import time
import abc
import logging
from typing import Optional
import requests
from config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class RateLimitError(LLMError):
    """Raised when an LLM provider returns a rate limit (HTTP 429 or quota exceeded)."""
    pass


class LLMClient(abc.ABC):
    """
    Abstract Base Class for LLM providers.
    Enforces a uniform `generate(prompt) -> str` interface, 5-second inter-call delay,
    and exponential backoff retry on rate-limit errors.
    """

    def __init__(
        self,
        call_delay: float = settings.LLM_CALL_DELAY_SECONDS,
        max_retries: int = settings.LLM_MAX_RETRIES,
        backoff_factor: float = settings.LLM_BACKOFF_FACTOR
    ):
        self.call_delay = call_delay
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._last_call_time: float = 0.0

    def _enforce_call_delay(self) -> None:
        """Enforces minimum delay between consecutive LLM calls."""
        if self._last_call_time > 0:
            elapsed = time.time() - self._last_call_time
            if elapsed < self.call_delay:
                sleep_needed = self.call_delay - elapsed
                logger.info(f"Pacing LLM calls: sleeping for {sleep_needed:.2f}s")
                time.sleep(sleep_needed)
        self._last_call_time = time.time()

    def generate(self, prompt: str) -> str:
        """
        Public method to generate a response from the LLM.
        Applies delay pacing and exponential backoff retry on rate-limit errors.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty")

        attempts = 0
        backoff = 2.0

        while True:
            self._enforce_call_delay()
            try:
                attempts += 1
                return self._call(prompt)
            except RateLimitError as e:
                if attempts > self.max_retries:
                    logger.error(f"Exceeded max retries ({self.max_retries}) on rate limit: {e}")
                    raise
                logger.warning(
                    f"Rate limit encountered (attempt {attempts}/{self.max_retries}). "
                    f"Backing off for {backoff:.2f}s..."
                )
                time.sleep(backoff)
                backoff *= self.backoff_factor

    @abc.abstractmethod
    def _call(self, prompt: str) -> str:
        """Subclasses must implement the actual provider API call here."""
        pass


class GeminiClient(LLMClient):
    """Gemini client using google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL

        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please add it to your .env file or environment."
            )

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            raise LLMError(f"Failed to initialize google-genai client: {e}") from e

    def _call(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            if not response or not response.text:
                raise LLMError("Gemini returned an empty response")
            return response.text.strip()
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "rate limit" in err_str or "resource_exhausted" in err_str:
                raise RateLimitError(f"Gemini rate limit exceeded: {e}") from e
            raise LLMError(f"Gemini generation error: {e}") from e


class OllamaClient(LLMClient):
    """Ollama client communicating over local REST API (default localhost:11434)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 60.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.OLLAMA_MODEL
        self.timeout = timeout

    def _call(self, prompt: str) -> str:
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post(endpoint, json=payload, timeout=self.timeout)
            if response.status_code == 429:
                raise RateLimitError(f"Ollama rate limit (HTTP 429): {response.text}")
            if response.status_code != 200:
                raise LLMError(
                    f"Ollama HTTP {response.status_code} error from {endpoint}: {response.text}"
                )

            data = response.json()
            output = data.get("response")
            if output is None:
                raise LLMError(f"Unexpected Ollama response payload: {data}")
            return output.strip()
        except requests.exceptions.RequestException as e:
            err_str = str(e).lower()
            if "429" in err_str:
                raise RateLimitError(f"Ollama rate limit: {e}") from e
            raise LLMError(f"Could not connect to Ollama at {endpoint}: {e}") from e


def get_llm_client() -> LLMClient:
    """Factory function returning the configured LLM client according to LLM_PROVIDER."""
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider == "gemini":
        return GeminiClient()
    elif provider == "ollama":
        return OllamaClient()
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. Must be 'gemini' or 'ollama'."
        )
