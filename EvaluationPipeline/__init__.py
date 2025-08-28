#!/usr/bin/env python3


__version__ = "1.0.0"
__author__ = "EvaluationPipeline Team"

# 导入核心模块
try:
    from .src.core.reasoning_engine import create_reasoning_agent
    __all__ = ["create_reasoning_agent"]
except ImportError:
    __all__ = []