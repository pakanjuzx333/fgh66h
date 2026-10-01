from src.config.settings import settings
from src.llm.api_llm import GeminiLLM, OpenAILLM
from src.llm.local_llm import LocalLLM
class LLMRouter:
    def __init__(self):
        if settings.llm_mode == "local": self.backend = LocalLLM(); self.name = "local llama.cpp"
        elif settings.google_gemini_api_key: self.backend = GeminiLLM(); self.name = "Google Gemini"
        elif settings.openai_api_key: self.backend = OpenAILLM(); self.name = "OpenAI-compatible API"
        else: raise RuntimeError("API mode requires GOOGLE_GEMINI_API_KEY or OPENAI_API_KEY")
    async def generate(self, prompt, system_prompt): return await self.backend.generate(prompt, system_prompt)
