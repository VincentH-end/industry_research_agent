import json
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import Settings
from .context import active_context
from .telemetry import record_event

T = TypeVar("T", bound=BaseModel)


class StructuredLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(
            api_key=settings.llm_api_key or "demo-key",
            base_url=settings.llm_base_url,
        )

    async def generate(self, system: str, prompt: str, schema: type[T]) -> T:
        manager = active_context.get()
        notes = manager.compose() if manager else ""
        if len(prompt) > self.settings.prompt_max_chars:
            # Do not silently discard instructions, source IDs or evidence boundaries.
            raise ValueError("Prompt exceeds PROMPT_MAX_CHARS; reduce source count or excerpts")
        if notes:
            prompt += "\n" + notes
        record_event("llm.started", schema=schema.__name__, input_chars=len(prompt), context_chars=len(notes))
        response = await self.client.chat.completions.create(
            model=self.settings.llm_model,
            temperature=0.15,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": prompt
                    + "\nJSON Schema:\n"
                    + json.dumps(schema.model_json_schema(), ensure_ascii=False),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        record_event("llm.completed", schema=schema.__name__, output_chars=len(content),
                     total_tokens=getattr(response.usage, "total_tokens", None))
        return schema.model_validate_json(content)
