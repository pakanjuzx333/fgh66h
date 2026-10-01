from __future__ import annotations
import asyncio, logging
import google.generativeai as genai
from openai import AsyncOpenAI
from src.config.settings import settings
from src.llm.local_llm import DEFAULT, parse_decision
log = logging.getLogger(__name__)
class _ApiBase:
    async def _parse_with_retry(self, call, prompt, system_prompt):
        for attempt in range(2):
            try: return parse_decision(await call(prompt, system_prompt))
            except Exception as exc:
                log.warning("API LLM response invalid (attempt %s): %s", attempt + 1, exc)
                prompt += "\nReturn ONLY valid JSON, no Markdown."
        return DEFAULT.copy()
class GeminiLLM(_ApiBase):
    def __init__(self):
        genai.configure(api_key=settings.google_gemini_api_key); self.model = genai.GenerativeModel(settings.gemini_model)
    async def generate(self, prompt, system_prompt):
        async def call(p, s):
            response = await asyncio.to_thread(self.model.generate_content, f"{s}\n\n{p}", generation_config={"response_mime_type":"application/json"})
            return response.text
        return await self._parse_with_retry(call, prompt, system_prompt)
class OpenAILLM(_ApiBase):
    def __init__(self): self.client = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    async def generate(self, prompt, system_prompt):
        async def call(p, s):
            response = await self.client.chat.completions.create(model=settings.openai_model, messages=[{"role":"system","content":s},{"role":"user","content":p}], response_format={"type":"json_object"}, temperature=settings.local_temperature, max_tokens=settings.local_max_tokens)
            return response.choices[0].message.content or "{}"
        return await self._parse_with_retry(call, prompt, system_prompt)
