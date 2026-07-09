# 智能托管 ESP 通信与控制说明

本文档给 ESP 固件同学使用，说明 Web 前端“智能托管”功能会下发什么数据，以及 ESP 侧如何解析并转换成具体执行器动作。

## 1. 控制值含义

Web 下发的控制值是 `0-100` 的标准化控制强度/控制需求值，不强制等同 PWM。

ESP 可以根据自己的硬件方案，把这些值换算成：

- PWM 占空比
- 继电器开启时长
- 风机/水泵/补光灯档位
- 舵机角度
- CO2 或喷雾设备的投放强度
- 其他可执行控制策略

也就是说，Web 只表达“希望这个执行器动作多强”，最终怎么驱动硬件由 ESP 固件决定。

## 2. 建议处理的 action

ESP 侧建议只处理两类智能托管命令：

```text
smart_control_update
smart_control_stop
```

- `smart_control_update`：更新执行器控制值。
- `smart_control_stop`：停止智能托管相关输出，建议把相关执行器强度清零。

## 3. 更新命令示例

```json
{
  "device_id": "sensairshuttle_001",
  "command": "smart_control_update",
  "value": 1,
  "reason": "一键自动托管",
  "action": "smart_control_update",
  "fieldId": "sensairshuttle_001",
  "fieldName": "智慧大棚",
  "source": "web_smart_control",
  "demands": {
    "water": 61,
    "light": 68,
    "heat": 14,
    "cool": 0,
    "vent": 30,
    "co2": 54
  },
  "waterDemand": 61,
  "lightDemand": 68,
  "heatDemand": 14,
  "coolDemand": 0,
  "ventDemand": 30,
  "co2Demand": 54,
  "tempDemand": 14,
  "airDemand": 30,
  "mistDemand": 54,
  "timestamp": 1779631124853
}
```

## 4. 字段说明

建议 ESP 优先读取顶层简化字段。

| 字段 | 含义 | 范围 |
| --- | --- | --- |
| `waterDemand` | 水泵/灌溉控制需求值 | 0-100 |
| `lightDemand` | 补光控制需求值 | 0-100 |
| `tempDemand` | 温控需求值，正数表示升温，负数表示降温 | -100 到 100 |
| `airDemand` | 通风控制需求值 | 0-100 |
| `mistDemand` | CO2/气肥/喷雾类控制需求值 | 0-100 |

保留的细分字段如下：

| 字段 | 含义 | 范围 |
| --- | --- | --- |
| `heatDemand` | 升温需求值 | 0-100 |
| `coolDemand` | 降温需求值 | 0-100 |
| `ventDemand` | 通风需求值 | 0-100 |
| `co2Demand` | CO2/气肥需求值 | 0-100 |

换算关系：

```text
waterDemand = demands.water
lightDemand = demands.light
heatDemand = demands.heat
coolDemand = demands.cool
ventDemand = demands.vent
co2Demand = demands.co2

tempDemand = heatDemand > 0 ? heatDemand : -coolDemand
airDemand = ventDemand
mistDemand = co2Demand
```

## 5. 停止命令示例

用户关闭智能托管时，Web 会下发停止命令：

```json
{
  "device_id": "sensairshuttle_001",
  "command": "smart_control_stop",
  "value": 0,
  "reason": "关闭智能托管",
  "action": "smart_control_stop",
  "fieldId": "sensairshuttle_001",
  "fieldName": "智慧大棚",
  "source": "web_smart_control",
  "demands": {
    "water": 0,
    "light": 0,
    "heat": 0,
    "cool": 0,
    "vent": 0,
    "co2": 0
  },
  "waterDemand": 0,
  "lightDemand": 0,
  "heatDemand": 0,
  "coolDemand": 0,
  "ventDemand": 0,
  "co2Demand": 0,
  "tempDemand": 0,
  "airDemand": 0,
  "mistDemand": 0,
  "timestamp": 1779631124853
}
```

ESP 收到 `smart_control_stop` 后，建议立即停止智能托管相关执行器输出。

## 6. ESP 侧伪代码

```cpp
if (action == "smart_control_update") {
  int water = readInt(payload, "waterDemand", 0, 100);
  int light = readInt(payload, "lightDemand", 0, 100);
  int temp = readInt(payload, "tempDemand", -100, 100);
  int air = readInt(payload, "airDemand", 0, 100);
  int mist = readInt(payload, "mistDemand", 0, 100);

  setPumpByDemand(water);
  setLightByDemand(light);

  if (temp > 0) {
    setHeaterByDemand(temp);
    setCoolerByDemand(0);
  } else if (temp < 0) {
    setHeaterByDemand(0);
    setCoolerByDemand(-temp);
  } else {
    setHeaterByDemand(0);
    setCoolerByDemand(0);
  }

  setFanByDemand(air);
  setCo2ByDemand(mist);
}

if (action == "smart_control_stop") {
  setPumpByDemand(0);
  setLightByDemand(0);
  setHeaterByDemand(0);
  setCoolerByDemand(0);
  setFanByDemand(0);
  setCo2ByDemand(0);
}
```

`setXxxByDemand()` 由 ESP 固件自己实现，可以换算为 PWM，也可以换算为档位、运行时长或其他硬件控制方式。

## 7. 注意事项

- 所有控制值都要做边界保护，超过范围时建议截断到安全范围。
- `timestamp` 只用于日志排查，不建议作为执行控制的必要条件。
- 如果 ESP 只支持部分执行器，可以忽略暂未接线的字段。
- 如果同时收到手动开关命令和智能托管命令，建议以最新收到的命令为准，或在固件中明确优先级。
