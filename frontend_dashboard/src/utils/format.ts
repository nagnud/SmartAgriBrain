export function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp));
}

export function formatDateTime(timestamp: number): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
}

export function numberText(value: number, digits = 1): string {
  return value.toFixed(digits);
}

export function airQualityFromGasResistance(value: number): { label: string; level: 'good' | 'watch' | 'danger' } {
  if (value >= 18000) {
    return { label: '空气质量良好', level: 'good' };
  }
  if (value >= 12000) {
    return { label: '需持续观察', level: 'watch' };
  }
  return { label: '建议通风换气', level: 'danger' };
}
