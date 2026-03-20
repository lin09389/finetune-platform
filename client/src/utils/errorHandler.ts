/**
 * 统一错误处理工具
 */
import { message } from 'antd'

export enum ErrorType {
  NETWORK = 'network',
  TIMEOUT = 'timeout',
  ABORT = 'abort',
  AUTH = 'auth',
  VALIDATION = 'validation',
  SERVER = 'server',
  UNKNOWN = 'unknown',
}

export interface AppError {
  type: ErrorType
  message: string
  detail?: string
  code?: string | number
  recoverable: boolean
  retryable: boolean
}

export class ErrorHandler {
  private static instance: ErrorHandler
  
  static getInstance(): ErrorHandler {
    if (!ErrorHandler.instance) {
      ErrorHandler.instance = new ErrorHandler()
    }
    return ErrorHandler.instance
  }
  
  parse(error: unknown, context?: string): AppError {
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return {
          type: ErrorType.ABORT,
          message: '操作已取消',
          recoverable: true,
          retryable: false,
        }
      }
      
      if (error.message.includes('timeout') || error.message.includes('Timeout')) {
        return {
          type: ErrorType.TIMEOUT,
          message: '请求超时，请稍后重试',
          detail: error.message,
          recoverable: true,
          retryable: true,
        }
      }
      
      if (error.message.includes('network') || error.message.includes('Network')) {
        return {
          type: ErrorType.NETWORK,
          message: '网络连接失败，请检查网络',
          detail: error.message,
          recoverable: true,
          retryable: true,
        }
      }
      
      if (error.message.includes('401') || error.message.includes('Unauthorized')) {
        return {
          type: ErrorType.AUTH,
          message: '认证失败，请重新登录',
          recoverable: false,
          retryable: false,
        }
      }
      
      if (error.message.includes('400') || error.message.includes('Bad Request')) {
        return {
          type: ErrorType.VALIDATION,
          message: '请求参数错误',
          detail: error.message,
          recoverable: true,
          retryable: false,
        }
      }
      
      if (error.message.includes('500') || error.message.includes('Internal Server Error')) {
        return {
          type: ErrorType.SERVER,
          message: '服务器错误，请稍后重试',
          detail: error.message,
          recoverable: true,
          retryable: true,
        }
      }
      
      return {
        type: ErrorType.UNKNOWN,
        message: context ? `${context}失败: ${error.message}` : error.message,
        detail: error.stack,
        recoverable: true,
        retryable: true,
      }
    }
    
    if (typeof error === 'string') {
      return {
        type: ErrorType.UNKNOWN,
        message: context ? `${context}失败: ${error}` : error,
        recoverable: true,
        retryable: true,
      }
    }
    
    return {
      type: ErrorType.UNKNOWN,
      message: context ? `${context}失败` : '未知错误',
      recoverable: true,
      retryable: true,
    }
  }
  
  show(error: AppError, duration: number = 5): void {
    const config = {
      content: error.detail ? `${error.message}\n${error.detail}` : error.message,
      duration,
    }
    
    if (error.type === ErrorType.ABORT) {
      message.info(config)
    } else if (error.type === ErrorType.AUTH) {
      message.warning(config)
    } else if (error.recoverable && error.retryable) {
      message.warning(config)
    } else {
      message.error(config)
    }
  }
  
  handle(error: unknown, context?: string, showToast: boolean = true): AppError {
    const appError = this.parse(error, context)
    if (showToast) {
      this.show(appError)
    }
    return appError
  }
}

export const errorHandler = ErrorHandler.getInstance()

export const handleApiError = (error: unknown, context: string): AppError => {
  return errorHandler.handle(error, context)
}

export const parseError = (error: unknown, context?: string): AppError => {
  return errorHandler.parse(error, context)
}
