import time
from unittest.mock import MagicMock, patch
import pytest

from llm import (
    LLMClient,
    GeminiClient,
    OllamaClient,
    RateLimitError,
    LLMError,
    get_llm_client
)


class DummyLLM(LLMClient):
    """Concrete subclass for testing abstract LLMClient pacing & backoff."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.call_count = 0
        self.should_fail_times = 0

    def _call(self, prompt: str) -> str:
        self.call_count += 1
        if self.call_count <= self.should_fail_times:
            raise RateLimitError("Mocked rate limit exceeded (429)")
        return f"Echo: {prompt}"


def test_llm_empty_prompt():
    client = DummyLLM()
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        client.generate("")


def test_llm_rate_limit_retry_success():
    client = DummyLLM(call_delay=0.01, max_retries=3, backoff_factor=1.5)
    client.should_fail_times = 2

    with patch("time.sleep") as mock_sleep:
        response = client.generate("hello test")
        assert response == "Echo: hello test"
        assert client.call_count == 3
        # Should have backed off twice
        assert mock_sleep.call_count >= 2


def test_llm_rate_limit_exceeded():
    client = DummyLLM(call_delay=0.01, max_retries=2, backoff_factor=1.5)
    client.should_fail_times = 5  # more than max_retries

    with patch("time.sleep"):
        with pytest.raises(RateLimitError):
            client.generate("fail prompt")
    assert client.call_count == 3  # initial + 2 retries


def test_llm_call_delay_enforced():
    client = DummyLLM(call_delay=0.1)
    t0 = time.time()
    client.generate("call 1")
    client.generate("call 2")
    elapsed = time.time() - t0
    # Must have waited at least 0.1s between the two calls
    assert elapsed >= 0.09


def test_gemini_client_mock():
    with patch("google.genai.Client") as mock_genai_cls:
        mock_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Hello from mocked Gemini!"
        mock_instance.models.generate_content.return_value = mock_response
        mock_genai_cls.return_value = mock_instance

        client = GeminiClient(api_key="fake-test-key", model_name="gemini-2.5-flash", call_delay=0.0)
        output = client.generate("say hello")

        assert output == "Hello from mocked Gemini!"
        mock_instance.models.generate_content.assert_called_once_with(
            model="gemini-2.5-flash",
            contents="say hello"
        )


def test_gemini_client_missing_key():
    with patch("config.settings.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
            GeminiClient(api_key=None)


def test_ollama_client_mock():
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Hello from mocked Ollama!"}
        mock_post.return_value = mock_response

        client = OllamaClient(
            base_url="http://localhost:11434",
            model_name="llama3.2",
            call_delay=0.0
        )
        output = client.generate("say hello")

        assert output == "Hello from mocked Ollama!"
        mock_post.assert_called_once_with(
            "http://localhost:11434/api/generate",
            json={"model": "llama3.2", "prompt": "say hello", "stream": False},
            timeout=60.0
        )


def test_ollama_client_rate_limit():
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit hit"
        mock_post.return_value = mock_response

        client = OllamaClient(call_delay=0.0, max_retries=1)
        with patch("time.sleep"):
            with pytest.raises(RateLimitError):
                client.generate("hello")


def test_get_llm_client_factory():
    with patch("config.settings.LLM_PROVIDER", "gemini"), \
         patch("config.settings.GEMINI_API_KEY", "test-key"), \
         patch("google.genai.Client"):
        client = get_llm_client()
        assert isinstance(client, GeminiClient)

    with patch("config.settings.LLM_PROVIDER", "ollama"):
        client = get_llm_client()
        assert isinstance(client, OllamaClient)

    with patch("config.settings.LLM_PROVIDER", "unknown"):
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            get_llm_client()
