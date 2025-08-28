#!/usr/bin/env python3
"""
运行管理器
管理每次运行的独立文件夹、日志、数据保存等
"""

import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import json

class RunManager:
    """运行管理器"""
    
    def __init__(self, base_dir: str = "runs"):
        """初始化运行管理器
        
        Args:
            base_dir: 基础运行目录
        """
        self.base_dir = Path(base_dir)
        self.current_run_id = None
        self.current_run_dir = None
        self.logger = None
        
    def create_new_run(self, run_name: Optional[str] = None) -> str:
        """创建新的运行
        
        Args:
            run_name: 运行名称，如果不提供则使用时间戳
            
        Returns:
            运行ID
        """
        # 生成运行ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if run_name:
            self.current_run_id = f"{timestamp}_{run_name}"
        else:
            self.current_run_id = timestamp
        
        # 创建运行目录
        self.current_run_dir = self.base_dir / self.current_run_id
        self.current_run_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        self._create_run_structure()
        
        # 复制模板文件
        self.copy_template_files()
        
        # 设置日志
        self._setup_logging()
        
        # 保存运行信息
        self._save_run_info()
        
        return self.current_run_id
    
    def _create_run_structure(self):
        """创建运行目录结构"""
        subdirs = [
            "logs",           # 日志文件
            "graphrag_data",  # GraphRAG数据
            "input",          # 输入数据
            "output",         # 输出结果
            "cache",          # 缓存文件
            "config"          # 配置文件
        ]
        
        for subdir in subdirs:
            (self.current_run_dir / subdir).mkdir(exist_ok=True)
        
        # 创建GraphRAG子目录
        graphrag_dir = self.current_run_dir / "graphrag_data"
        for subdir in ["input", "output", "cache", "prompts"]:
            (graphrag_dir / subdir).mkdir(exist_ok=True)
    
    def _setup_logging(self):
        """设置运行专用的日志"""
        log_dir = self.current_run_dir / "logs"
        log_file = log_dir / "run.log"
        
        # 创建专用logger
        logger_name = f"run_{self.current_run_id}"
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 文件handler
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 控制台handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    def _save_run_info(self):
        """保存运行信息"""
        run_info = {
            "run_id": self.current_run_id,
            "created_at": datetime.now().isoformat(),
            "status": "running",
            "directories": {
                "base": str(self.current_run_dir),
                "logs": str(self.current_run_dir / "logs"),
                "graphrag_data": str(self.current_run_dir / "graphrag_data"),
                "input": str(self.current_run_dir / "input"),
                "output": str(self.current_run_dir / "output"),
                "cache": str(self.current_run_dir / "cache"),
                "config": str(self.current_run_dir / "config")
            }
        }
        
        # 保存到运行目录
        with open(self.current_run_dir / "run_info.json", 'w', encoding='utf-8') as f:
            json.dump(run_info, f, indent=2, ensure_ascii=False)
        
        # 保存到全局索引
        self._update_global_index(run_info)
    
    def _update_global_index(self, run_info: Dict[str, Any]):
        """更新全局运行索引"""
        index_file = self.base_dir / "runs_index.json"
        
        # 读取现有索引
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    index = json.load(f)
                # 确保runs键存在
                if "runs" not in index:
                    index["runs"] = []
            except (json.JSONDecodeError, KeyError):
                # 如果文件损坏，重新创建
                index = {"runs": []}
        else:
            index = {"runs": []}
        
        # 添加新运行
        index["runs"].append(run_info)
        
        # 保存索引
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def get_run_paths(self) -> Dict[str, str]:
        """获取当前运行的所有路径"""
        if not self.current_run_dir:
            raise RuntimeError("没有活跃的运行，请先调用 create_new_run()")
        
        return {
            "run_dir": str(self.current_run_dir),
            "logs_dir": str(self.current_run_dir / "logs"),
            "graphrag_root": str(self.current_run_dir / "graphrag_data"),
            "graphrag_input": str(self.current_run_dir / "graphrag_data" / "input"),
            "graphrag_output": str(self.current_run_dir / "graphrag_data" / "output"),
            "graphrag_cache": str(self.current_run_dir / "graphrag_data" / "cache"),
            "input_dir": str(self.current_run_dir / "input"),
            "output_dir": str(self.current_run_dir / "output"),
            "cache_dir": str(self.current_run_dir / "cache"),
            "config_dir": str(self.current_run_dir / "config")
        }
    
    def copy_template_files(self):
        """复制模板文件到运行目录"""
        if not self.current_run_dir:
            return
        
        # 复制GraphRAG配置模板
        template_files = [
            # ("graphrag_data/settings.yaml", "graphrag_data/settings.yaml"),
            ("graphrag_data/prompts", "graphrag_data/prompts")
        ]
        
        for src, dst in template_files:
            src_path = Path(src)
            dst_path = self.current_run_dir / dst
            
            if src_path.exists():
                try:
                    if src_path.is_file():
                        shutil.copy2(src_path, dst_path)
                        if self.logger:
                            self.logger.info(f"复制文件: {src_path} -> {dst_path}")
                    elif src_path.is_dir():
                        if dst_path.exists():
                            shutil.rmtree(dst_path)
                        shutil.copytree(src_path, dst_path)
                        if self.logger:
                            self.logger.info(f"复制目录: {src_path} -> {dst_path}")
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"复制模板文件失败 {src_path}: {e}")
            else:
                if self.logger:
                    self.logger.warning(f"模板文件/目录不存在: {src_path}")
    
    def save_result(self, result: Dict[str, Any], filename: str = "result.json"):
        """保存运行结果"""
        if not self.current_run_dir:
            return
        
        output_file = self.current_run_dir / "output" / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        if self.logger:
            self.logger.info(f"结果已保存到: {output_file}")
    
    def complete_run(self, success: bool = True, error_message: str = None):
        """完成运行"""
        if not self.current_run_dir:
            return
        
        # 更新运行信息
        run_info_file = self.current_run_dir / "run_info.json"
        if run_info_file.exists():
            with open(run_info_file, 'r', encoding='utf-8') as f:
                run_info = json.load(f)
            
            run_info["completed_at"] = datetime.now().isoformat()
            run_info["status"] = "completed" if success else "failed"
            if error_message:
                run_info["error_message"] = error_message
            
            with open(run_info_file, 'w', encoding='utf-8') as f:
                json.dump(run_info, f, indent=2, ensure_ascii=False)
        
        if self.logger:
            if success:
                self.logger.info(f"运行 {self.current_run_id} 成功完成")
            else:
                self.logger.error(f"运行 {self.current_run_id} 失败: {error_message}")
    
    def get_logger(self) -> logging.Logger:
        """获取运行专用的logger"""
        return self.logger
    
    @classmethod
    def list_runs(cls, base_dir: str = "runs") -> list:
        """列出所有运行"""
        index_file = Path(base_dir) / "runs_index.json"
        if not index_file.exists():
            return []
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
            return index.get("runs", [])
        except (json.JSONDecodeError, KeyError):
            # 如果文件损坏，返回空列表
            return []
    
    @classmethod
    def load_run(cls, run_id: str, base_dir: str = "runs") -> Optional['RunManager']:
        """加载已有运行（预留功能）"""
        # TODO: 实现加载已有运行的功能
        # 这个功能在后续版本中实现
        raise NotImplementedError("加载已有运行功能将在后续版本中实现") 