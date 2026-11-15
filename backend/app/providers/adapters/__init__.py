from .base import Adapter
from .gemini import GeminiAdapter
from .mock import MockAdapter
from .ollama import OllamaAdapter
from .openai import OpenAIAdapter
from .recraft import RecraftAdapter

ADAPTERS: dict[str, Adapter] = {a.service: a for a in (OpenAIAdapter(), RecraftAdapter(), GeminiAdapter(), OllamaAdapter(), MockAdapter())}
