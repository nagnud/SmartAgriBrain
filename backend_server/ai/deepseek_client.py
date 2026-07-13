import os
from dotenv import load_dotenv
from openai import OpenAI

# 1. 强行跨层级定位并加载项目根目录下的 .env 文件
root_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(root_env_path)

# 2. 从环境变量取值，兜底校验
api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")

if not api_key:
    raise ValueError("🚨 严重错误: 未在 .env 文件中读取到 OPENAI_API_KEY 或 DEEPSEEK_API_KEY！")

# 3. 初始化大模型客户端
client = OpenAI(
    api_key=api_key,
    base_url=base_url
)

def chat(prompt: str) -> str:
    """调用 DeepSeek 接口获取诊断方案"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[  # type: ignore
                {"role": "system", "content": "你是一位拥有30年经验的农业专职大模型，擅长通过传感器数据与环境图谱进行精确的农事分析与决策输出。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content or "未返回有效诊断结果。"
    except Exception as e:
        print(f"[DeepSeek 调用错误]: {e}")
        return "AI诊断暂时无法执行，请参考基础规则库进行降级决策。"