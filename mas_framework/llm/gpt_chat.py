import aiohttp
from typing import List, Union, Optional
from tenacity import retry, wait_random_exponential, stop_after_attempt
from typing import Dict, Any
from dotenv import load_dotenv
import os

from mas_framework.llm.format import Message
from mas_framework.llm.price import cost_count_from_usage
from mas_framework.llm.llm import LLM
from mas_framework.llm.llm_registry import LLMRegistry

load_dotenv()  # 加载.env文件
MINE_BASE_URL = os.getenv("BASE_URL")
MINE_API_KEY = os.getenv("API_KEY")
from openai import OpenAI, AsyncOpenAI


@retry(wait=wait_random_exponential(max=100), stop=stop_after_attempt(3))
async def achat(
        model: str,
        msg: List[Dict],
        max_tokens: Optional[int] = None,  # 限制最大输出长度
        temperature: Optional[float] = 0.,
        num_comps: Optional[int] = 1,
):
    client = AsyncOpenAI(base_url=MINE_BASE_URL, api_key=MINE_API_KEY, timeout=120,max_retries=1, )  # 创建客户端：拿 .env 里的地址和 key，构造一个 OpenAI 兼容客户端

    # 真正发送请求：把消息 msg 发给指定模型 model，拿回返回结果
    chat_completion = await client.chat.completions.create(
        messages=msg, 
        model=model, 
        max_tokens=max_tokens,
        temperature=temperature
    )
    # # 新增开始
    # print("DEBUG type:", type(chat_completion))
    # print("DEBUG obj:", chat_completion)
    # # 新增结束

    if chat_completion.usage:  # 拿token用量：从 API 返回中取出 token 数，交给 price.py 去统计成本
        prompt_tokens = chat_completion.usage.prompt_tokens
        completion_tokens = chat_completion.usage.completion_tokens
        cost_count_from_usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, model_name=model)

    try:
        response = chat_completion.choices[0].message.content  # 拿到llm的实际回复文本
    except Exception as e:
        print("DEBUG parse error:", repr(e))
        print("DEBUG raw response:", chat_completion)
        raise

    return response


@LLMRegistry.register('GPTChat')
class GPTChat(LLM):

    def __init__(self, model_name: str):
        self.model_name = model_name

    async def agen(  # 上层 agent 实际调用的入口
            self,
            messages: List[Message],
            max_tokens: Optional[int] = None,
            temperature: Optional[float] = None,
            num_comps: Optional[int] = None,
    ) -> Union[List[str], str]:

        if max_tokens is None:
            max_tokens = self.DEFAULT_MAX_TOKENS
        if temperature is None:
            temperature = self.DEFAULT_TEMPERATURE
        if num_comps is None:
            num_comps = self.DEFUALT_NUM_COMPLETIONS

        if isinstance(messages, str):
            messages = [Message(role="user", content=messages)]
        return await achat(self.model_name, messages)  # agent → GPTChat.agen(...) → achat(...) → OpenAI API

    def gen(
            self,
            messages: List[Message],
            max_tokens: Optional[int] = None,
            temperature: Optional[float] = None,
            num_comps: Optional[int] = None,
    ) -> Union[List[str], str]:
        pass
