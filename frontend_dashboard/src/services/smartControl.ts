import type {
  HistoryPoint,
  MetricTargetRange,
  SmartControlDecision,
  SmartControlDemands,
  SmartControlParamKey,
  SmartControlParamState,
  TelemetryPayload,
  WeatherPayload,
} from '../types';

export const smartControlParamKeys: SmartControlParamKey[] = ['water', 'light', 'heat', 'cool', 'vent', 'co2'];

export const zeroSmartControlDemands: SmartControlDemands = {
  water: 0,
  light: 0,
  heat: 0,
  cool: 0,
  vent: 0,
  co2: 0,
};

export function clampControlValue(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(1, value));
}

function deficit(current: number, target: number, deadband: number, scale: number): number {
  return clamp01((target - current - deadband) / scale);
}

function excess(current: number, target: number, deadband: number, scale: number): number {
  return clamp01((current - target - deadband) / scale);
}

function recentSlope(values: number[]): number {
  const samples = values.filter(Number.isFinite).slice(-8);
  if (samples.length < 2) {
    return 0;
  }
  return (samples[samples.length - 1] - samples[0]) / (samples.length - 1);
}

function limitStep(next: number, previous: number, step: number): number {
  if (!Number.isFinite(previous)) {
    return clampControlValue(next);
  }
  const diff = next - previous;
  if (Math.abs(diff) <= step) {
    return clampControlValue(next);
  }
  return clampControlValue(previous + Math.sign(diff) * step);
}

function weatherWindLevel(weather?: WeatherPayload | null): number {
  const text = weather?.wind_level ?? '';
  const match = text.match(/\d+/);
  return match ? Number(match[0]) : 0;
}

function weatherSummary(weather?: WeatherPayload | null): string {
  if (!weather) {
    return '天气暂不可用，按棚内传感器和历史趋势本地自治';
  }
  return `天气联动：${weather.condition} / 外温 ${weather.temperature}°C / 外湿 ${weather.humidity}% / 风力 ${weather.wind_level}`;
}

function demandLevel(demands: SmartControlDemands): number {
  return Math.max(demands.water, demands.light, demands.heat, demands.cool, demands.vent, demands.co2);
}

export function cloneSmartControlDemands(demands: SmartControlDemands): SmartControlDemands {
  return {
    water: clampControlValue(demands.water),
    light: clampControlValue(demands.light),
    heat: clampControlValue(demands.heat),
    cool: clampControlValue(demands.cool),
    vent: clampControlValue(demands.vent),
    co2: clampControlValue(demands.co2),
  };
}

export function smartControlValueFromDemands(key: SmartControlParamKey, demands: SmartControlDemands): number {
  return demands[key];
}

export function applySmartControlOverrides(
  autoDemands: SmartControlDemands,
  states: Record<SmartControlParamKey, SmartControlParamState>,
): SmartControlDemands {
  const next = cloneSmartControlDemands(autoDemands);
  smartControlParamKeys.forEach((key) => {
    const state = states[key];
    if (state.mode === 'manual') {
      next[key] = clampControlValue(state.value);
    }
  });
  return next;
}

export function defaultSmartControlParamStates(): Record<SmartControlParamKey, SmartControlParamState> {
  return {
    water: { key: 'water', mode: 'auto', value: 0, lastManualValue: 0 },
    light: { key: 'light', mode: 'auto', value: 0, lastManualValue: 0 },
    heat: { key: 'heat', mode: 'auto', value: 0, lastManualValue: 0 },
    cool: { key: 'cool', mode: 'auto', value: 0, lastManualValue: 0 },
    vent: { key: 'vent', mode: 'auto', value: 0, lastManualValue: 0 },
    co2: { key: 'co2', mode: 'auto', value: 0, lastManualValue: 0 },
  };
}

export function computeSmartControlDecision(
  latest: TelemetryPayload,
  history: HistoryPoint[],
  targets: Record<string, MetricTargetRange>,
  weather: WeatherPayload | null,
  previous: SmartControlDemands,
): SmartControlDecision {
  const sensors = latest.sensors;
  const tempTarget = targets.temperature;
  const humidityTarget = targets.humidity;
  const lightTarget = targets.light;
  const co2Target = targets.co2;
  const soilTarget = targets.soil_moisture;

  const tempSlope = recentSlope(history.map((point) => point.temperature));
  const humiditySlope = recentSlope(history.map((point) => point.humidity));
  const lightSlope = recentSlope(history.map((point) => point.light));
  const co2Slope = recentSlope(history.map((point) => point.co2));
  const soilSlope = recentSlope(history.map((point) => point.soil_moisture));

  const outsideHot = weather ? excess(weather.temperature, tempTarget.max, 1, 12) : 0;
  const outsideCold = weather ? deficit(weather.temperature, tempTarget.min, 1, 12) : 0;
  const outsideHumidity = weather?.humidity ?? sensors.humidity;
  const outsideDry = weather ? deficit(outsideHumidity, 45, 0, 40) : 0;
  const outsideWet = weather ? excess(outsideHumidity, 82, 0, 18) : 0;
  const windy = excess(weatherWindLevel(weather), 5, 0, 5);
  const cloudy = /阴|云|雾|霾|cloud|overcast|fog|haze/i.test(weather?.condition ?? '') ? 1 : 0;
  const rainy = /雨|雪|雷|rain|storm|shower|snow/i.test(weather?.condition ?? '') ? 1 : 0;

  const soilLow = deficit(sensors.soil_moisture, (soilTarget.min + soilTarget.max) / 2, 1, 22);
  const soilTooLow = deficit(sensors.soil_moisture, soilTarget.min, 0.5, 18);
  const soilFalling = clamp01(-soilSlope / 2.2);
  let waterScore = Math.max(soilLow, soilTooLow * 0.85) + soilFalling * 0.18 + outsideDry * 0.1 + outsideHot * 0.08;
  if (sensors.soil_moisture > soilTarget.max || rainy || outsideWet > 0.5) {
    waterScore *= 0.35;
  }

  const lightLow = deficit(sensors.light, (lightTarget.min + lightTarget.max) / 2, 80, 12000);
  const lightFalling = clamp01(-lightSlope / 1200);
  let lightScore = Math.max(lightLow, lightFalling * 0.55);
  if (cloudy && sensors.light < lightTarget.min) {
    lightScore += 0.12;
  }
  if (sensors.temperature > tempTarget.max) {
    lightScore *= 0.45;
  }
  if (sensors.light > lightTarget.max) {
    lightScore = 0;
  }

  const coldScore = Math.max(
    deficit(sensors.temperature, (tempTarget.min + tempTarget.max) / 2, 0.4, 8),
    deficit(sensors.temperature + tempSlope * 3, tempTarget.min, 0.2, 7) * 0.7,
  ) + outsideCold * 0.14 + clamp01(-tempSlope / 1.2) * 0.12;

  const hotScore = Math.max(
    excess(sensors.temperature, (tempTarget.min + tempTarget.max) / 2, 0.4, 8),
    excess(sensors.temperature + tempSlope * 3, tempTarget.max, 0.2, 7) * 0.7,
  ) + outsideHot * 0.16 + clamp01(tempSlope / 1.2) * 0.12;

  const heatRaw = coldScore >= hotScore ? coldScore : 0;
  const coolRaw = hotScore > coldScore ? hotScore : 0;

  const co2Low = deficit(sensors.co2, (co2Target.min + co2Target.max) / 2, 25, 450);
  const co2Falling = clamp01(-co2Slope / 35);
  let co2Score = Math.max(co2Low, co2Falling * 0.45);
  if (sensors.light > lightTarget.min && sensors.co2 < co2Target.min) {
    co2Score += 0.1;
  }
  if (sensors.co2 > co2Target.max) {
    co2Score = 0;
  }

  const humidityHigh = excess(sensors.humidity, humidityTarget.max, 1, 18);
  const humidityRising = clamp01(humiditySlope / 2.4);
  const co2High = excess(sensors.co2, co2Target.max, 30, 500);
  let ventScore = Math.max(coolRaw * 0.9, humidityHigh * 0.82, co2High * 0.72) + humidityRising * 0.12 + windy * 0.06;
  if (rainy && coolRaw < 0.2 && co2High < 0.2) {
    ventScore *= 0.55;
  }

  const raw: SmartControlDemands = {
    water: waterScore * 100,
    light: lightScore * 100,
    heat: heatRaw * 100,
    cool: coolRaw * 100,
    vent: ventScore * 100,
    co2: co2Score * 100,
  };

  const urgent = sensors.temperature > tempTarget.max + 3 ||
    sensors.temperature < tempTarget.min - 3 ||
    sensors.humidity > humidityTarget.max + 8 ||
    sensors.soil_moisture < soilTarget.min - 6 ||
    sensors.co2 > co2Target.max + 350;
  const step = urgent ? 35 : 15;
  const demands: SmartControlDemands = {
    water: limitStep(raw.water, previous.water, step),
    light: limitStep(raw.light, previous.light, step),
    heat: limitStep(raw.heat, previous.heat, step),
    cool: limitStep(raw.cool, previous.cool, step),
    vent: limitStep(raw.vent, previous.vent, step),
    co2: limitStep(raw.co2, previous.co2, step),
  };

  const maxDemand = demandLevel(demands);
  const activeNames = smartControlParamKeys
    .filter((key) => demands[key] >= 8)
    .map((key) => smartControlParamLabel(key));
  const riskLevel = urgent ? 'urgent' : maxDemand >= 35 ? 'watch' : 'normal';

  return {
    demands,
    status: riskLevel === 'urgent' ? '紧急调控' : riskLevel === 'watch' ? '托管调节中' : '稳定巡检',
    summary: activeNames.length > 0
      ? `当前重点调节：${activeNames.join('、')}，控制值随环境趋势自动更新`
      : '当前环境接近目标范围，智能托管保持低强度巡检',
    confidence: history.length >= 8 ? 0.86 : 0.72,
    riskLevel,
    weatherSummary: weatherSummary(weather),
  };
}

export function smartControlParamLabel(key: SmartControlParamKey): string {
  if (key === 'water') {
    return '水泵';
  }
  if (key === 'light') {
    return '补光';
  }
  if (key === 'heat') {
    return '升温';
  }
  if (key === 'cool') {
    return '降温';
  }
  if (key === 'vent') {
    return '通风';
  }
  return 'CO2';
}

export function smartControlParamColor(key: SmartControlParamKey): string {
  if (key === 'water') {
    return '#118AB2';
  }
  if (key === 'light') {
    return '#D69900';
  }
  if (key === 'heat') {
    return '#D95A47';
  }
  if (key === 'cool') {
    return '#2A7FA8';
  }
  if (key === 'vent') {
    return '#2D7A46';
  }
  return '#7A5CFA';
}
