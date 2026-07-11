import json
from openai import OpenAI

import config
from ai.parser import parse_ai_result
from ai.decision_engine import make_decision
client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.BASE_URL,
    timeout=config.REQUEST_TIMEOUT
)

SYSTEM_PROMPT = """
你是一名智慧农业专家。

请根据用户提供的环境数据和农业知识库进行分析。

分析必须结合农业知识，不允许随意猜测。

你只能返回 JSON。

禁止 Markdown。

禁止 ```json。

禁止解释。

禁止输出任何额外文字。

JSON 格式必须严格如下：

{
    "risk_level":"low|medium|high",
    "summary":"一句话总结",
    "suggestions":[
        "...",
        "...",
        "..."
    ],
    "commands":[
        {
            "command":"fan_on",
            "value":1,
            "reason":"..."
        }
    ]
}

commands 中 command 只能使用：

fan_on
fan_off
pump_on
pump_off
light_on
light_off

如果无需控制设备：

commands 返回 []

不要输出任何其它内容。
"""


def chat(prompt: str) -> dict:
    """
    调用 DeepSeek 大模型并返回标准化 JSON
    """

    try:

        response = client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,

            # 如果当前模型支持，将直接返回 JSON
            response_format={
                "type": "json_object"
            }
        )

    except Exception as e:

        print("========== DeepSeek 调用失败 ==========")
        print(e)
        print("======================================")

        return parse_ai_result({
            "summary": f"DeepSeek 调用失败：{e}"
        })

    result = response.choices[0].message.content.strip()

    # 去除 Markdown 标记
    result = (
        result.replace("```json", "")
              .replace("```", "")
              .strip()
    )

    try:

        data = json.loads(result)

        data = parse_ai_result(data)

        return data
    except Exception as e:

        print("========== DeepSeek 返回解析失败 ==========")
        print(result)
        print("==========================================")

        return parse_ai_result({
            "summary": result
        })