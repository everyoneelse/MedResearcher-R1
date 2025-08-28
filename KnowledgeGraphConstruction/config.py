import os
from dotenv import load_dotenv
from typing import Dict, Optional

# 加载环境变量
load_dotenv(override=True)

class Settings:
    """项目配置"""
    
    def __init__(self, run_paths: Optional[Dict[str, str]] = None):
        """初始化配置
        
        Args:
            run_paths: 运行路径字典，如果提供则使用动态路径
        """
        # API 配置
        self.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        
        # QA专用模型配置
        self.QA_API_KEY = os.getenv("QA_API_KEY", self.OPENAI_API_KEY)  # 默认使用OPENAI_API_KEY
        self.QA_API_BASE = os.getenv("QA_API_BASE", "https://openrouter.ai/api/v1")
        self.QA_MODEL = os.getenv("QA_MODEL", "google/gemini-2.5-pro")
        
        # 路径配置 - 支持动态路径
        if run_paths:
            self.GRAPHRAG_ROOT_DIR = run_paths["graphrag_root"]
            self.GRAPHRAG_INPUT_DIR = run_paths["graphrag_input"]
            self.GRAPHRAG_OUTPUT_DIR = run_paths["graphrag_output"]
            self.GRAPHRAG_CACHE_DIR = run_paths["graphrag_cache"]
            self.RUN_DIR = run_paths["run_dir"]
            self.LOGS_DIR = run_paths["logs_dir"]
            self.INPUT_DIR = run_paths["input_dir"]
            self.OUTPUT_DIR = run_paths["output_dir"]
            self.CACHE_DIR = run_paths["cache_dir"]
            self.CONFIG_DIR = run_paths["config_dir"]
        else:
            # 默认路径（兼容旧版本）
            self.GRAPHRAG_ROOT_DIR = os.getenv("GRAPHRAG_ROOT_DIR", "graphrag_data")
            self.GRAPHRAG_INPUT_DIR = os.getenv("GRAPHRAG_INPUT_DIR", "graphrag_data/input")
            self.GRAPHRAG_OUTPUT_DIR = os.getenv("GRAPHRAG_OUTPUT_DIR", "graphrag_data/output")
            self.GRAPHRAG_CACHE_DIR = os.getenv("GRAPHRAG_CACHE_DIR", "graphrag_data/cache")
            self.RUN_DIR = "."
            self.LOGS_DIR = "logs"
            self.INPUT_DIR = "input"
            self.OUTPUT_DIR = "output"
            self.CACHE_DIR = "cache"
            self.CONFIG_DIR = "config"
        
        # 搜索配置
        self.SEARCH_RESULTS_LIMIT = int(os.getenv("SEARCH_RESULTS_LIMIT", "10"))
        self.MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "2000"))
        
        # 图构建配置
        self.MAX_NODES = int(os.getenv("MAX_NODES", "30"))
        self.MAX_RELATIONS_PER_NODE = int(os.getenv("MAX_RELATIONS_PER_NODE", "10"))
        self.ITERATION_LIMIT = int(os.getenv("ITERATION_LIMIT", "15"))
        
        # 采样配置
        self.SAMPLE_SIZE = int(os.getenv("SAMPLE_SIZE", "8"))
        
        # 模糊化配置
        self.ANONYMIZE_PROBABILITY = float(os.getenv("ANONYMIZE_PROBABILITY", "0.3"))
        
        # 文本清理配置
        self.MIN_TEXT_LENGTH = int(os.getenv("MIN_TEXT_LENGTH", "100"))
        self.MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "1000"))
    
    def update_paths(self, run_paths: Dict[str, str]):
        """更新路径配置"""
        self.GRAPHRAG_ROOT_DIR = run_paths["graphrag_root"]
        self.GRAPHRAG_INPUT_DIR = run_paths["graphrag_input"]
        self.GRAPHRAG_OUTPUT_DIR = run_paths["graphrag_output"]
        self.GRAPHRAG_CACHE_DIR = run_paths["graphrag_cache"]
        self.RUN_DIR = run_paths["run_dir"]
        self.LOGS_DIR = run_paths["logs_dir"]
        self.INPUT_DIR = run_paths["input_dir"]
        self.OUTPUT_DIR = run_paths["output_dir"]
        self.CACHE_DIR = run_paths["cache_dir"]
        self.CONFIG_DIR = run_paths["config_dir"]

# 创建全局设置实例（默认配置）
settings = Settings()

def create_run_settings(run_paths: Dict[str, str]) -> Settings:
    """为特定运行创建配置实例"""
    return Settings(run_paths)

def setup_global_logging():
    """设置全局日志配置 - 带有trace支持的简单实现"""
    import logging
    from datetime import datetime
    from lib.trace_manager import TraceFormatter
    
    # 创建logs目录（如果不存在）
    import os
    logs_dir = os.path.expanduser(os.path.join(os.path.dirname(__file__), 'logs'))
    os.makedirs(logs_dir, exist_ok=True)
    
    # 生成日志文件名（按日期）
    date_str = datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(logs_dir, f"app_{date_str}.log")
    
    # 获取根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 检查是否已经配置过文件handler，避免重复配置
    has_file_handler = any(isinstance(handler, logging.FileHandler) for handler in root_logger.handlers)
    
    if not has_file_handler:
        # 创建文件handler
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 创建带有trace的格式化器
        trace_formatter = TraceFormatter(
            '%(asctime)s [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(trace_formatter)
        
        # 添加到根logger
        root_logger.addHandler(file_handler)
    
    return log_filename 