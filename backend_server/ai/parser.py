def parse_ai_result(result: dict) -> dict:
    """
    标准化 DeepSeek 返回结果，确保所有字段都存在。
    """

    if not isinstance(result, dict):
        result = {}

    return {
        "risk_level": result.get("risk_level", "medium"),
        "summary": result.get("summary", ""),
        "suggestions": result.get("suggestions", []),
        "commands": result.get("commands", [])
    }