"""AI provider configuration. Keep credentials in environment variables."""
import os

API_URL = ""
API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
MODEL = os.getenv("DASHSCOPE_MODEL", "qwen-plus")
BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
TEMPERATURE = 0.7
MAX_TOKENS = 2000
TIMEOUT = 30
