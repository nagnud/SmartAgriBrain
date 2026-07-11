def make_decision(ai_result: dict, sensor_data: dict) -> dict:
    """
    根据 AI 返回结果和传感器数据，自动补充控制命令。
    """

    commands = ai_result.get("commands", [])

    # 如果 AI 已经给出了控制命令，直接返回
    if commands:
        return ai_result

    temperature = sensor_data.get("temperature", 25)
    humidity = sensor_data.get("humidity", 60)

    # 自动决策
    if temperature >= 30:
        commands.append({
            "command": "fan_on",
            "value": 1,
            "reason": "温度高于30℃，自动开启风机"
        })

    elif temperature <= 18:
        commands.append({
            "command": "fan_off",
            "value": 0,
            "reason": "温度较低，关闭风机"
        })

    if humidity >= 85:
        commands.append({
            "command": "fan_on",
            "value": 1,
            "reason": "湿度过高，加强通风"
        })

    ai_result["commands"] = commands

    return ai_result