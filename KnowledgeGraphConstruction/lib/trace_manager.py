#!/usr/bin/env python3
"""
Trace管理器
用于生成和管理请求追踪ID，方便日志追踪和调试
支持异步并发和多线程环境
"""

import uuid
import threading
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

# 尝试导入contextvars（Python 3.7+），回退到线程本地存储
try:
    import contextvars
    # 异步上下文变量，用于在协程间共享trace ID
    _trace_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('trace_id', default=None)
    _use_contextvars = True
except ImportError:
    # Python 3.6及以下版本的回退方案
    _use_contextvars = False

# 线程本地存储，用于在同一个请求线程中共享trace ID（回退方案）
_local = threading.local()

class TraceManager:
    """Trace管理器"""
    
    @staticmethod
    def generate_trace_id(prefix: str = "trace") -> str:
        """生成新的trace ID"""
        timestamp = datetime.now().strftime("%y%m%d%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"{prefix}_{timestamp}_{short_uuid}"
    
    @staticmethod
    def set_trace_id(trace_id: str):
        """设置当前上下文的trace ID"""
        if _use_contextvars:
            _trace_context.set(trace_id)
        else:
            _local.trace_id = trace_id
    
    @staticmethod
    def get_trace_id() -> Optional[str]:
        """获取当前上下文的trace ID"""
        if _use_contextvars:
            return _trace_context.get(None)
        else:
            return getattr(_local, 'trace_id', None)
    
    @staticmethod
    def clear_trace_id():
        """清除当前上下文的trace ID"""
        if _use_contextvars:
            _trace_context.set(None)
        else:
            if hasattr(_local, 'trace_id'):
                delattr(_local, 'trace_id')
    
    @staticmethod
    def create_batch_trace_id(batch_trace_id: str, item_index: int) -> str:
        """为批量处理中的单个项目创建trace ID"""
        # 如果batch_trace_id已经包含_item_信息，先去掉
        if "_item_" in batch_trace_id:
            # 找到最后一个_item_的位置，截取之前的部分作为基础trace
            parts = batch_trace_id.split("_item_")
            base_trace = parts[0]
            return f"{base_trace}_item_{item_index:05d}"
        else:
            return f"{batch_trace_id}_item_{item_index:05d}"

class TraceFormatter(logging.Formatter):
    """带有trace ID的日志格式化器"""
    
    def format(self, record):
        # 获取当前线程的trace ID
        trace_id = TraceManager.get_trace_id()
        
        # 如果有trace ID，添加到日志记录中
        if trace_id:
            record.trace_id = trace_id
        else:
            record.trace_id = 'NO_TRACE'
        
        return super().format(record)

def get_traced_logger(name: str) -> logging.Logger:
    """获取带有trace功能的logger"""
    return logging.getLogger(name)

# 便捷函数
def start_trace(trace_id: str = None, prefix: str = "trace") -> str:
    """开始一个新的trace"""
    if not trace_id:
        trace_id = TraceManager.generate_trace_id(prefix)
    TraceManager.set_trace_id(trace_id)
    return trace_id

def end_trace():
    """结束当前trace"""
    TraceManager.clear_trace_id()

def log_with_trace(logger: logging.Logger, level: int, message: str, **kwargs):
    """带有trace信息的日志记录"""
    trace_id = TraceManager.get_trace_id()
    if trace_id:
        logger.log(level, f"[{trace_id}] {message}", **kwargs)
    else:
        logger.log(level, message, **kwargs)
