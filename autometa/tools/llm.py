import asyncio
import json
import logging
import re
from functools import lru_cache
from typing import List

import httpx
import tenacity
from openai import AsyncOpenAI, OpenAI

from autometa.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def _get_sync_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(
            timeout=180,
            limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        ),
    )


@lru_cache(maxsize=16)
def _get_async_client(api_key: str, base_url: str) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.AsyncClient(
            timeout=180,
            limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
        ),
    )


def _resolve_clients() -> tuple[OpenAI, AsyncOpenAI]:
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value()
    if not api_key:
        raise ValueError("LLM API key is empty. Please configure LLM_API_KEY.")

    return (
        _get_sync_client(api_key, settings.llm_base_url),
        _get_async_client(api_key, settings.llm_base_url),
    )


@tenacity.retry(
    retry=tenacity.retry_if_not_exception_type(TimeoutError),
    wait=tenacity.wait_random_exponential(min=1, max=20),
    stop=tenacity.stop_after_attempt(5),
    reraise=True,
)
def _call_sync(messages: list, temperature: float = 0.0, model: str = None, **kwargs):
    model_name = model or get_settings().llm_model
    sync_client, _ = _resolve_clients()
    return sync_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )


@tenacity.retry(
    retry=tenacity.retry_if_not_exception_type(TimeoutError),
    wait=tenacity.wait_random_exponential(min=1, max=20),
    stop=tenacity.stop_after_attempt(5),
    reraise=True,
)
async def _call_async(
    messages: list, temperature: float = 0.0, model: str = None, **kwargs
):
    model_name = model or get_settings().llm_model
    _, async_client = _resolve_clients()
    return await async_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )


def _prompt_to_messages(prompt_template: str, inputs: dict) -> list:
    content = prompt_template.format(**inputs)
    return [{"role": "user", "content": content}]


def _clean_content(text: str) -> str:

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


async def _gather_text(
    messages_list: list,
    temperature: float = 0.0,
    max_concurrency: int = 50,
    model: str = None,
    **kwargs,
) -> list:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _call_with_sem(msgs):
        async with semaphore:
            return await _call_async(
                msgs, temperature=temperature, model=model, **kwargs
            )

    return await asyncio.gather(*[_call_with_sem(msgs) for msgs in messages_list])


async def _gather_tools(
    messages_list: list,
    tools: list,
    temperature: float = 0.0,
    max_concurrency: int = 50,
    model: str = None,
) -> list:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _call_with_sem(msgs):
        async with semaphore:
            return await _call_async(
                msgs, tools=tools, temperature=temperature, model=model
            )

    return await asyncio.gather(*[_call_with_sem(msgs) for msgs in messages_list])


def _run_async(coro):

    from concurrent.futures import ThreadPoolExecutor

    try:
        asyncio.get_running_loop()

        with ThreadPoolExecutor(1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()
    except RuntimeError:
        return asyncio.run(coro)


def call_llm(
    prompt_template: str,
    inputs: dict,
    temperature: float = 0.0,
    model: str = None,
    **kwargs,
) -> str:

    messages = _prompt_to_messages(prompt_template, inputs)
    response = _call_sync(messages, temperature=temperature, model=model, **kwargs)
    return _clean_content(response.choices[0].message.content)


def call_llm_messages(
    messages: list,
    temperature: float = 0.0,
    model: str = None,
    **kwargs,
) -> str:

    response = _call_sync(messages, temperature=temperature, model=model, **kwargs)
    return _clean_content(response.choices[0].message.content)


def function_call_llm(
    prompt_template: str,
    inputs: dict,
    tool: dict,
    temperature: float = 0.0,
    model: str = None,
) -> dict:

    messages = _prompt_to_messages(prompt_template, inputs)
    response = _call_sync(
        messages,
        tools=[tool],
        temperature=temperature,
        model=model,
    )
    try:
        tool_calls = response.choices[0].message.tool_calls
        if tool_calls:
            return json.loads(tool_calls[0].function.arguments)
        content = _clean_content(response.choices[0].message.content)
        return json.loads(content)
    except Exception:
        logger.exception("function_call_llm failed to parse model output")
        return {}


def batch_call_llm(
    prompt_template: str,
    batch_inputs: list,
    temperature: float = 0.0,
    max_concurrency: int = 50,
    model: str = None,
    **kwargs,
) -> List[str]:

    all_messages = [_prompt_to_messages(prompt_template, inp) for inp in batch_inputs]
    results = _run_async(
        _gather_text(
            all_messages,
            temperature=temperature,
            max_concurrency=max_concurrency,
            model=model,
            **kwargs,
        )
    )
    return [_clean_content(r.choices[0].message.content) for r in results]


def batch_function_call_llm(
    prompt_template: str,
    batch_inputs: list,
    tool: dict,
    temperature: float = 0.0,
    max_concurrency: int = 50,
    model: str = None,
) -> List[dict]:

    tools = [tool]
    all_messages = [_prompt_to_messages(prompt_template, inp) for inp in batch_inputs]
    results = _run_async(
        _gather_tools(
            all_messages,
            tools=tools,
            temperature=temperature,
            max_concurrency=max_concurrency,
            model=model,
        )
    )

    parsed = []
    for r in results:
        try:
            tool_calls = r.choices[0].message.tool_calls
            if tool_calls:
                parsed.append(json.loads(tool_calls[0].function.arguments))
            else:
                content = _clean_content(r.choices[0].message.content)
                parsed.append(json.loads(content))
        except Exception:
            parsed.append({})
    return parsed
