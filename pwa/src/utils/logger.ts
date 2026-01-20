/**
 * Simple environment-aware logger utility
 *
 * Debug logs only show in development mode
 * Error and warn logs always show
 */

const isDevelopment = import.meta.env.DEV;

class Logger {
  private prefix: string;

  constructor(prefix = '') {
    this.prefix = prefix;
  }

  debug(...args: unknown[]): void {
    if (isDevelopment) {
      console.log(this.prefix, ...args);
    }
  }

  info(...args: unknown[]): void {
    if (isDevelopment) {
      console.info(this.prefix, ...args);
    }
  }

  warn(...args: unknown[]): void {
    console.warn(this.prefix, ...args);
  }

  error(...args: unknown[]): void {
    console.error(this.prefix, ...args);
  }
}

// Default logger instance
export const logger = new Logger('[Azlin]');

// Create logger with custom prefix
export const createLogger = (prefix: string): Logger => new Logger(prefix);
