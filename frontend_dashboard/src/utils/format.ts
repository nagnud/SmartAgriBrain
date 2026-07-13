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

export function confidenceText(value: number): string {
  const percentage = `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
  if (value >= 0.8) {
    return `判断把握较高（${percentage}）`;
  }
  if (value >= 0.6) {
    return `判断把握一般（${percentage}）`;
  }
  return `判断把握较低（${percentage}）`;
}

export class UserFacingError extends Error {
  cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = 'UserFacingError';
    this.cause = cause;
  }
}

export function userErrorText(error: unknown, fallback = '操作没有完成，请稍后重试。'): string {
  if (error instanceof UserFacingError) {
    return error.message;
  }
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') {
      return '未获得所需权限，请允许访问后重试。';
    }
    if (error.name === 'NotFoundError') {
      return '没有找到可用内容，请检查后重试。';
    }
    if (error.name === 'AbortError') {
      return '等待时间过长，请稍后重试。';
    }
    if (error.name === 'SecurityError') {
      return '当前页面无法使用这项功能，请改用选择文件或拖入图片。';
    }
  }
  return fallback;
}
