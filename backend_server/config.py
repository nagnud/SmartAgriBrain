import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ==========================================
# AI 配置
# ==========================================

AI_PROVIDER = "deepseek"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

BASE_URL = "https://api.deepseek.com"

MODEL = "deepseek-v4-flash"

TEMPERATURE = 0.2

MAX_TOKENS = 1024

REQUEST_TIMEOUT = 60