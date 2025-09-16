#!/usr/bin/env python3
"""
基于 GraphRag 的知识图谱构建器
用于替代 DeepKE + Neo4j 的方案
"""

import os
import json
import random
import logging
import asyncio
import tempfile
import shutil
import hashlib
import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import re # Added for _parse_search_result_to_triplets

from config import settings
from lib.search_engine import SearchEngine
from lib.llm_client import LLMClient
from lib.text_processor import TextProcessor
from lib.graph_sampler import GraphSampler
from lib.enhanced_graph_sampler import EnhancedGraphSampler, SamplingAlgorithm
from lib.information_anonymizer import InformationAnonymizer
from lib.qa_generator import QAGenerator
from lib.unified_qa_generator import UnifiedQAGenerator
from lib.entity_linker import EntityLinker

logger = logging.getLogger(__name__)

class GraphRagBuilder:
    """基于 GraphRag 的知识图谱构建器"""
    
    def __init__(self, settings_instance=None, graph_update_callback=None):
        """初始化构建器
        
        Args:
            settings_instance: 配置实例，如果不提供则使用全局配置
            graph_update_callback: 图更新回调函数
        """
        # 使用提供的设置或默认设置
        if settings_instance:
            self.settings = settings_instance
        else:
            # 使用全局配置但创建一个副本，避免并发冲突
            from config import Settings
            self.settings = Settings()
        
        self.graph_update_callback = graph_update_callback
        self.search_engine = SearchEngine()
        self.llm_client = LLMClient()
        self.text_processor = TextProcessor()
        self.graph_sampler = GraphSampler()
        self.enhanced_sampler = EnhancedGraphSampler()  # 新的增强采样器
        self.anonymizer = InformationAnonymizer()
        self.qa_generator = QAGenerator()
        self.unified_qa_generator = UnifiedQAGenerator()  # 新的统一QA生成器
        
        # 确保 GraphRag 目录存在
        self._setup_graphrag_directories()
        
        # 初始化 GraphRag 配置
        self._initialize_graphrag_config()
        
        # 统计信息
        self.stats = {
            'total_iterations': 0,
            'total_nodes': 0,
            'total_relations': 0,
            'search_queries': [],
            'processed_texts': [],
            'start_time': None,
            'end_time': None
        }

        # 初始化图结构相关字段
        self.existing_relations_set = set()    # source,relation,target 去重集合
        self.entity_name_to_entities = {}      # 实体名称到实体信息的映射

    def _setup_graphrag_directories(self):
        """设置 GraphRag 目录结构"""
        directories = [
            self.settings.GRAPHRAG_ROOT_DIR,
            self.settings.GRAPHRAG_INPUT_DIR,
            self.settings.GRAPHRAG_OUTPUT_DIR,
            self.settings.GRAPHRAG_CACHE_DIR
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"GraphRag 目录结构已创建: {self.settings.GRAPHRAG_ROOT_DIR}")
    
    def _initialize_graphrag_config(self):
        """初始化 GraphRag 配置"""
        config_path = Path(self.settings.GRAPHRAG_ROOT_DIR) / "settings.yaml"
        env_path = Path(self.settings.GRAPHRAG_ROOT_DIR) / ".env"
        
        # 设置环境变量（确保GraphRAG能够找到API密钥）
        os.environ['GRAPHRAG_API_KEY'] = self.settings.OPENAI_API_KEY
        os.environ['OPENAI_MODEL'] = self.settings.OPENAI_MODEL
        os.environ['OPENAI_API_BASE'] = self.settings.OPENAI_API_BASE
        os.environ['EMBEDDING_MODEL'] = self.settings.EMBEDDING_MODEL
        logger.info(f"设置环境变量 GRAPHRAG_API_KEY: {self.settings.OPENAI_API_KEY[:10]}...")
        logger.info(f"设置环境变量 OPENAI_MODEL: {self.settings.OPENAI_MODEL}")
        logger.info(f"设置环境变量 OPENAI_API_BASE: {self.settings.OPENAI_API_BASE}")
        logger.info(f"设置环境变量 EMBEDDING_MODEL: {self.settings.EMBEDDING_MODEL}")
        
        if not config_path.exists():
            # 创建 GraphRag 配置文件
            config_content = self._generate_graphrag_config()
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            logger.info(f"GraphRag 配置文件已创建: {config_path}")
        else:
            logger.info(f"GraphRag 配置文件已存在: {config_path}")
        
        if not env_path.exists():
            # 创建环境变量文件
            env_content = f"""GRAPHRAG_API_KEY={self.settings.OPENAI_API_KEY}
OPENAI_MODEL={self.settings.OPENAI_MODEL}
OPENAI_API_BASE={self.settings.OPENAI_API_BASE}
EMBEDDING_MODEL={self.settings.EMBEDDING_MODEL}
"""
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_content)
            logger.info(f"GraphRag 环境文件已创建: {env_path}")
        else:
            # 更新现有的环境变量文件
            env_content = f"""GRAPHRAG_API_KEY={self.settings.OPENAI_API_KEY}
OPENAI_MODEL={self.settings.OPENAI_MODEL}
OPENAI_API_BASE={self.settings.OPENAI_API_BASE}
EMBEDDING_MODEL={self.settings.EMBEDDING_MODEL}
"""
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(env_content)
            logger.info(f"GraphRag 环境文件已更新: {env_path}")
        
        logger.info(f"GraphRAG API密钥已设置: {self.settings.OPENAI_API_KEY[:10]}...")
    
    def _generate_entity_id(self, name: str, entity_type: str, description: str) -> str:
        """为实体生成唯一标识符
        
        Args:
            name: 实体名称
            entity_type: 实体类型
            description: 实体描述
            
        Returns:
            唯一的实体标识符
        """
        # 标准化实体名称（去除多余空格、标点符号，转换为小写）
        normalized_name = self._normalize_entity_name(name)
        normalized_type = entity_type.strip().lower()
        
        # 主要使用标准化的名称和类型生成ID，描述只作为辅助
        content = f"{normalized_name}|{normalized_type}"
        entity_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        return f"entity_{entity_hash}"
    
    def _normalize_entity_name(self, name: str) -> str:
        """标准化实体名称，避免重复"""
        import re
        
        # 去除首尾空格
        name = name.strip()
        
        # 去除多余的空格（连续空格变成单个空格）
        name = re.sub(r'\s+', ' ', name)
        
        # 去除常见的标点符号（使用简单的字符串替换）
        punctuations = ['，', '。', '！', '？', '；', '：', '"', '"', ''', ''', 
                       '(', ')', '（', '）', '【', '】', '《', '》', '<', '>', '/', '\\']
        for p in punctuations:
            name = name.replace(p, '')
        
        # 转换为小写进行比较（但保留原始大小写用于显示）
        normalized = name.lower()
        
        # 处理常见的繁简体字符转换
        traditional_to_simplified = {
            '著': '着',      # 著名 -> 着名，裹著心的光 -> 裹着心的光
            '麼': '么',      # 什麼 -> 什么
            '來': '来',      # 來自 -> 来自
            '說': '说',      # 說話 -> 说话
            '開': '开',      # 開始 -> 开始
            '關': '关',      # 關於 -> 关于
            '這': '这',      # 這個 -> 这个
            '那': '那',      # 保持不变
            '個': '个',      # 個人 -> 个人
            '們': '们',      # 我們 -> 我们
            '時': '时',      # 時間 -> 时间
            '間': '间',      # 時間 -> 时间
            '會': '会',      # 會議 -> 会议
            '員': '员',      # 成員 -> 成员
            '業': '业',      # 企業 -> 企业
            '學': '学',      # 學習 -> 学习
            '習': '习',      # 學習 -> 学习
            '國': '国',      # 中國 -> 中国
            '華': '华',      # 中華 -> 中华
            '發': '发',      # 發布 -> 发布
            '現': '现',      # 發現 -> 发现
            '進': '进',      # 進步 -> 进步
            '後': '后',      # 之後 -> 之后
            '種': '种',      # 種類 -> 种类
            '類': '类',      # 種類 -> 种类
            '動': '动',      # 活動 -> 活动
            '態': '态',      # 狀態 -> 状态
            '狀': '状',      # 狀態 -> 状态
            '報': '报',      # 報告 -> 报告
            '導': '导',      # 導致 -> 导致
            '義': '义',      # 意義 -> 意义
            '買': '买',      # 購買 -> 购买
            '購': '购',      # 購買 -> 购买
            '賣': '卖',      # 販賣 -> 贩卖
            '販': '贩',      # 販賣 -> 贩卖
            '條': '条',      # 條件 -> 条件
            '線': '线',      # 線上 -> 线上
            '網': '网',      # 網路 -> 网路
            '電': '电',      # 電腦 -> 电脑
            '腦': '脑',      # 電腦 -> 电脑
            '機': '机',      # 機器 -> 机器
            '車': '车',      # 汽車 -> 汽车
            '還': '还',      # 還有 -> 还有
            '選': '选',      # 選擇 -> 选择
            '擇': '择',      # 選擇 -> 选择
            '話': '话',      # 對話 -> 对话
            '對': '对',      # 對話 -> 对话
            '過': '过',      # 經過 -> 经过
            '經': '经',      # 經過 -> 经过
            '內': '内',      # 內容 -> 内容
            '容': '容',      # 保持不变
            '並': '并',      # 並且 -> 并且
            '確': '确',      # 確定 -> 确定
            '實': '实',      # 實際 -> 实际
            '際': '际',      # 實際 -> 实际
            '題': '题',      # 問題 -> 问题
            '問': '问',      # 問題 -> 问题
            '結': '结',      # 結果 -> 结果
            '果': '果',      # 保持不变
            '處': '处',      # 處理 -> 处理
            '理': '理',      # 保持不变
            '場': '场',      # 市場 -> 市场
            '市': '市',      # 保持不变
            '層': '层',      # 層次 -> 层次
            '次': '次',      # 保持不变
            '點': '点',      # 觀點 -> 观点
            '觀': '观',      # 觀點 -> 观点
            '應': '应',      # 應該 -> 应该
            '該': '该',      # 應該 -> 应该
            '數': '数',      # 數字 -> 数字
            '字': '字',      # 保持不变
            '計': '计',      # 計算 -> 计算
            '算': '算',      # 保持不变
            '記': '记',      # 記錄 -> 记录
            '錄': '录',      # 記錄 -> 记录
            '據': '据',      # 數據 -> 数据
            '準': '准',      # 標準 -> 标准
            '標': '标',      # 標準 -> 标准
        }

        # 应用繁简体转换
        for traditional, simplified in traditional_to_simplified.items():
            normalized = normalized.replace(traditional, simplified)

        # 处理常见的同义词或变体
        synonyms = {
            'ai': '人工智能',
            'artificial intelligence': '人工智能',
            'ml': '机器学习',
            'machine learning': '机器学习',
            'deep learning': '深度学习',
            'blockchain': '区块链',
            'quantum computing': '量子计算',
            'quantum computer': '量子计算机'
        }
        
        for syn, standard in synonyms.items():
            if syn in normalized:
                normalized = normalized.replace(syn, standard)
        
        return normalized
    
    def _generate_graphrag_config(self) -> str:
        """生成 GraphRag 配置内容"""
        # 检查prompt文件是否存在
        root_dir = Path(self.settings.GRAPHRAG_ROOT_DIR)
        prompts_dir = root_dir / "prompts"
        
        # 生成entity_extraction配置
        entity_extraction_config = "entity_extraction:\n"
        entity_extraction_prompt = prompts_dir / "entity_extraction.txt"
        if entity_extraction_prompt.exists():
            entity_extraction_config += '  prompt: "graphrag_data/prompts/entity_extraction.txt"\n'
        entity_extraction_config += "  entity_types: [person, organization, location, concept, technology, event]\n"
        entity_extraction_config += "  max_gleanings: 0\n"
        
        # 生成summarize_descriptions配置
        summarize_descriptions_config = "summarize_descriptions:\n"
        summarize_descriptions_prompt = prompts_dir / "summarize_descriptions.txt"
        if summarize_descriptions_prompt.exists():
            summarize_descriptions_config += '  prompt: "graphrag_data/prompts/summarize_descriptions.txt"\n'
        summarize_descriptions_config += "  max_length: 500\n"
        
        # 生成community_reports配置
        community_reports_config = "community_reports:\n"
        community_reports_prompt = prompts_dir / "community_report.txt"
        if community_reports_prompt.exists():
            community_reports_config += '  graph_prompt: "prompts/community_report.txt"\n'
        community_reports_config += "  max_length: 2000\n"
        community_reports_config += "  max_input_length: 8000\n"
        
        # 生成claim_extraction配置
        claim_extraction_config = "claim_extraction:\n"
        claim_extraction_prompt = prompts_dir / "claim_extraction.txt"
        if claim_extraction_prompt.exists():
            claim_extraction_config += '  prompt: "graphrag_data/prompts/claim_extraction.txt"\n'
        claim_extraction_config += '  description: "Any claims or facts that could be relevant to information discovery."\n'
        claim_extraction_config += "  max_gleanings: 0\n"
        
        return f"""
encoding: utf-8
skip_workflows: []
llm:
  api_key: ${{GRAPHRAG_API_KEY}}
  type: openai_chat
  model: ${{OPENAI_MODEL}}
  api_base: ${{OPENAI_API_BASE}}
  model_supports_json: true
  max_tokens: 4000
  temperature: 0
  top_p: 1
  n: 1
  encoding_model: cl100k_base

models:
  default_chat_model:
    api_key: ${{GRAPHRAG_API_KEY}}
    type: openai_chat
    model: ${{OPENAI_MODEL}}
    api_base: ${{OPENAI_API_BASE}}
    model_supports_json: true
    max_tokens: 4000
    temperature: 0
    top_p: 1
    n: 1
    encoding_model: cl100k_base
  default_embedding_model:
    type: openai_embedding
    api_key: ${{GRAPHRAG_API_KEY}}
    api_base: ${{OPENAI_API_BASE}}
    model: ${{EMBEDDING_MODEL}}
    encoding_model: cl100k_base
    max_tokens: 8191
  
parallelization:
  stagger: 0.3
  num_threads: 50

async_mode: threaded

embeddings:
  async_mode: threaded
  llm:
    type: openai_embedding
    api_key: ${{GRAPHRAG_API_KEY}}
    api_base: ${{OPENAI_API_BASE}}
    model: ${{EMBEDDING_MODEL}}
    encoding_model: cl100k_base
    max_tokens: 8191
    
chunks:
  size: 300
  overlap: 100
  group_by_columns: [id]
  
input:
  type: file
  file_type: text
  base_dir: "input"
  file_encoding: utf-8
  file_pattern: ".*\\\\.txt$$"
  
cache:
  type: file
  base_dir: "cache"
  
storage:
  type: file
  base_dir: "output"
  
reporting:
  type: file
  base_dir: "output"
  
{entity_extraction_config}
  
{summarize_descriptions_config}
  
{community_reports_config}
  
{claim_extraction_config}
  
embed_graph:
  enabled: true
  num_walks: 10
  walk_length: 40
  window_size: 2
  iterations: 3
  random_seed: 597832
  
umap:
  enabled: true
  
snapshots:
  graphml: false
  raw_entities: false
  top_level_nodes: false
  
local_search:
  text_unit_prop: 0.5
  community_prop: 0.1
  conversation_history_max_turns: 5
  top_k_mapped_entities: 10
  top_k_relationships: 10
  max_tokens: 12000
  
global_search:
  max_tokens: 12000
  data_max_tokens: 12000
  map_max_tokens: 10000
  reduce_max_tokens: 2000
  concurrency: 32
"""
    
    async def build_knowledge_graph(
        self, 
        initial_entity: str = None, 
        progress_callback=None, 
        max_iterations=10,
        sampling_algorithm: str = "mixed",  # 新增：采样算法选择
        use_unified_qa: bool = True  # 新增：是否使用统一QA生成器
    ) -> Dict[str, Any]:
        """构建知识图谱"""
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            logger.info(f"知识图谱构建器继承trace: {parent_trace}")
        else:
            start_trace(prefix="kg_builder")
            logger.info(f"知识图谱构建器创建新trace")
        
        self.stats['start_time'] = datetime.now().isoformat()  # 转换为字符串
        logger.info(f"开始构建知识图谱，初始实体: {initial_entity}")
        
        try:
            # 1. 获取初始实体
            if not initial_entity:
                if progress_callback:
                    progress_callback("获取随机实体", 5)
                initial_entity = await self._get_random_entity()
            
            logger.info(f"使用初始实体: {initial_entity}")
            
            # 2. 迭代构建知识图谱
            if progress_callback:
                progress_callback("开始迭代构建", 10)
            await self._iterative_graph_building(initial_entity, progress_callback, max_iterations)
            
            # 3. 简化的图结构信息（基于已抽取的实体）
            if progress_callback:
                progress_callback("整理图结构信息", 60)
            graph_info = await self._build_simple_graph_info()
            
            # 注释掉月份到年份映射功能，暂时不使用
            # if progress_callback:
            #     progress_callback("生成年份实体映射", 70)
            # graph_info = await self._map_months_to_years(graph_info)
            
            # 如果需要完整的GraphRAG分析，可以选择性运行索引
            # await self._run_graphrag_indexing()
            # graph_info = await self._get_graph_info()
            
            # 5. 采样图结构（使用增强采样器）
            if progress_callback:
                progress_callback("采样复杂拓扑子图", 75)
            sample_info = await self._sample_graph_enhanced(graph_info, sampling_algorithm)
            
            # 6. 生成统一QA（包含模糊化）
            if progress_callback:
                progress_callback("生成复杂问答对", 85)
            qa_pair = await self._generate_qa_unified(sample_info, use_unified_qa, sampling_algorithm)
            
            # 7. 保持向后兼容的模糊化信息（如果需要）
            if not use_unified_qa:
                if progress_callback:
                    progress_callback("模糊化信息", 90)
                anonymized_sample = await self._anonymize_sample(sample_info)
            else:
                # 统一QA生成器已经包含了模糊化逻辑
                anonymized_sample = sample_info
            
            # 8. 更新统计信息
            self.stats['end_time'] = datetime.now().isoformat()  # 转换为字符串
            self.stats['total_nodes'] = graph_info.get('node_count', 0)
            self.stats['total_relations'] = graph_info.get('relationship_count', 0)
            
            if progress_callback:
                progress_callback("构建完成", 100)
            
            return {
                'initial_entity': initial_entity,
                'graph_info': graph_info,
                'sample_info': sample_info,
                'anonymized_sample': anonymized_sample,
                'qa_pair': qa_pair,
                'statistics': self.stats
            }
            
        except Exception as e:
            logger.error(f"构建知识图谱失败: {e}")
            raise
    
    async def _get_random_entity(self) -> str:
        """获取随机实体（简化版本，不依赖 Wikidata）"""
        # 备选实体列表（医学相关）
        fallback_entities = [
            "量子计算机", "基因编辑", "纳米医学", "神经形态芯片",
            "合成生物学", "脑机接口", "量子传感器", "光遗传学",
            "液体活检", "数字孪生", "边缘计算", "蛋白质折叠",
            "免疫疗法", "干细胞治疗", "精准医学", "生物传感器",
            "人工智能诊断", "微流控芯片", "组织工程", "基因治疗"
        ]
        
        selected_entity = random.choice(fallback_entities)
        logger.info(f"随机选择实体: {selected_entity}")
        return selected_entity
    
    async def _iterative_graph_building(self, initial_entity_name: str, progress_callback=None, max_iterations=5):
        """迭代构建知识图谱 - 基于expansion node策略"""
        import random

        # 核心数据结构
        self.expansion_nodes = []      # expansion节点列表（按顺序）
        self.current_node = None       # 当前正在处理的节点
        self.graph_entities = {}       # 所有实体：entity_id -> entity_info
        self.graph_relationships = []  # 所有关系
        self.node_neighbors = {}       # 节点邻居关系：entity_id -> [neighbor_ids]
        self.processed_entities = set()  # 已处理的实体，避免重复处理
        self.latest_iteration_entities = set()  # 最新一轮迭代产生的实体名称
        self.existing_relations_set = set()    # source,relation,target 去重集合
        self.entity_name_to_entities = {}      # 实体名称到实体信息的映射

        # 第一步：处理初始实体
        logger.info(f"开始expansion构建，初始实体: {initial_entity_name}")

        # 1. 对初始实体进行搜索拓展
        if progress_callback:
            progress_callback(f"初始拓展: {initial_entity_name}", 10)

        # 清空最新迭代实体集合，准备记录初始拓展产生的实体
        self.latest_iteration_entities.clear()
        
        initial_entities = await self._process_search_results(initial_entity_name, initial_entity_name)
        self.processed_entities.add(initial_entity_name)

        # 2. 将初始实体加入expansion_nodes
        initial_entity_id = self._generate_entity_id(initial_entity_name, 'concept', f'初始实体：{initial_entity_name}')
        self.expansion_nodes.append(initial_entity_id)
        self.current_node = initial_entity_name

        # 3. 构建初始图结构
        update_result = await self._update_graph_structure()
        logger.info(f"初始图结构更新完成: 新增实体 {update_result['new_entity_count']} 个, 新增关系 {update_result['new_relationship_count']} 个")
        
        # 移除重复的图更新调用，_send_expansion_update已经会发送图数据
        # try:
        #     await self._send_graph_update()
        # except Exception as e:
        #     logger.error(f"发送实时图更新失败: {e}")
        
        # 4. 发送初始图更新
        await self._send_expansion_update(iteration=0, action="初始拓展")

        # 迭代拓展过程
        for iteration in range(1, max_iterations + 1):
            logger.info(f"=== 迭代 {iteration}/{max_iterations} ===")

            # 检查是否超过最大关系数限制
            if len(self.graph_relationships) >= self.settings.MAX_NODES:
                logger.info(f"达到最大关系数限制 ({self.settings.MAX_NODES})，停止迭代")
                if progress_callback:
                    progress_callback(f"达到最大关系数限制，停止迭代", 50)
                break

            # 选择下一个扩展实体
            next_entity_name = await self._select_next_entity_for_expansion()

            if not next_entity_name:
                logger.info("没有找到可拓展的实体，停止迭代")
                if progress_callback:
                    progress_callback("没有可拓展实体，迭代结束", 50)
                break

            # 设置当前expansion节点
            self.current_node = next_entity_name
            self.expansion_nodes.append(next_entity_name)
            
            logger.info(f"迭代 {iteration}: 选择expansion节点 '{next_entity_name}'")
            logger.info(f"当前expansion节点列表: {self.expansion_nodes}")

            # 发送expansion状态更新到前端
            expansion_info = {
                'iteration': iteration,
                'max_iterations': max_iterations,
                'current_expansion_node': next_entity_name,
                'expansion_nodes': list(self.expansion_nodes),
                'total_expansion_nodes': len(self.expansion_nodes),
                'total_nodes': len(self.graph_entities),
                'total_relations': len(self.graph_relationships),
                'action': f'拓展节点: {next_entity_name}'
            }

            # 移除重复的图更新发送，将在后面的_send_expansion_update中统一发送
            # if self.graph_update_callback:
            #     try:
            #         # 发送expansion状态更新
            #         current_graph = await self._build_simple_graph_info()
            #         # ... (省略重复的图更新代码)
            #         self.graph_update_callback(update_data)
            #         logger.info(f"发送expansion状态更新: 迭代{iteration}, 节点{next_entity_name}")
            #     except Exception as e:
            #         logger.warning(f"发送expansion状态更新失败: {e}")

            # 设置迭代进度
            progress = int(10 + (iteration / max_iterations) * 40)  # 10-50%
            if progress_callback:
                progress_callback(f"迭代 {iteration}/{max_iterations}: 拓展节点 {next_entity_name}", progress)

            logger.info(f"expansion_nodes: {[self._get_entity_name(node_id) for node_id in self.expansion_nodes]}")
            logger.info(f"current_node: {next_entity_name}")

            # 对选定实体进行搜索拓展
            new_entities = await self._process_search_results(next_entity_name, next_entity_name)
            self.processed_entities.add(next_entity_name)

            # 将当前实体加入expansion_nodes
            current_entity_id = self._find_entity_id_by_name(next_entity_name)
            if current_entity_id and current_entity_id not in self.expansion_nodes:
                self.expansion_nodes.append(current_entity_id)
                self.current_node = next_entity_name
                logger.info(f"将 {next_entity_name} 加入expansion_nodes")

            # 更新图结构
            update_result = await self._update_graph_structure()
            logger.info(f"迭代 {iteration} 图结构更新完成: 新增实体 {update_result['new_entity_count']} 个, 新增关系 {update_result['new_relationship_count']} 个")
            
            # 移除重复的图更新调用，_send_expansion_update已经会发送图数据
            # try:
            #     await self._send_graph_update()
            # except Exception as e:
            #     logger.error(f"发送实时图更新失败: {e}")
            
            # 发送实时更新
            await self._send_expansion_update(iteration=iteration, action=f"拓展 {next_entity_name}")

            self.stats['total_iterations'] = iteration

            # 每次迭代后稍作延迟，让前端有时间渲染
            import asyncio
            await asyncio.sleep(0.5)

        # 最终更新
        await self._send_expansion_update(iteration=max_iterations, action="拓展完成", final=True)
        logger.info(f"完成expansion构建，expansion_nodes数量: {len(self.expansion_nodes)}")

    async def _select_next_entity_for_expansion(self) -> str:
        """选择下一个用于拓展的实体名称"""
        import random

        # 从已发现但未处理的实体中选择
        all_entity_names = set(self.entity_name_to_entities.keys())

        # 调试信息
        logger.info(f"=== 实体选择调试信息 ===")
        logger.info(f"graph_entities总数: {len(self.graph_entities)}")
        logger.info(f"所有实体名称: {list(all_entity_names)}")
        logger.info(f"已处理实体: {list(self.processed_entities)}")
        logger.info(f"最新一轮迭代产生的实体: {list(self.latest_iteration_entities)}")

        # 过滤掉已处理的实体
        unprocessed_entities = all_entity_names - self.processed_entities

        logger.info(f"未处理的实体: {list(unprocessed_entities)}")

        if not unprocessed_entities:
            logger.info("没有找到可拓展的实体")
            return None

        # 分组：区分最新一轮迭代产生的实体和之前已存在的实体
        latest_unprocessed = unprocessed_entities & self.latest_iteration_entities
        previous_unprocessed = unprocessed_entities - self.latest_iteration_entities
        
        # 获取上一轮迭代的实体名称
        last_iteration_entity = self.current_node
        
        # 过滤最新一轮实体：只保留与上一轮迭代实体距离为1的实体
        if last_iteration_entity and latest_unprocessed:
            filtered_latest = set()
            logger.info(f"过滤最新一轮实体，只保留与上一轮迭代实体 '{last_iteration_entity}' 距离为1的实体")
            
            for entity in latest_unprocessed:
                distance = self._calculate_entity_distance(entity, last_iteration_entity)
                logger.info(f"  实体 '{entity}' 与 '{last_iteration_entity}' 的距离: {distance}")
                if distance == 1:
                    filtered_latest.add(entity)
                    logger.info(f"    -> 保留距离为1的实体: {entity}")
                else:
                    logger.info(f"    -> 过滤掉距离不为1的实体: {entity}")

            if filtered_latest:
                latest_unprocessed = filtered_latest
            logger.info(f"过滤后的最新一轮实体: {list(latest_unprocessed)}")
        
        logger.info(f"最新一轮未处理实体: {list(latest_unprocessed)}")
        logger.info(f"之前已存在未处理实体: {list(previous_unprocessed)}")

        # 以50%概率选择实体集合
        entity_groups = []
        if latest_unprocessed:
            entity_groups.append(("latest", latest_unprocessed))
        if previous_unprocessed:
            entity_groups.append(("previous", previous_unprocessed))
        
        if not entity_groups:
            logger.info("没有可选的实体组")
            return None
        
        # 随机选择一个组开始
        random.shuffle(entity_groups)
        primary_group_name, primary_group = entity_groups[0]
        secondary_group_name, secondary_group = entity_groups[1] if len(entity_groups) > 1 else (None, set())
        
        logger.info(f"优先选择实体组: {primary_group_name} (数量: {len(primary_group)})")
        logger.info(f"备选实体组: {secondary_group_name} (数量: {len(secondary_group) if secondary_group else 0})")

        # 在主要组中尝试选择实体
        selected_entity, first_event_entity = await self._try_select_from_group(primary_group, primary_group_name)
        if selected_entity:
            return selected_entity
        
        # 如果主要组没有找到，尝试备选组
        if secondary_group:
            logger.info(f"主要组 {primary_group_name} 没有找到符合要求的实体，尝试备选组 {secondary_group_name}")
            selected_entity, backup_first_event = await self._try_select_from_group(secondary_group, secondary_group_name)
            if selected_entity:
                return selected_entity
            
            # 如果备选组也没有first_event_entity，使用主要组的
            if not first_event_entity:
                first_event_entity = backup_first_event
        
        # 最终兜底：使用第一次选到的事件实体
        if first_event_entity:
            logger.info(f"所有组都没有找到符合要求的实体，使用第一次选到的事件实体作为兜底: {first_event_entity}")
            return first_event_entity
        
        # 最后的兜底：随机选择一个未处理的实体
        if unprocessed_entities:
            fallback_entity = random.choice(list(unprocessed_entities))
            logger.info(f"最终兜底选择: {fallback_entity}")
            return fallback_entity
        
        logger.info("没有找到可拓展的实体")
        return None

    async def _try_select_from_group(self, entity_group: set, group_name: str) -> tuple:
        """从指定的实体组中尝试选择实体
        
        Returns:
            tuple: (selected_entity, first_event_entity)
        """
        import random
        
        if not entity_group:
            return None, None
        
        logger.info(f"=== 在{group_name}组中选择实体 ===")
        
        # 确定候选实体列表
        candidate_entities = list(entity_group)
        
        # 在组内使用事件->时间实体选择逻辑
        max_attempts = len(candidate_entities)
        first_event_entity = None
        attempted_entities = set()
        
        for attempt in range(max_attempts):
            # 过滤掉已尝试的实体
            available_entities = [e for e in candidate_entities if e not in attempted_entities]
            if not available_entities:
                break
                
            # 随机选择一个候选实体
            selected_entity = random.choice(available_entities)
            attempted_entities.add(selected_entity)
            
            logger.info(f"  在{group_name}组尝试 {attempt + 1}/{max_attempts}: 选择实体 {selected_entity}")
            
            # 获取实体类型
            entity_type = self._get_entity_type(selected_entity)
            logger.info(f"  实体类型: {entity_type}")
            
            if entity_type == "event":
                # 记录第一次选到的事件实体
                if first_event_entity is None:
                    first_event_entity = selected_entity
                    logger.info(f"  记录{group_name}组第一次选到的事件实体: {first_event_entity}")
                
                # 查找与事件关联的时间实体
                related_time_entities = self._find_related_time_entities(selected_entity)
                logger.info(f"  事件实体 {selected_entity} 关联的时间实体: {related_time_entities}")
                
                # 过滤出未处理且在当前组中的时间实体
                unprocessed_time_entities = [t for t in related_time_entities 
                                           if t in entity_group and t not in self.processed_entities]
                logger.info(f"  {group_name}组中未处理的时间实体: {unprocessed_time_entities}")
                
                if unprocessed_time_entities:
                    # 选择第一个未处理的时间实体
                    selected_time_entity = unprocessed_time_entities[0]
                    logger.info(f"  在{group_name}组选择关联的时间实体: {selected_time_entity}")
                    return selected_time_entity, first_event_entity
                else:
                    logger.info(f"  事件实体 {selected_entity} 在{group_name}组中没有关联的未处理时间实体，继续尝试其他实体")
                    continue
            else:
                # 非事件实体，直接返回
                logger.info(f"  在{group_name}组选择非事件实体: {selected_entity}")
                return selected_entity, first_event_entity
        
        logger.info(f"在{group_name}组中没有找到符合要求的实体")
        return None, first_event_entity

    async def _select_from_neighbors(self) -> str:
        """从现有节点的邻居中选择一个未处理的实体"""
        import random

        # 收集所有expansion节点的邻居
        all_neighbors = set()
        for expansion_node_id in self.expansion_nodes:
            neighbors = self.node_neighbors.get(expansion_node_id, [])
            for neighbor_id in neighbors:
                neighbor_name = self._get_entity_name(neighbor_id)
                if neighbor_name not in self.processed_entities:
                    all_neighbors.add(neighbor_name)

        if all_neighbors:
            selected = random.choice(list(all_neighbors))
            logger.info(f"从邻居中选择: {selected}")
            return selected

        # 如果还是没有，尝试从所有实体中选择
        all_entity_names = set()
        for entity_info in self.graph_entities.values():
            entity_name = entity_info.get('name', '')
            if entity_name and entity_name not in self.processed_entities:
                all_entity_names.add(entity_name)

        if all_entity_names:
            selected = random.choice(list(all_entity_names))
            logger.info(f"从所有实体中选择: {selected}")
            return selected

        return None

    def _get_entity_name(self, entity_id: str) -> str:
        """获取实体名称"""
        if entity_id in self.graph_entities:
            return self.graph_entities[entity_id].get('name', entity_id)
        return entity_id

    def _get_entity_type(self, entity_name: str) -> str:
        """根据实体名称获取实体类型"""
        for entity_id, entity_info in self.graph_entities.items():
            if entity_info.get('name') == entity_name:
                return entity_info.get('type', 'concept')
        return 'concept'  # 默认类型

    def _find_related_time_entities(self, event_entity_name: str) -> List[str]:
        """查找与事件实体关联的时间实体"""
        related_time_entities = []
        
        # 遍历所有关系，查找与事件实体相关的时间实体
        for relationship in self.graph_relationships:
            source_name = relationship.get('source_name', '')
            target_name = relationship.get('target_name', '')
            relation_type = relationship.get('relation', relationship.get('relationship', ''))
            
            # 检查事件实体作为source的情况
            if source_name == event_entity_name:
                # 检查target是否为时间实体
                target_type = self._get_entity_type(target_name)
                if target_type == "time":
                    related_time_entities.append(target_name)
                    logger.info(f"找到关联时间实体: {event_entity_name} --[{relation_type}]--> {target_name}")
            
            # 检查事件实体作为target的情况
            elif target_name == event_entity_name:
                # 检查source是否为时间实体
                source_type = self._get_entity_type(source_name)
                if source_type == "time":
                    related_time_entities.append(source_name)
                    logger.info(f"找到关联时间实体: {source_name} --[{relation_type}]--> {event_entity_name}")
        
        return list(set(related_time_entities))  # 去重

    def _calculate_entity_distance(self, entity1_name: str, entity2_name: str) -> int:
        """计算两个实体之间的距离（通过关系图的最短路径）
        
        Returns:
            int: 距离值，如果不连通返回-1
        """
        # 标准化实体名称以避免繁简体等差异
        normalized_entity1 = self._normalize_entity_name(entity1_name)
        normalized_entity2 = self._normalize_entity_name(entity2_name)

        if normalized_entity1 == normalized_entity2:
            return 0
        
        # 构建邻接表，使用标准化的实体名称
        adjacency = {}
        for relationship in self.graph_relationships:
            source_name = relationship.get('source_name', '')
            target_name = relationship.get('target_name', '')
            
            if source_name and target_name:
                # 标准化关系中的实体名称
                normalized_source = self._normalize_entity_name(source_name)
                normalized_target = self._normalize_entity_name(target_name)

                # 无向图，双向连接
                if normalized_source not in adjacency:
                    adjacency[normalized_source] = set()
                if normalized_target not in adjacency:
                    adjacency[normalized_target] = set()
                
                adjacency[normalized_source].add(normalized_target)
                adjacency[normalized_target].add(normalized_source)
        
        # BFS寻找最短路径
        from collections import deque
        
        if normalized_entity1 not in adjacency or normalized_entity2 not in adjacency:
            logger.debug(f"实体不在图中 - '{entity1_name}'({normalized_entity1}) 或 '{entity2_name}'({normalized_entity2})")
            logger.debug(f"图中可用实体: {list(adjacency.keys())}")
            return -1  # 实体不在图中
        
        queue = deque([(normalized_entity1, 0)])
        visited = {normalized_entity1}
        
        while queue:
            current_entity, distance = queue.popleft()
            
            if current_entity == normalized_entity2:
                return distance
            
            # 访问所有邻居
            for neighbor in adjacency.get(current_entity, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, distance + 1))
        
        return -1  # 不连通

    def _get_last_iteration_entity(self) -> str:
        """获取上一轮迭代的实体名称"""
        if len(self.expansion_nodes) > 0:
            last_expansion_node_id = self.expansion_nodes[-1]
            return self._get_entity_name(last_expansion_node_id)
        logger.info(f"上一轮迭代实体 '{self.graph_entities[last_expansion_node_id]}'")
        return None

    def _get_available_neighbors(self, node_id: str) -> list:
        """获取节点的可用邻居（不在expansion_nodes中的邻居）"""
        neighbors = self.node_neighbors.get(node_id, [])
        available = [n for n in neighbors if n not in self.expansion_nodes]
        return available

    async def _update_graph_structure(self):
        """从抽取结果更新图结构

        Returns:
            dict: 包含新增实体和新增关系信息的字典
        """
        logger.info(f"=== 更新图结构开始 ===")
        logger.info(f"当前 graph_entities 数量: {len(self.graph_entities)}")
        
        # 记录更新前的实体ID和关系，用于跟踪新增内容
        existing_entity_ids = set(self.graph_entities.keys())
        existing_relationship_keys = self.existing_relations_set.copy()

        # 读取所有抽取结果的JSON文件
        input_dir = Path(self.settings.GRAPHRAG_INPUT_DIR)
        extraction_files = list(input_dir.glob("*_extraction.json"))

        logger.info(f"找到 {len(extraction_files)} 个抽取文件: {[f.name for f in extraction_files]}")

        for file_path in extraction_files:
            try:
                extraction_data = await asyncio.to_thread(self._read_json_file, file_path)

                # 更新实体
                extracted_entities = extraction_data.get('extracted_entities', [])
                logger.info(f"从文件 {file_path.name} 读取到 {len(extracted_entities)} 个实体")

                for i, entity_data in enumerate(extracted_entities):
                    if isinstance(entity_data, dict):
                        entity_name = entity_data.get('name', '')
                        entity_type = entity_data.get('type', 'concept')
                        entity_desc = entity_data.get('description', '')
                        entity_id = entity_data.get('id', '')
                        if not entity_id:
                            entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)

                        logger.info(f"  实体{i+1}: {entity_name} -> {entity_id}")

                        # 合并实体信息
                        if entity_id not in self.graph_entities:
                            self.graph_entities[entity_id] = {
                                'id': entity_id,
                                'name': entity_name,
                                'type': entity_type,
                                'description': entity_desc
                            }
                            self.node_neighbors[entity_id] = []
                            logger.info(f"    -> 新增实体: {entity_name} ({entity_id})")
                        else:
                            # 更新实体信息（保留更长的名称和更详细的描述）
                            existing = self.graph_entities[entity_id]
                            if len(entity_name) > len(existing.get('name', '')):
                                existing['name'] = entity_name
                            if len(entity_desc) > len(existing.get('description', '')):
                                existing['description'] = entity_desc
                            logger.info(f"    -> 更新现有实体: {entity_name} ({entity_id})")

                    elif isinstance(entity_data, str):
                        entity_name = entity_data
                        entity_type = 'concept'
                        entity_desc = f'抽取的实体：{entity_name}'
                        entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)

                        logger.info(f"  字符串实体{i+1}: {entity_name} -> {entity_id}")

                        if entity_id not in self.graph_entities:
                            self.graph_entities[entity_id] = {
                                'id': entity_id,
                                'name': entity_name,
                                'type': entity_type,
                                'description': entity_desc
                            }
                            self.node_neighbors[entity_id] = []
                            logger.info(f"    -> 新增字符串实体: {entity_name} ({entity_id})")

                # 更新关系和邻居
                extracted_relationships = extraction_data.get('extracted_relationships', [])
                logger.info(f"从文件 {file_path.name} 读取到 {len(extracted_relationships)} 个关系")

                for i, rel in enumerate(extracted_relationships):
                    # 优先使用文件中已有的ID字段
                    source_id = rel.get('source_id', '')
                    target_id = rel.get('target_id', '')
                    source_name = rel.get('source', '')
                    target_name = rel.get('target', '')
                    relation = rel.get('relation', rel.get('relationship', ''))

                    logger.info(f"  关系{i+1}: {source_name} --[{relation}]--> {target_name}")

                    # 如果没有ID，通过名称查找对应的实体ID
                    if not source_id and source_name:
                        source_id = self._find_entity_id_by_name(source_name)
                    if not target_id and target_name:
                        target_id = self._find_entity_id_by_name(target_name)

                    logger.info(f"    source_id: {source_id}, target_id: {target_id}")

                    if source_id and target_id:
                        # 添加邻居关系
                        if target_id not in self.node_neighbors.get(source_id, []):
                            self.node_neighbors.setdefault(source_id, []).append(target_id)
                        if source_id not in self.node_neighbors.get(target_id, []):
                            self.node_neighbors.setdefault(target_id, []).append(source_id)

                        # 存储关系信息
                        relationship = {
                            'source': source_id,
                            'target': target_id,
                            'relation': relation,
                            'source_name': source_name,
                            'target_name': target_name
                        }

                        # 避免重复关系
                        rel_exists = any(
                            r['source'] == source_id and r['target'] == target_id and r['relation'] == relation
                            for r in self.graph_relationships
                        )
                        if not rel_exists:
                            self.graph_relationships.append(relationship)
                            logger.info(f"    -> 添加关系: {source_name} --[{relation}]--> {target_name}")
                        else:
                            logger.info(f"    -> 关系已存在，跳过")
                    else:
                        logger.warning(f"    -> 关系无效，找不到对应的实体ID")

            except Exception as e:
                logger.error(f"读取抽取文件 {file_path} 失败: {e}", exc_info=True)
                continue

        # 计算新增实体和新增关系
        current_entity_ids = set(self.graph_entities.keys())
        new_entities = current_entity_ids - existing_entity_ids

        # 构建当前基于ID的关系键集合
        current_relationship_keys = set()
        for rel in self.graph_relationships:
            source_id = rel.get('source', '')
            target_id = rel.get('target', '')
            relation = rel.get('relation', '')
            if source_id and target_id and relation:
                current_relationship_keys.add((source_id, relation, target_id))

        new_relationships = current_relationship_keys - existing_relationship_keys

        # 更新最新一轮迭代产生的实体（使用ID作为标识）
        self.latest_iteration_entities.clear()
        for entity_id in new_entities:
            entity_info = self.graph_entities.get(entity_id, {})
            entity_name = entity_info.get('name', '')
            if entity_name:
                self.latest_iteration_entities.add(entity_name)
        
        # 更新entity_name_to_entities映射（为所有实体）
        self.entity_name_to_entities.clear()
        for entity_id, entity_info in self.graph_entities.items():
            entity_name = entity_info.get('name', '')
            if entity_name:
                self.entity_name_to_entities[entity_name] = entity_info


        # 更新existing_relations_set - 使用基于ID的关系键
        self.existing_relations_set.clear()
        for rel in self.graph_relationships:
            source_id = rel.get('source', '')
            target_id = rel.get('target', '')
            relation = rel.get('relation', '')

            if source_id and target_id and relation:
                # 使用基于ID的键值进行去重检查
                rel_key = (source_id, relation, target_id)
                self.existing_relations_set.add(rel_key)

        logger.info(f"=== 图结构更新完成 ===")
        logger.info(f"最终 graph_entities 数量: {len(self.graph_entities)}")
        logger.info(f"最终 graph_relationships 数量: {len(self.graph_relationships)}")
        logger.info(f"新增实体数量: {len(new_entities)}")
        logger.info(f"新增关系数量: {len(new_relationships)}")
        logger.info(f"entity_name_to_entities 数量: {len(self.entity_name_to_entities)}")
        logger.info(f"existing_relations_set 数量: {len(self.existing_relations_set)}")
        logger.info(f"实体列表: {[entity['name'] for entity in self.graph_entities.values()]}")
        logger.info(f"最新一轮迭代产生的实体: {list(self.latest_iteration_entities)}")

        # 打印新增实体和关系详情
        if new_entities:
            logger.info("新增实体详情:")
            for entity_id in new_entities:
                entity_info = self.graph_entities.get(entity_id, {})
                entity_name = entity_info.get('name', 'N/A')
                entity_type = entity_info.get('type', 'N/A')
                logger.info(f"  - {entity_name} [{entity_type}] ({entity_id})")

        if new_relationships:
            logger.info("新增关系详情:")
            for rel_key in new_relationships:
                source_id, relation, target_id = rel_key
                source_name = self.graph_entities.get(source_id, {}).get('name', source_id)
                target_name = self.graph_entities.get(target_id, {}).get('name', target_id)
                logger.info(f"  - {source_name} --[{relation}]--> {target_name}")

        # 打印部分关系去重集合用于调试
        if self.existing_relations_set:
            logger.info("现有关系去重集合样例:")
            for i, rel_key in enumerate(list(self.existing_relations_set)[:5]):  # 只显示前5个
                source_id, relation, target_id = rel_key
                source_name = self.graph_entities.get(source_id, {}).get('name', source_id)
                target_name = self.graph_entities.get(target_id, {}).get('name', target_id)
                logger.info(f"  {i+1}. {source_name} --[{relation}]--> {target_name}")

        # 返回新增实体和关系信息
        return {
            'new_entities': list(new_entities),
            'new_relationships': list(new_relationships),
            'new_entity_count': len(new_entities),
            'new_relationship_count': len(new_relationships)
        }

    def _find_entity_id_by_name(self, entity_name: str) -> str:
        """根据实体名称查找ID"""
        normalized_name = self._normalize_entity_name(entity_name)

        for entity_id, entity_info in self.graph_entities.items():
            if self._normalize_entity_name(entity_info.get('name', '')) == normalized_name:
                return entity_id
        return None

    async def _send_expansion_update(self, iteration: int, action: str, final: bool = False):
        """发送expansion状态的图更新"""
        try:
            # 构建节点列表
            graph_nodes = []
            for entity_id, entity_info in self.graph_entities.items():
                node_data = {
                    'id': entity_id,
                    'name': entity_info.get('name', entity_id),
                    'type': entity_info.get('type', 'concept'),
                    'description': entity_info.get('description', ''),
                    'group': hash(entity_info.get('type', 'concept')) % 10
                }

                # 设置expansion状态
                if entity_id in self.expansion_nodes:
                    node_data['expansion_status'] = 'expansion'
                    node_data['expansion_order'] = self.expansion_nodes.index(entity_id)

                    # 当前节点特殊标识
                    if entity_id == self.current_node:
                        node_data['expansion_status'] = 'current'
                else:
                    node_data['expansion_status'] = 'normal'

                graph_nodes.append(node_data)

            # 构建关系列表
            graph_links = []
            for rel in self.graph_relationships:
                link_data = {
                    'source': rel['source'],
                    'target': rel['target'],
                    'relation': rel['relation'],
                    'source_name': rel.get('source_name', ''),
                    'target_name': rel.get('target_name', '')
                }
                graph_links.append(link_data)
            
            # 添加调试日志：打印前几个关系数据
            if graph_links:
                logger.info(f"=== 发送的关系数据样例 ===")
                for i, link in enumerate(graph_links[:3]):  # 只打印前3个
                    logger.info(f"关系{i+1}: {link['source_name']} --[{link['relation']}]--> {link['target_name']}")
                logger.info(f"总共发送 {len(graph_links)} 个关系")

            # 构建expansion状态信息
            expansion_info = {
                'iteration': iteration,
                'action': action,
                'expansion_nodes': [
                    {
                        'id': node_id,
                        'name': self._get_entity_name(node_id),
                        'order': idx
                    }
                    for idx, node_id in enumerate(self.expansion_nodes)
                ],
                'current_node': {
                    'id': self.current_node,
                    'name': self._get_entity_name(self.current_node)
                } if self.current_node else None,
                'total_nodes': len(self.graph_entities),
                'total_expansion_nodes': len(self.expansion_nodes),
                'final': final
            }

            # 发送更新
            if self.graph_update_callback:
                graph_data = {
                    'nodes': graph_nodes,
                    'links': graph_links,
                    'expansion_info': expansion_info
                }
                self.graph_update_callback(graph_data)
                logger.info(f"发送expansion更新: {action}, expansion节点数: {len(self.expansion_nodes)}, 当前节点: {self._get_entity_name(self.current_node) if self.current_node else 'None'}")
            else:
                logger.warning("没有设置图更新回调函数")

        except Exception as e:
            logger.error(f"发送expansion更新失败: {e}")
    
    async def _send_graph_update(self):
        """发送实时图更新"""
        try:
            # 构建当前的图信息
            current_graph = await self._build_simple_graph_info()
            
            # 转换为前端需要的格式
            graph_nodes = []
            entities = current_graph.get('entities', [])
            for i, entity in enumerate(entities):
                if isinstance(entity, str):
                    graph_nodes.append({
                        'id': entity,
                        'name': entity,
                        'type': 'entity',
                        'group': hash(entity) % 10
                    })
                else:
                    entity_id = entity.get('id', f'Entity_{i}')
                    entity_name = entity.get('name', f'Entity_{i}')
                    entity_type = entity.get('type', 'unknown')
                    
                    graph_nodes.append({
                        'id': entity_id,  # 使用唯一ID
                        'name': entity_name,
                        'type': entity_type,
                        'group': hash(entity_type) % 10,
                        'description': entity.get('description', '')
                    })
            
            graph_links = []
            relationships = current_graph.get('relationships', [])
            for relation in relationships:
                if isinstance(relation, dict):
                    # 优先使用ID，如果没有则使用名称
                    source = relation.get('source_id', relation.get('source', ''))
                    target = relation.get('target_id', relation.get('target', ''))
                    rel_type = relation.get('relationship', relation.get('relation', 'related_to'))
                    
                    if source and target:
                        graph_links.append({
                            'source': source,
                            'target': target,
                            'relation': rel_type,  # 使用'relation'字段与前端保持一致
                            'type': rel_type,
                            'source_name': relation.get('source_name', ''),
                            'target_name': relation.get('target_name', '')
                        })
            
            # 将图数据传递给一个全局更新函数
            self._notify_graph_update(graph_nodes, graph_links)
            
        except Exception as e:
            logger.error(f"发送图更新失败: {e}")
    
    def _notify_graph_update(self, nodes, links):
        """通知图更新"""
        try:
            # 使用回调函数发送实时更新
            if self.graph_update_callback:
                graph_data = {
                    'nodes': [{'id': node['id'], 'name': node['name'], 'type': node['type'], 'description': node.get('description', '')} for node in nodes],
                    'links': [{'source': link['source'], 'target': link['target'], 'relation': link['relation'], 'source_name': link.get('source_name', ''), 'target_name': link.get('target_name', '')} for link in links]
                }
                self.graph_update_callback(graph_data)
                logger.info(f"实时图更新回调: {len(nodes)} 个节点, {len(links)} 个关系")
            else:
                logger.warning("没有设置图更新回调函数")
                
        except Exception as e:
            logger.error(f"通知图更新失败: {e}")
    
    async def _generate_search_queries(self, entity: str) -> List[str]:
        """生成搜索查询 - 简化版本，每个实体只生成一个查询"""
        prompt = f"""
        基于实体 "{entity}"，生成一个最相关的搜索查询，用于发现与该实体直接相关的知识和关系。
        
        目标：获取能够拓展"{entity}"知识网络的相关信息。
        
        要求：
        1. 查询应该关注"{entity}"的组成部分、应用场景、相关技术或概念
        2. 优先获取能够发现"{entity}"与其他实体关系的信息
        3. 查询应该能够获取到可以构建知识图谱连接的具体内容
        4. 避免过于宽泛的查询，要有针对性
        
        查询示例格式：
        - "{entity} 定义 主要应用 足球战术分析"
        - "{entity}的核心定义及实战应用分析"
        - "{entity}历史、荣誉及当前阵容"
        
        请直接返回一个搜索查询词，不需要JSON格式。
        """
        
        try:
            response = await self.llm_client.generate_response(prompt)
            
            if not response or response.strip() == "":
                raise ValueError("LLM 返回空响应")
            
            # 清理响应文本，取第一行作为查询
            query = response.strip().split('\n')[0].strip(' -"[],"')
            
            if not query or len(query) < 3:
                raise ValueError("生成的查询无效")
            
            # 记录查询
            self.stats['search_queries'].append(query)
            
            logger.info(f"为实体 '{entity}' 生成搜索查询: {query}")
            return [query]  # 返回包含一个查询的列表
            
        except Exception as e:
            logger.error(f"生成搜索查询失败: {e}")
            # 返回默认查询
            default_query = f"{entity} 是什么"
            self.stats['search_queries'].append(default_query)
            return [default_query]
    
    async def _process_search_results(self, entity: str, query: str) -> List[str]:
        """处理搜索结果 - 立即进行LLM实体抽取"""
        all_texts = []
        new_entities = []
        
        try:
            # 使用Tavily搜索：直接获取搜索结果的content内容，现在获取前5个结果
            contents = await self.search_engine.get_search_contents(query, limit=5)
            
            # 处理每个内容
            for content in contents:
                if content and len(content.strip()) > 50:  # 过滤太短的内容
                    # 清理文本
                    cleaned_text = await self.text_processor.clean_text(content)
                    if cleaned_text:
                        all_texts.append(cleaned_text)
            # logger.info(f"all_texts：{all_texts}")
            
            # 立即进行LLM实体和关系抽取
            if all_texts:
                combined_text = "\n\n".join(all_texts)
                extracted_entities, extracted_relationships = await self._extract_entities_with_llm(combined_text, entity)
                
                # 从实体对象中提取名称（保持向后兼容）
                for entity_obj in extracted_entities:
                    if isinstance(entity_obj, dict):
                        entity_name = entity_obj.get('name', '')
                        if entity_name:
                            new_entities.append(entity_name)
                    elif isinstance(entity_obj, str):
                        # 兼容旧格式
                        new_entities.append(entity_obj)
                
                # 保存抽取的关系信息到文件
                await self._save_extraction_results(entity, all_texts, extracted_entities, extracted_relationships)
            
        except Exception as e:
            logger.error(f"处理搜索查询 '{query}' 失败: {e}")
            return []
        
        # 记录处理的文本
        self.stats['processed_texts'].extend(all_texts)
        
        # 注释掉立即的图更新，避免与后续的_update_graph_structure重复读取文件
        # 图更新将在_update_graph_structure之后统一进行
        # if new_entities or all_texts:
        #     try:
        #         await self._send_graph_update()
        #     except Exception as e:
        #         logger.error(f"发送实时图更新失败: {e}")
        
        logger.info(f"为实体 '{entity}' 处理了 {len(all_texts)} 个文本，通过LLM发现 {len(new_entities)} 个新实体")
        return list(set(new_entities))

    async def _extract_entities_with_llm(self, text: str, current_entity: str = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """使用LLM从文本中抽取实体和关系，并进行Wikidata实体链接"""
        
        # 步骤1: 文本预筛选
        logger.info("=== 开始文本预筛选阶段 ===")
        filtered_text = await self._prefilter_text_with_llm(text, current_entity)
        logger.info("=== 文本预筛选完成，开始实体关系抽取 ===")
        
        # 使用筛选后的文本继续原有的处理流程
        current_graph = await self._build_simple_graph_info()
        
        # 提取已有实体列表
        existing_entities = []
        entities_data = current_graph.get('entities', [])
        for entity in entities_data:
            if isinstance(entity, str):
                existing_entities.append(entity)
            elif isinstance(entity, dict):
                entity_id = entity.get('id', '')
                entity_name = entity.get('name', '')
                entity_type = entity.get('type', '')
                entity_desc = entity.get('description', '')
                # 格式化显示：名称[类型](ID前8位)
                if entity_type and entity_id:
                    short_id = entity_id[-8:] if len(entity_id) > 8 else entity_id
                    existing_entities.append(f"{entity_name}[{entity_type}]({short_id})")
                elif entity_type:
                    existing_entities.append(f"{entity_name}[{entity_type}]")
                else:
                    existing_entities.append(entity_name)
        
        existing_entities_str = "、".join(existing_entities) if existing_entities else "无"
        
        # 提取已有关系列表
        existing_relationships = []
        relationships_data = current_graph.get('relationships', [])
        for rel in relationships_data:
            if isinstance(rel, dict):
                source_name = rel.get('source_name', rel.get('source', ''))
                target_name = rel.get('target_name', rel.get('target', ''))
                relation_type = rel.get('relation', rel.get('relationship', ''))
                if source_name and target_name and relation_type:
                    existing_relationships.append(f"{source_name} --[{relation_type}]--> {target_name}")
        
        existing_relationships_str = "\n".join(existing_relationships) if existing_relationships else "无"
        
        if current_entity:
            prompt = f"""
            基于核心实体"{current_entity}"，从文本中抽取实体和关系。

            当前已有实体：{existing_entities_str}
            当前已有关系：{existing_relationships_str}
            
            文本：{filtered_text}

            请以JSON格式返回结果：
            {{
                "entities": [
                    {{"name": "苹果公司", "type": "organization", "description": ""}},
                    {{"name": "苹果发布iPhone15", "type": "event", "description": ""}},
                    {{"name": "2024年03月15日", "type": "time", "description": ""}},
                    {{"name": "iPhone15", "type": "technology", "description": ""}}
                ],
                "relationships": [
                    {{"source": "苹果公司", "relation": "发起", "target": "苹果发布iPhone15"}},
                    {{"source": "苹果发布iPhone15", "relation": "发生于", "target": "2024年03月15日"}},
                    {{"source": "苹果发布iPhone15", "relation": "推出", "target": "iPhone15"}}
                ]
            }}

            **实体类型**：person, organization, location, technology, concept, event, time

            **关键要求**：
            1. **避免重复**：检查已有实体和关系列表，不要重复抽取
            2. **事件实体**：重大事件用"主体+动作+客体"格式命名（如"苹果公司发布iPhone15"）
            3. **时间格式**：只使用yyyy年MM月dd日、yyyy年MM月、yyyy年格式，拒绝相对时间
            4. **关系明确**：使用具体动词，避免"相关"、"关联"等模糊词
            5. **禁止孤立实体**：每个实体必须至少在一个关系中出现
            6. **实体关系一致性**：entities中的实体必须在relationships中作为source或target出现
            7. **最多10个关系**：优先质量，控制数量

            返回有效JSON格式，不包含其他文本。如无符合标准的内容，返回空数组。
            """
        else:
            logger.warning("当前实体为空，不进行实体提取")
            return [], []
        
        try:
            response = await self.llm_client.generate_response(prompt)

            if not response:
                logger.warning("llm response 为空")
                return [], []
            
            # 使用JSON解析响应
            raw_entities = []
            relationships = []
            
            try:
                # 清理响应，移除可能的代码块标记
                clean_response = response.strip()
                if clean_response.startswith('```json'):
                    clean_response = clean_response.replace('```json', '').replace('```', '').strip()
                elif clean_response.startswith('```'):
                    clean_response = clean_response.replace('```', '').strip()
                
                # 解析JSON
                data = json.loads(clean_response)
                
                # 提取关系并进行质量过滤
                relations_data = data.get('relationships', [])
                filtered_relationships = []
                
                # 构建已有关系的集合，用于去重检查
                existing_relations_set = self.existing_relations_set.copy()

                for rel_data in relations_data:
                    if isinstance(rel_data, dict):
                        source = rel_data.get('source', '').strip()
                        target = rel_data.get('target', '').strip()
                        relation_type = rel_data.get('relation', '').strip()
                        
                        if source and target and relation_type:
                            # 1. 检查关系质量
                            if not self._is_high_quality_relationship(relation_type):
                                logger.info(f"跳过低质量关系: {source} --[{relation_type}]--> {target}")
                                continue
                            
                            # 2. 检查关系是否重复
                            rel_key = (source.lower(), relation_type.lower(), target.lower())
                            if rel_key in existing_relations_set:
                                logger.info(f"跳过重复关系: {source} --[{relation_type}]--> {target}")
                                continue
                            
                            # 3. 通过过滤的关系
                            filtered_relationships.append({
                                'source': source,
                                'target': target,
                                'relation': relation_type,  # 统一使用'relation'字段名
                                'weight': 0.8  # 由LLM抽取的关系权重较高
                            })
                            
                            # 将新关系添加到去重集合中
                            existing_relations_set.add(rel_key)
                            
                            logger.info(f"保存高质量新关系: {source} --[{relation_type}]--> {target}")

                # 排除孤立节点
                filtered_graph_relations = self._recursively_filter_relationships_by_entities(
                    filtered_relationships,
                    max_relations=15
                )

                relationships = filtered_graph_relations

                # 提取实体并验证与expansion节点的关联性
                all_entities_from_data = data.get('entities', [])
                entities_in_relationships = set()
                
                # 收集过滤后关系中涉及的所有实体
                for rel in relationships:
                    entities_in_relationships.add(rel['source'])
                    entities_in_relationships.add(rel['target'])
                
                # 创建实体名称到ID的映射
                entity_name_to_id = {}
                raw_entities = []
                
                # 只为在高质量关系中出现的实体生成ID和保存
                for entity_data in all_entities_from_data:
                    if isinstance(entity_data, dict):
                        entity_name = entity_data.get('name', '').strip()
                        entity_type = entity_data.get('type', 'concept').strip()
                        entity_desc = entity_data.get('description', '').strip()
                        
                        if entity_name:
                            # 生成唯一ID
                            entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)
                            entity_name_to_id[entity_name] = entity_id
                            
                            # 只保存在高质量关系中出现的实体
                            if entity_name in entities_in_relationships:
                                raw_entities.append({
                                    'id': entity_id,
                                    'name': entity_name,
                                    'type': entity_type,
                                    'description': entity_desc
                                })
                                logger.info(f"保存关联实体: {entity_name} [{entity_type}]")
                            else:
                                logger.info(f"跳过无关实体: {entity_name} [{entity_type}] - 不在任何高质量关系中")

                # 更新关系中的实体引用，使用ID而不是名称
                for relationship in relationships:
                    source_name = relationship.get('source', '').strip()
                    target_name = relationship.get('target', '').strip()
                    
                    # 处理source实体ID
                    if source_name in entity_name_to_id:
                        relationship['source_id'] = entity_name_to_id[source_name]
                        relationship['source_name'] = source_name
                    elif source_name in self.entity_name_to_entities:
                        # 从现有实体映射中获取ID
                        existing_entity = self.entity_name_to_entities[source_name]
                        relationship['source_id'] = existing_entity.get('id', source_name)
                        relationship['source_name'] = source_name
                    else:
                        # 如果都找不到对应的实体ID，使用名称作为ID
                        relationship['source_id'] = source_name
                        relationship['source_name'] = source_name
                    
                    # 处理target实体ID
                    if target_name in entity_name_to_id:
                        relationship['target_id'] = entity_name_to_id[target_name]
                        relationship['target_name'] = target_name
                    elif target_name in self.entity_name_to_entities:
                        # 从现有实体映射中获取ID
                        existing_entity = self.entity_name_to_entities[target_name]
                        relationship['target_id'] = existing_entity.get('id', target_name)
                        relationship['target_name'] = target_name
                    else:
                        # 如果都找不到对应的实体ID，使用名称作为ID
                        relationship['target_id'] = target_name
                        relationship['target_name'] = target_name
                
                # 如果没有任何实体有关系，记录警告
                if all_entities_from_data and not raw_entities:
                    logger.warning(f"抽取的 {len(all_entities_from_data)} 个实体都没有关系连接，已过滤")
                
                logger.info(f"实体验证完成: 原始 {len(all_entities_from_data)} 个实体，有关系连接 {len(raw_entities)} 个实体")
                
                # 打印原始实体和关系
                logger.info(f"=== 原始实体和关系 ===")
                logger.info(f"原始实体列表:")
                for i, entity in enumerate(raw_entities):
                    if isinstance(entity, dict):
                        entity_id = entity.get('id', 'N/A')
                        entity_name = entity.get('name', 'N/A')
                        entity_type = entity.get('type', 'N/A')
                        entity_desc = entity.get('description', 'N/A')
                        logger.info(f"  实体{i+1}: [{entity_id}] {entity_name} [{entity_type}] - {entity_desc}")
                    else:
                        logger.info(f"  实体{i+1}: {entity}")
                logger.info(f"原始关系列表:")
                for i, rel in enumerate(relationships):
                    source_info = f"{rel.get('source_name', rel.get('source', 'N/A'))}({rel.get('source_id', 'N/A')})"
                    target_info = f"{rel.get('target_name', rel.get('target', 'N/A'))}({rel.get('target_id', 'N/A')})"
                    relation_type = rel.get('relation', rel.get('relationship', 'N/A'))
                    logger.info(f"  关系{i+1}: {source_info} --[{relation_type}]--> {target_info}")
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失败: {e}, 响应内容: {response}")
                # 回退到简单解析
                lines = response.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('{') and not line.startswith('}'):
                        # 简单提取可能的实体
                        words = line.split()
                        for word in words:
                            if len(word) > 2 and word not in ['是', '的', '和', '与', '或']:
                                raw_entities.append(word)
                raw_entities = list(set(raw_entities[:5]))  # 去重并限制数量
            
            # # 进行实体链接，获取标准化的实体名称
            # standardized_entities = []
            # if raw_entities:
            #     logger.info(f"对 {len(raw_entities)} 个抽取的实体进行Wikidata链接")
                
            #     # 使用EntityLinker进行批量实体链接
            #     async with EntityLinker() as linker:
            #         linking_results = await linker.link_entities_batch(raw_entities, language="zh")
                
            #     for raw_entity in raw_entities:
            #         linking_result = linking_results.get(raw_entity, {})
                    
            #         if linking_result.get('success', False):
            #             # 使用标准化的实体名称
            #             standard_name = linking_result.get('standard_name', raw_entity)
            #             standardized_entities.append(standard_name)
                        
            #             logger.info(f"实体链接成功: '{raw_entity}' -> '{standard_name}' "
            #                       f"(ID: {linking_result.get('wikidata_id', 'N/A')}, "
            #                       f"置信度: {linking_result.get('confidence', 0):.2f})")
            #         else:
            #             # 链接失败，使用原始名称
            #             standardized_entities.append(raw_entity)
            #             logger.warning(f"实体链接失败: '{raw_entity}' - {linking_result.get('error', '未知错误')}")
                
            #     # 更新关系中的实体名称
            #     entity_mapping = {}
            #     for i, raw_entity in enumerate(raw_entities):
            #         if i < len(standardized_entities):
            #             entity_mapping[raw_entity] = standardized_entities[i]
                
            #     # 应用映射到关系中
            #     for relation in relationships:
            #         original_source = relation['source']
            #         original_target = relation['target']
                    
            #         if relation['source'] in entity_mapping:
            #             relation['source'] = entity_mapping[relation['source']]
            #             relation['source_linked'] = True
            #         else:
            #             relation['source_linked'] = False
                        
            #         if relation['target'] in entity_mapping:
            #             relation['target'] = entity_mapping[relation['target']]
            #             relation['target_linked'] = True
            #         else:
            #             relation['target_linked'] = False
                
            #     # 打印映射后的实体和关系
            #     logger.info(f"=== 映射后的实体和关系 ===")
            #     logger.info(f"实体映射表:")
            #     for raw_entity, standard_entity in entity_mapping.items():
            #         logger.info(f"  '{raw_entity}' -> '{standard_entity}'")
            #     logger.info(f"标准化实体列表: {standardized_entities}")
            #     logger.info(f"映射后关系列表:")
            #     for i, rel in enumerate(relationships):
            #         source_status = "✓" if rel.get('source_linked', False) else "✗"
            #         target_status = "✓" if rel.get('target_linked', False) else "✗"
            #         logger.info(f"  关系{i+1}: {rel['source']} ({source_status}) --[{rel['relationship']}]--> {rel['target']} ({target_status})")
            
            # logger.info(f"实体抽取和链接完成 - 原始实体: {len(raw_entities)}, 标准化实体: {len(standardized_entities)}, 关系: {len(relationships)}")
            return raw_entities, relationships
            
        except Exception as e:
            logger.error(f"LLM实体关系抽取失败: {e}")
            return [], []
    
    async def _save_extraction_results(self, entity: str, texts: List[str], entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]]):
        """保存抽取的实体和关系结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 保存文本文件
        text_filename = f"{entity}_{timestamp}.txt"
        text_filepath = Path(self.settings.GRAPHRAG_INPUT_DIR) / text_filename
        combined_text = "\n\n".join(texts)
        
        # 使用asyncio.to_thread将同步文件I/O转为异步
        import asyncio
        await asyncio.to_thread(self._write_text_file, text_filepath, combined_text)
        
        # 保存抽取结果的JSON文件
        extraction_filename = f"{entity}_{timestamp}_extraction.json"
        extraction_filepath = Path(self.settings.GRAPHRAG_INPUT_DIR) / extraction_filename
        extraction_data = {
            'source_entity': entity,
            'timestamp': timestamp,
            'extracted_entities': entities,
            'extracted_relationships': relationships,
            'source_texts': texts
        }
        
        await asyncio.to_thread(self._write_json_file, extraction_filepath, extraction_data)
        
        logger.info(f"保存抽取结果到: {extraction_filepath}")
    
    def _write_text_file(self, filepath: Path, content: str):
        """同步写入文本文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _write_json_file(self, filepath: Path, data: dict):
        """同步写入JSON文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def _build_simple_graph_info(self) -> Dict[str, Any]:
        """构建简化的图结构信息（基于已抽取的实体）"""
        input_dir = Path(self.settings.GRAPHRAG_INPUT_DIR)
        all_entities = {}  # 使用字典避免重复
        all_relationships = []
        
        try:
            # 读取所有抽取结果的JSON文件
            import asyncio
            extraction_files = list(input_dir.glob("*_extraction.json"))
            
            for file_path in extraction_files:
                try:
                    # 使用异步文件读取
                    extraction_data = await asyncio.to_thread(self._read_json_file, file_path)
                    
                    # 收集实体
                    extracted_entities = extraction_data.get('extracted_entities', [])
                    for entity_data in extracted_entities:
                        if isinstance(entity_data, dict):
                            # 新格式：包含id、name、type、description的字典
                            entity_name = entity_data.get('name', '')
                            entity_type = entity_data.get('type', 'concept')
                            entity_desc = entity_data.get('description', '')
                            
                            # 生成标准化的ID（简化版本，不使用description）
                            entity_id = self._generate_entity_id(entity_name, entity_type, "")
                            
                            # 合并实体（如果已存在，保留更详细的描述）
                            if entity_id not in all_entities:
                                all_entities[entity_id] = {
                                    'id': entity_id,
                                'name': entity_name,
                                    'type': entity_type,
                                    'description': entity_desc
                                }
                            else:
                                # 如果实体已存在，更新描述（保留更长更详细的）
                                existing = all_entities[entity_id]
                                if len(entity_desc) > len(existing.get('description', '')):
                                    existing['description'] = entity_desc
                                # 保留原始名称格式（可能包含大小写等）
                                if len(entity_name) > len(existing.get('name', '')):
                                    existing['name'] = entity_name
                                    
                        elif isinstance(entity_data, str):
                            # 兼容旧格式：字符串
                            entity_name = entity_data
                            entity_type = 'concept'
                            entity_desc = f'抽取的实体：{entity_name}'
                            entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)
                            
                            # 同样进行合并处理
                            if entity_id not in all_entities:
                                all_entities[entity_id] = {
                                    'id': entity_id,
                                    'name': entity_name,
                                    'type': entity_type,
                                    'description': entity_desc
                                }
                            else:
                                # 保留原始名称格式
                                existing = all_entities[entity_id]
                                if len(entity_name) > len(existing.get('name', '')):
                                    existing['name'] = entity_name
                    
                    # 收集关系
                    extracted_relationships = extraction_data.get('extracted_relationships', [])
                    all_relationships.extend(extracted_relationships)
                    
                except Exception as e:
                    logger.error(f"读取抽取文件 {file_path} 失败: {e}")
                    continue
            
            # 如果没有抽取结果，回退到基于文件名的简单方法
            if not all_entities:
                text_files = list(input_dir.glob("*.txt"))
                for file_path in text_files:
                    entity_name = file_path.stem.split('_')[0]
                    entity_type = 'concept'
                    entity_desc = f'文件实体：{entity_name}'
                    entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)
                    
                    all_entities[entity_id] = {
                        'id': entity_id,
                        'name': entity_name,
                        'type': entity_type,
                        'description': entity_desc
                    }
                
                # 创建简单的关系作为后备
                entity_list = list(all_entities.values())
                for i, entity1 in enumerate(entity_list):
                    for j, entity2 in enumerate(entity_list[i+1:], i+1):
                        all_relationships.append({
                            'source_id': entity1['id'],
                            'source_name': entity1['name'],
                            'target_id': entity2['id'],
                            'target_name': entity2['name'],
                            'relationship': 'related_to',
                            'weight': 0.3  # 较低权重表示这是推测的关系
                        })
            
            entities_list = list(all_entities.values())
            graph_info = {
                'node_count': len(entities_list),
                'relationship_count': len(all_relationships),
                'entities': entities_list,
                'relationships': all_relationships,
                'communities': []
            }
            
            logger.info(f"构建图信息：{len(entities_list)}个节点，{len(all_relationships)}个关系")
            logger.info(f"抽取的关系类型: {set(r.get('relationship', 'unknown') for r in all_relationships)}")
            
            # 打印实体类型统计
            entity_types = {}
            for entity in entities_list:
                entity_type = entity.get('type', 'unknown')
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
            logger.info(f"实体类型分布: {entity_types}")
            
            # 打印部分实体信息（前5个）
            logger.info("实体样例:")
            for i, entity in enumerate(entities_list[:5]):
                if isinstance(entity, dict):
                    entity_id = entity.get('id', 'N/A')
                    entity_name = entity.get('name', 'N/A')
                    entity_type = entity.get('type', 'N/A')
                    entity_desc = entity.get('description', 'N/A')
                    # 安全处理 entity_id，确保它是字符串类型
                    if isinstance(entity_id, str) and len(entity_id) > 8:
                        short_id = entity_id[-8:]
                    else:
                        short_id = str(entity_id) if entity_id != 'N/A' else 'N/A'
                    logger.info(f"  {i+1}. [{short_id}] {entity_name} [{entity_type}] - {entity_desc}")
                else:
                    logger.info(f"  {i+1}. [警告] 非字典格式的实体: {entity}")
            
            return graph_info
            
        except Exception as e:
            logger.error(f"构建图信息失败: {e}")
            return {
                'node_count': 0,
                'relationship_count': 0,
                'entities': [],
                'relationships': [],
                'communities': []
            }

    def _read_json_file(self, filepath: Path) -> dict:
        """同步读取JSON文件"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    async def _save_texts_for_graphrag(self, entity: str, texts: List[str]):
        """将文本保存到 GraphRag 输入目录"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{entity}_{timestamp}.txt"
        filepath = Path(self.settings.GRAPHRAG_INPUT_DIR) / filename
        
        # 合并所有文本
        combined_text = "\n\n".join(texts)
        
        # 保存到文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(combined_text)
        
        logger.info(f"保存文本到 GraphRag 输入目录: {filepath}")
    
    async def _run_graphrag_indexing(self):
        """运行 GraphRag 索引"""
        logger.info("开始运行 GraphRag 索引...")
        
        import subprocess
        
        try:
            # 确保环境变量被正确设置
            os.environ['GRAPHRAG_API_KEY'] = self.settings.OPENAI_API_KEY
            os.environ['OPENAI_MODEL'] = self.settings.OPENAI_MODEL
            os.environ['OPENAI_API_BASE'] = self.settings.OPENAI_API_BASE
            os.environ['EMBEDDING_MODEL'] = self.settings.EMBEDDING_MODEL
            logger.info(f"设置环境变量 GRAPHRAG_API_KEY: {self.settings.OPENAI_API_KEY[:10]}...")
            logger.info(f"设置环境变量 OPENAI_MODEL: {self.settings.OPENAI_MODEL}")
            logger.info(f"设置环境变量 OPENAI_API_BASE: {self.settings.OPENAI_API_BASE}")
            logger.info(f"设置环境变量 EMBEDDING_MODEL: {self.settings.EMBEDDING_MODEL}")
            
            # 运行 GraphRag 索引命令
            cmd = [
                "graphrag", "index",
                "--root", self.settings.GRAPHRAG_ROOT_DIR
            ]
            
            # 确保在子进程中也能访问环境变量
            env = os.environ.copy()
            env['GRAPHRAG_API_KEY'] = self.settings.OPENAI_API_KEY
            env['OPENAI_MODEL'] = self.settings.OPENAI_MODEL
            env['OPENAI_API_BASE'] = self.settings.OPENAI_API_BASE
            env['EMBEDDING_MODEL'] = self.settings.EMBEDDING_MODEL
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30分钟超时
                env=env
            )
            
            if result.returncode != 0:
                logger.error(f"GraphRag 索引失败: {result.stderr}")
                raise Exception(f"GraphRag 索引失败: {result.stderr}")
            
            logger.info("GraphRag 索引完成")
            
        except subprocess.TimeoutExpired:
            logger.error("GraphRag 索引超时")
            raise Exception("GraphRag 索引超时")
        except Exception as e:
            logger.error(f"运行 GraphRag 索引失败: {e}")
            raise
    
    async def _get_graph_info(self) -> Dict[str, Any]:
        """获取图结构信息"""
        # 从 GraphRag 输出目录读取图信息
        output_dir = Path(self.settings.GRAPHRAG_OUTPUT_DIR)
        
        # 寻找最新的输出目录
        output_dirs = [d for d in output_dir.iterdir() if d.is_dir()]
        if not output_dirs:
            raise Exception("未找到 GraphRag 输出目录")
        
        latest_dir = max(output_dirs, key=lambda d: d.stat().st_mtime)
        artifacts_dir = latest_dir / "artifacts"
        
        if not artifacts_dir.exists():
            raise Exception("未找到 GraphRag artifacts 目录")
        
        # 读取实体和关系信息
        graph_info = {
            'node_count': 0,
            'relationship_count': 0,
            'entities': [],
            'relationships': [],
            'communities': []
        }
        
        try:
            # 读取实体文件
            entities_file = artifacts_dir / "create_final_entities.parquet"
            if entities_file.exists():
                import pandas as pd
                df = pd.read_parquet(entities_file)
                graph_info['node_count'] = len(df)
                graph_info['entities'] = df.to_dict('records')
            
            # 读取关系文件
            relationships_file = artifacts_dir / "create_final_relationships.parquet"
            if relationships_file.exists():
                import pandas as pd
                df = pd.read_parquet(relationships_file)
                graph_info['relationship_count'] = len(df)
                graph_info['relationships'] = df.to_dict('records')
            
            # 读取社区文件
            communities_file = artifacts_dir / "create_final_communities.parquet"
            if communities_file.exists():
                import pandas as pd
                df = pd.read_parquet(communities_file)
                graph_info['communities'] = df.to_dict('records')
            
        except Exception as e:
            logger.error(f"读取图信息失败: {e}")
        
        return graph_info
    
    async def _sample_graph(self, graph_info: Dict[str, Any]) -> Dict[str, Any]:
        """采样图结构（原始方法，保持向后兼容）"""
        return await self.graph_sampler.sample_connected_subgraph(graph_info, self.settings.SAMPLE_SIZE)
    
    async def _sample_graph_enhanced(self, graph_info: Dict[str, Any], sampling_algorithm: str) -> Dict[str, Any]:
        """使用增强采样器采样复杂拓扑子图"""
        try:
            # 将字符串转换为枚举
            algorithm_map = {
                "mixed": SamplingAlgorithm.MIXED,
                "augmented_chain": SamplingAlgorithm.AUGMENTED_CHAIN,
                "community_core_path": SamplingAlgorithm.COMMUNITY_CORE_PATH,
                "dual_core_bridge": SamplingAlgorithm.DUAL_CORE_BRIDGE,
                "max_chain": SamplingAlgorithm.MAX_CHAIN
            }
            
            algorithm = algorithm_map.get(sampling_algorithm, SamplingAlgorithm.MIXED)
            logger.info(f"使用采样算法: {algorithm.value}")
            
            # 使用增强采样器
            sample_result = await self.enhanced_sampler.sample_complex_subgraph(
                graph_info, 
                self.settings.SAMPLE_SIZE, 
                algorithm
            )
            
            # 分析拓扑复杂度
            topology_analysis = self.enhanced_sampler.analyze_topology(sample_result)
            sample_result['topology_analysis'] = topology_analysis
            
            logger.info(f"增强采样完成: 算法={algorithm.value}, 节点={len(sample_result.get('nodes', []))}, "
                       f"关系={len(sample_result.get('relations', []))}, "
                       f"复杂度={topology_analysis.get('topology_complexity', 'unknown')}")
            
            return sample_result
            
        except Exception as e:
            logger.error(f"增强采样失败，回退到原始采样方法: {e}")
            # 回退到原始采样方法
            return await self._sample_graph(graph_info)
    
    async def _anonymize_sample(self, sample_info: Dict[str, Any]) -> Dict[str, Any]:
        """模糊化采样信息（原始方法，保持向后兼容）"""
        return await self.anonymizer.anonymize_sample(sample_info)
    
    async def _generate_qa_pair(self, anonymized_sample: Dict[str, Any]) -> Dict[str, str]:
        """生成问答对（原始方法，保持向后兼容）"""
        return await self.qa_generator.generate_complex_qa(anonymized_sample)
    
    async def _generate_qa_unified(self, sample_info: Dict[str, Any], use_unified: bool = True, sampling_algorithm: str = "mixed") -> Dict[str, Any]:
        """使用统一QA生成器生成复杂问答对（包含模糊化）"""
        try:
            if use_unified:
                logger.info("使用统一QA生成器（包含模糊化和问题生成）")
                # 获取采样算法信息
                algorithm_used = sample_info.get('algorithm', sampling_algorithm)
                qa_result = await self.unified_qa_generator.generate_qa(
                    sample_info, 
                    sampling_algorithm=algorithm_used
                )
                
                # 添加统一生成的标记
                qa_result['generation_method'] = 'unified_obfuscation_qa'
                qa_result['includes_obfuscation'] = True
                
                logger.info(f"统一QA生成完成: 问题长度={len(qa_result.get('question', ''))}, "
                           f"答案={qa_result.get('answer', 'N/A')[:50]}..., "
                           f"复杂度={qa_result.get('complexity_analysis', {}).get('difficulty_level', 'unknown')}")
                
                return qa_result
            else:
                logger.info("使用原始QA生成流程（先模糊化，后生成问题）")
                # 回退到原始的两步法：先模糊化，后生成QA
                anonymized_sample = await self._anonymize_sample(sample_info)
                qa_result = await self._generate_qa_pair(anonymized_sample)
                
                # 添加原始生成的标记
                qa_result['generation_method'] = 'traditional_two_step'
                qa_result['includes_obfuscation'] = True
                qa_result['anonymized_sample'] = anonymized_sample
                
                return qa_result
                
        except Exception as e:
            logger.error(f"统一QA生成失败，回退到原始方法: {e}")
            # 紧急回退
            try:
                anonymized_sample = await self._anonymize_sample(sample_info)
                qa_result = await self._generate_qa_pair(anonymized_sample)
                qa_result['generation_method'] = 'fallback_traditional'
                qa_result['includes_obfuscation'] = True
                qa_result['fallback_reason'] = str(e)
                return qa_result
            except Exception as fallback_error:
                logger.error(f"回退方法也失败: {fallback_error}")
                return {
                    'question': '基于复杂的知识图谱结构，通过多跳推理识别核心实体的关键属性。',
                    'answer': '无法确定',
                    'generation_method': 'emergency_fallback',
                    'includes_obfuscation': False,
                    'error': str(fallback_error)
                }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats
    
    async def query_graph(self, query: str, method: str = "global") -> str:
        """查询图"""
        logger.info(f"执行 {method} 查询: {query}")
        
        import subprocess
        
        try:
            # 确保环境变量被正确设置
            os.environ['GRAPHRAG_API_KEY'] = self.settings.OPENAI_API_KEY
            os.environ['OPENAI_MODEL'] = self.settings.OPENAI_MODEL
            os.environ['OPENAI_API_BASE'] = self.settings.OPENAI_API_BASE
            os.environ['EMBEDDING_MODEL'] = self.settings.EMBEDDING_MODEL
            
            cmd = [
                "graphrag", "query",
                "--root", self.settings.GRAPHRAG_ROOT_DIR,
                "--method", method,
                query
            ]
            
            # 确保在子进程中也能访问环境变量
            env = os.environ.copy()
            env['GRAPHRAG_API_KEY'] = self.settings.OPENAI_API_KEY
            env['OPENAI_MODEL'] = self.settings.OPENAI_MODEL
            env['OPENAI_API_BASE'] = self.settings.OPENAI_API_BASE
            env['EMBEDDING_MODEL'] = self.settings.EMBEDDING_MODEL
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                env=env
            )
            
            if result.returncode != 0:
                logger.error(f"GraphRag 查询失败: {result.stderr}")
                return f"查询失败: {result.stderr}"
            
            return result.stdout
            
        except Exception as e:
            logger.error(f"执行 GraphRag 查询失败: {e}")
            return f"查询失败: {e}"
    
    def cleanup(self):
        """清理资源"""
        # 如果需要清理临时文件等
        pass

    def _is_high_quality_relationship(self, relation_type: str) -> bool:
        """判断关系是否为高质量关系"""
        # 禁止的低质量关系词汇
        low_quality_relations = {
            '关联', '相关', '有关', '关系', '连接', '联系', '关连',
            '相关联', '相关性', '关联性', '联结', '相接', '相连',
            'related', 'connected', 'associated', 'linked', 'relation'
        }

        # 去除空格并转换为小写进行比较
        normalized_relation = relation_type.strip().lower()

        # 检查是否为禁止的关系类型
        if normalized_relation in low_quality_relations:
            return False

        # 检查是否包含禁止词汇
        for forbidden in low_quality_relations:
            if forbidden in normalized_relation:
                return False

        # 关系不能为空或过短
        if len(relation_type.strip()) < 2:
            return False

        return True

    def _is_entity_related_to_expansion_node(self, entity_name: str, current_entity: str, relationships: List[Dict]) -> bool:
        """判断实体是否与当前expansion节点有关联"""
        if entity_name == current_entity:
            return True

        # 检查是否在任何关系中与current_entity直接相关
        for rel in relationships:
            source = rel.get('source', '')
            target = rel.get('target', '')

            if (source == current_entity and target == entity_name) or \
               (target == current_entity and source == entity_name):
                return True

        # 检查是否与已有的expansion节点相关
        if hasattr(self, 'expansion_nodes'):
            for expansion_node in self.expansion_nodes:
                for rel in relationships:
                    source = rel.get('source', '')
                    target = rel.get('target', '')

                    if (source == expansion_node and target == entity_name) or \
                       (target == expansion_node and source == entity_name):
                        return True

        # 检查是否在已有的图实体中
        if hasattr(self, 'graph_entities'):
            for existing_entity in self.graph_entities.values():
                existing_name = existing_entity.get('name', '')
                if existing_name == entity_name:
                    return True

        return False

    async def _prefilter_text_with_llm(self, text: str, current_entity: str = None) -> str:
        """使用LLM预筛选文本，支持分块并行处理"""
        logger.info(f"开始文本预筛选 - 原始文本长度: {len(text)}")
        
        # 配置参数
        chunk_size = 70000  # 每个分块的字符数
        overlap_size = 10000  # 重叠字符数
        min_total_size = 70000  # 不拆分的最小总长度
        
        # 判断是否需要分块
        if len(text) < min_total_size:
            logger.info(f"文本长度({len(text)})小于{min_total_size}，不进行分块处理")
            return await self._prefilter_single_chunk(text, current_entity)
        
        # 创建分块
        chunks = self._create_text_chunks(text, chunk_size, overlap_size)
        logger.info(f"文本分为{len(chunks)}个分块进行并行处理")
        
        # 并行处理所有分块
        try:
            chunk_results = await asyncio.gather(
                *[self._prefilter_single_chunk(chunk, current_entity, chunk_index=i+1) 
                  for i, chunk in enumerate(chunks)],
                return_exceptions=True
            )
            
            # 收集所有有效的筛选结果
            all_sentences = []
            for i, result in enumerate(chunk_results):
                if isinstance(result, Exception):
                    logger.error(f"分块{i+1}处理失败: {result}")
                    continue
                    
                if result and result != chunks[i]:  # 如果有筛选结果且不是原始文本
                    sentences = [s.strip() for s in result.split('\n') if s.strip()]
                    all_sentences.extend(sentences)
            
            if not all_sentences:
                logger.warning("所有分块筛选失败，使用原始文本")
                return text
            
            final_result = '\n'.join(all_sentences)
            
            logger.info(f"并行分块预筛选完成:")
            logger.info(f"  - 原始文本长度: {len(text)} 字符") 
            logger.info(f"  - 分块数量: {len(chunks)}")
            logger.info(f"  - 筛选后文本长度: {len(final_result)} 字符")
            logger.info(f"  - 最终筛选出句子数量: {len(all_sentences)}")
            
            return final_result if final_result else text
            
        except Exception as e:
            logger.error(f"并行文本预筛选失败: {e}")
            return text
    
    def _create_text_chunks(self, text: str, chunk_size: int, overlap_size: int) -> List[str]:
        """创建带重叠的文本分块"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # 如果不是最后一个分块，尝试在句号、换行符或空格处分割
            if end < len(text):
                # 在最后500个字符中寻找合适的分割点
                search_start = max(end - 500, start)
                best_split = end
                
                for i in range(end - 1, search_start - 1, -1):
                    if text[i] in ['。', '！', '？', '\n', '；']:
                        best_split = i + 1
                        break
                    elif text[i] == ' ' and best_split == end:
                        best_split = i
                
                end = best_split
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # 计算下一个分块的起始位置（考虑重叠）
            if end >= len(text):
                break
                
            start = end - overlap_size
            if start < 0:
                start = 0
        
        return chunks
    
    async def _prefilter_single_chunk(self, text: str, current_entity: str = None, chunk_index: int = None) -> str:
        """处理单个文本分块的预筛选"""
        chunk_info = f" (分块{chunk_index})" if chunk_index else ""
        logger.info(f"开始处理文本分块{chunk_info} - 长度: {len(text)}")
        
        entity_context = f"当前核心实体: {current_entity}" if current_entity else "无特定核心实体"
        
        prompt = f"""
        请从以下与{current_entity}有关的文本中筛选出最多5句话，这些句子应当包含明确客观信息，适合构建知识图谱。

        {entity_context}

        **筛选要求**：
        1. **包含具体信息**：优先选择包含时间、地点、人物关系、具体数据的句子
        2. **实体明确**：句子中的实体必须是具体名称，避免"他"、"它"、"该公司"等模糊指代词
        3. **关系清晰**：能明确表达"实体A-关系-实体B"的结构
        4. **与当前实体相关**：句子必须与"{current_entity}"有明确关联
        5. **信息量高**：避免选择过于简单或常见的句子

        **避免选择**：
        - 包含模糊指代词的句子
        - 过于抽象或概念化的句子
        - 仅包含主观评价的句子
        - 与当前实体关联度低的句子

        原始文本：
        {text}

        请直接返回筛选出的5句话，每句话占一行，不要添加编号或其他格式标记。如果文本中少于5句话，则返回所有可用的句子。
        """
        
        try:
            response = await self.llm_client.generate_response(prompt)
            
            if not response:
                logger.warning(f"文本分块{chunk_info}预筛选失败，使用原始文本")
                return text
            
            # 清理响应并分割成句子
            filtered_sentences = []
            lines = response.strip().split('\n')
            
            for line in lines:
                sentence = line.strip()
                # 移除可能的编号
                if sentence and not sentence.startswith(('```', '#', '*', '-')):
                    # 移除序号前缀 (如 "1. ", "2. ", "一、", "二、")
                    sentence = re.sub(r'^\d+[\.、]\s*', '', sentence)
                    sentence = re.sub(r'^[一二三四五六七八九十][、．]\s*', '', sentence)
                    
                    if sentence and len(sentence) > 10:  # 过滤过短的句子
                        filtered_sentences.append(sentence)
            
            # 限制最多5句
            filtered_sentences = filtered_sentences[:5]
            filtered_text = '\n'.join(filtered_sentences)
            
            logger.info(f"文本分块{chunk_info}预筛选完成 - 筛选出{len(filtered_sentences)}句")
            
            # 如果筛选结果太短，使用原始文本
            if len(filtered_text) < 50:
                logger.warning(f"分块{chunk_info}筛选结果过短，使用原始文本")
                return text
                
            return filtered_text
            
        except Exception as e:
            logger.error(f"文本分块{chunk_info}预筛选失败: {e}")
            return text

    def _recursively_filter_relationships_by_entities(
        self,
        relationships: List[Dict[str, Any]],
        max_relations: int = 10
    ) -> List[Dict[str, Any]]:
        """
        递归筛选与现有图实体相关的relationship

        Args:
            relationships: 待筛选的关系列表
            max_relations: 最大关系数量限制

        Returns:
            筛选后的关系列表
        """
        logger.info(f"开始递归筛选关系 - 输入关系数: {len(relationships)}, 现有实体数: {len(self.entity_name_to_entities)}, 最大关系数: {max_relations}")

        # 使用entity_name_to_entities的key作为现有实体名称集合
        existing_entity_names = set(self.entity_name_to_entities.keys())

        logger.info(f"现有实体名称: {list(existing_entity_names)}")

        # 初始化结果列表和已处理的关系集合（避免死循环）
        filtered_graph_relations = []
        processed_relations = set()  # 用于避免重复处理
        iteration_count = 0
        max_iterations = 100  # 防止无限循环的安全限制

        # 第一轮：筛选直接与现有实体相关的关系
        current_relationships = relationships.copy()

        while (len(filtered_graph_relations) < max_relations and
               current_relationships and
               iteration_count < max_iterations):

            iteration_count += 1
            logger.info(f"=== 递归筛选第 {iteration_count} 轮 ===")
            logger.info(f"当前筛选结果: {len(filtered_graph_relations)} 个关系")
            logger.info(f"待处理关系: {len(current_relationships)} 个")

            # 本轮新添加的关系
            new_relations_this_round = []
            remaining_relationships = []

            for rel in current_relationships:
                # 避免重复处理
                rel_key = (rel.get('source', ''), rel.get('relation', ''), rel.get('target', ''))
                if rel_key in processed_relations:
                    continue

                processed_relations.add(rel_key)

                source_name = rel.get('source', '')
                target_name = rel.get('target', '')

                # 检查关系是否与现有实体相关
                source_in_graph = source_name in existing_entity_names
                target_in_graph = target_name in existing_entity_names

                if source_in_graph or target_in_graph or not self.entity_name_to_entities:
                    # 添加到筛选结果
                    new_relations_this_round.append(rel)
                    logger.info(f"保留关系: {source_name} --[{rel.get('relation', '')}]--> {target_name} "
                              f"(source_in_graph: {source_in_graph}, target_in_graph: {target_in_graph})")

                    # 将关系中的新实体添加到现有实体集合中
                    if not source_in_graph and source_name:
                        existing_entity_names.add(source_name)
                        # 创建新实体信息并添加到映射中
                        new_entity_info = {
                            'id': f"temp_{source_name}_{len(existing_entity_names)}",
                            'name': source_name,
                            'type': 'concept',
                            'description': f'从关系抽取的新实体: {source_name}'
                        }
                        self.entity_name_to_entities[source_name] = new_entity_info
                        logger.info(f"添加新实体到图: {source_name}")
                    if not target_in_graph and target_name:
                        existing_entity_names.add(target_name)
                        # 创建新实体信息并添加到映射中
                        new_entity_info = {
                            'id': f"temp_{target_name}_{len(existing_entity_names)}",
                            'name': target_name,
                            'type': 'concept',
                            'description': f'从关系抽取的新实体: {target_name}'
                        }
                        self.entity_name_to_entities[target_name] = new_entity_info
                        logger.info(f"添加新实体到图: {target_name}")
                else:
                    # 保留到下一轮处理
                    remaining_relationships.append(rel)
                    logger.info(f"保留到下一轮: {source_name} --[{rel.get('relation', '')}]--> {target_name}")

            # 将本轮新关系添加到结果中
            filtered_graph_relations.extend(new_relations_this_round)
            logger.info(f"第 {iteration_count} 轮添加了 {len(new_relations_this_round)} 个关系")

            # 检查终止条件
            if not new_relations_this_round:
                logger.info(f"第 {iteration_count} 轮没有添加任何关系，停止递归")
                break

            if len(filtered_graph_relations) >= max_relations:
                logger.info(f"已达到最大关系数限制 ({max_relations})，停止递归")
                break

            # 更新待处理关系列表
            current_relationships = remaining_relationships

            # 如果没有剩余关系，停止递归
            if not current_relationships:
                logger.info("没有剩余关系需要处理，停止递归")
                break

        # 限制最终结果数量
        final_result = filtered_graph_relations[:max_relations]

        logger.info(f"递归筛选完成:")
        logger.info(f"  - 总迭代轮数: {iteration_count}")
        logger.info(f"  - 筛选前关系数: {len(relationships)}")
        logger.info(f"  - 筛选后关系数: {len(final_result)}")
        logger.info(f"  - 最终实体数: {len(existing_entity_names)}")

        # 打印最终筛选结果
        logger.info("最终筛选的关系:")
        for i, rel in enumerate(final_result, 1):
            source_name = rel.get('source', 'N/A')
            target_name = rel.get('target', 'N/A')
            relation_type = rel.get('relation', 'N/A')
            logger.info(f"  {i}. {source_name} --[{relation_type}]--> {target_name}")

        return final_result