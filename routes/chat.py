#=====================================================
# 文件名：routes/chat.py
# 作用：PolyDB Agent 聊天接口（Flask 版）
# =====================================================

import os
import json
from flask import Blueprint, request, jsonify
from openai import OpenAI

from services.agent_tools import TOOLS, TOOL_MAP

chat_bp = Blueprint('chat', __name__)

ARK_API_KEY = os.environ.get("ARK_API_KEY")
MODEL_ID = os.environ.get("ARK_MODEL_ID", "deepseek-v4-1-flash-260910")

if not ARK_API_KEY:
    raise RuntimeError("环境变量 ARK_API_KEY 未设置，请在启动服务前配置好再运行")

client = OpenAI(api_key=ARK_API_KEY, base_url="https://ark.cn-beijing.volces.com/api/v3")

SYSTEM_PROMPT = """
You are the PolyDB retrieval assistant for a polyamine conjugate compound database.

Core rules — must be strictly followed:
1. For compound search, structure similarity search, or synthesis route lookup, you MUST call the corresponding tool. Never fabricate data.
2. Answer strictly based on the tool results. Do not alter any returned values.
3. If a tool call fails, tell the user the real error message honestly. Do not make up a reason.
4. If the user provides an invalid SMILES, politely ask them to check the chemical structure.
5. When presenting multiple compounds, use a Markdown table.
6. Only answer questions related to PolyDB compound retrieval; politely decline anything else.
7. Always respond in English, regardless of the language the user writes in.
"""

MAX_TOOL_ROUNDS = 4  # cap tool-calling rounds to avoid an infinite loop

QUOTA_ERROR_KEYWORDS = (
    "insufficient_quota", "insufficient quota", "rate limit", "rate_limit",
    "429", "quota exceeded", "exceeded your current quota",
)

QUOTA_EXCEEDED_MESSAGE = (
    "The assistant is temporarily unavailable because the usage quota for "
    "this service has been reached. Please try again later, or contact the "
    "site administrator if this continues."
)


def _is_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(kw in msg for kw in QUOTA_ERROR_KEYWORDS)


@chat_bp.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True) or {}
    user_message = (data.get('message') or '').strip()
    history = data.get('history') or []  # maintained by the frontend: [{"role": "user"/"assistant", "content": "..."}]

    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        if m.get('role') in ('user', 'assistant') and isinstance(m.get('content'), str):
            messages.append({"role": m['role'], "content": m['content']})
    messages.append({"role": "user", "content": user_message})

    try:
        answer = _run_agent(messages)
    except Exception as e:
        if _is_quota_error(e):
            return jsonify({'error': QUOTA_EXCEEDED_MESSAGE}), 429
        return jsonify({'error': f'Agent error: {e}'}), 500

    return jsonify({'answer': answer})


def _run_agent(messages: list) -> str:
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg_dict = response.choices[0].message.model_dump()
        messages.append(msg_dict)

        tool_calls = msg_dict.get("tool_calls")
        if not tool_calls:
            return msg_dict.get("content") or ""

        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                func_args = {}

            func = TOOL_MAP.get(func_name)
            if func is None:
                result = f"Error: unknown tool {func_name}"
            else:
                try:
                    result = func(**func_args)
                except Exception as e:
                    result = f"Tool execution failed. Real error: {e}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
        # loop continues: feed the tool result back so the model can decide
        # whether to call another tool or give the final answer

    return "Sorry, I couldn't complete this query within the allowed steps. Please try simplifying your question."
