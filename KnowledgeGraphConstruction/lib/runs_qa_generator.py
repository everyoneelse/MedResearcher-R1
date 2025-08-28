#!/usr/bin/env python3
"""
基于Runs记录的QA生成器
读取runs下的图记录，直接拿来取子图生成问题
"""

import os
import json
import logging
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from .graph_sampler import GraphSampler
from .enhanced_graph_sampler import EnhancedGraphSampler, SamplingAlgorithm
from .unified_qa_generator import UnifiedQAGenerator
from .qa_generator import QAGenerator

logger = logging.getLogger(__name__)

class RunsQAGenerator:
    """基于Runs记录的QA生成器"""
    
    def __init__(self, runs_base_dir: str = "runs"):
        """初始化生成器
        
        Args:
            runs_base_dir: runs目录的基础路径
        """
        self.runs_base_dir = Path(runs_base_dir)
        self.graph_sampler = GraphSampler()
        self.enhanced_sampler = EnhancedGraphSampler()
        self.unified_qa_generator = UnifiedQAGenerator()
        self.qa_generator = QAGenerator()
        
    def list_available_runs(self) -> List[Dict[str, Any]]:
        """列出所有可用的运行记录
        
        Returns:
            运行记录列表，包含基本信息
        """
        runs = []
        
        if not self.runs_base_dir.exists():
            logger.warning(f"Runs目录不存在: {self.runs_base_dir}")
            return runs
        
        for run_dir in self.runs_base_dir.iterdir():
            if run_dir.is_dir():
                run_info = self._get_run_info(run_dir)
                if run_info:
                    runs.append(run_info)
        
        # 按时间排序（最新的在前）
        runs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return runs
    
    def _get_run_info(self, run_dir: Path) -> Optional[Dict[str, Any]]:
        """获取运行记录的基本信息
        
        Args:
            run_dir: 运行目录路径
            
        Returns:
            运行记录信息字典
        """
        try:
            run_info = {
                'run_id': run_dir.name,
                'path': str(run_dir),
                'timestamp': run_dir.name.split('_')[0] + '_' + run_dir.name.split('_')[1] if '_' in run_dir.name else run_dir.name
            }
            
            # 检查是否有graphrag_data
            graphrag_data_dir = run_dir / "graphrag_data"
            if graphrag_data_dir.exists():
                input_dir = graphrag_data_dir / "input"
                if input_dir.exists():
                    # 统计输入文件数量
                    input_files = list(input_dir.glob("*.txt"))
                    run_info['input_files_count'] = len(input_files)
                    run_info['has_graph_data'] = True
                    
                    # 提取实体列表（从文件名）
                    entities = []
                    for file_path in input_files:
                        entity_name = file_path.stem.split('_')[0]  # 提取实体名
                        if entity_name not in entities:
                            entities.append(entity_name)
                    run_info['entities'] = entities  # 显示所有实体
                    run_info['total_entities'] = len(entities)
                else:
                    run_info['has_graph_data'] = False
            else:
                run_info['has_graph_data'] = False
                
            return run_info
            
        except Exception as e:
            logger.error(f"获取运行信息失败 {run_dir}: {e}")
            return None
    
    async def extract_graph_from_run(self, run_id: str) -> Dict[str, Any]:
        """从运行记录中提取图数据
        
        Args:
            run_id: 运行ID
            
        Returns:
            图数据字典，包含entities和relationships
        """
        run_dir = self.runs_base_dir / run_id
        if not run_dir.exists():
            raise ValueError(f"运行记录不存在: {run_id}")
        
        # 检查是否有extraction文件（包含已抽取的图数据）
        graphrag_input_dir = run_dir / "graphrag_data" / "input"
        if not graphrag_input_dir.exists():
            raise ValueError(f"运行记录中没有找到图数据: {run_id}")
        
        # 查找extraction文件
        extraction_files = list(graphrag_input_dir.glob("*_extraction.json"))
        
        if extraction_files:
            # 有extraction文件，直接从中读取图数据
            logger.info(f"从{len(extraction_files)}个extraction文件中读取图数据")
            return await self._load_graph_from_extractions(extraction_files)
        else:
            # 没有extraction文件，尝试从文本文件重建图数据
            logger.info("没有找到extraction文件，尝试从文本文件重建图数据")
            return await self._reconstruct_graph_from_texts(graphrag_input_dir)
    
    async def _load_graph_from_extractions(self, extraction_files: List[Path]) -> Dict[str, Any]:
        """从extraction文件中加载图数据
        
        Args:
            extraction_files: extraction文件路径列表
            
        Returns:
            图数据字典
        """
        all_entities = {}  # entity_id -> entity_info
        all_relationships = []
        
        for file_path in extraction_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    extraction_data = json.load(f)
                
                # 处理实体
                extracted_entities = extraction_data.get('extracted_entities', [])
                for entity_data in extracted_entities:
                    if isinstance(entity_data, dict):
                        entity_name = entity_data.get('name', '')
                        entity_type = entity_data.get('type', 'concept')
                        entity_desc = entity_data.get('description', '')
                        entity_id = entity_data.get('id', '')
                        
                        if not entity_id:
                            entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)
                        
                        # 合并实体信息
                        if entity_id not in all_entities:
                            all_entities[entity_id] = {
                                'id': entity_id,
                                'name': entity_name,
                                'type': entity_type,
                                'description': entity_desc
                            }
                        else:
                            # 更新实体信息（保留更详细的）
                            existing = all_entities[entity_id]
                            if len(entity_desc) > len(existing.get('description', '')):
                                existing['description'] = entity_desc
                            if len(entity_name) > len(existing.get('name', '')):
                                existing['name'] = entity_name
                    
                    elif isinstance(entity_data, str):
                        entity_name = entity_data
                        entity_type = 'concept'
                        entity_desc = f'抽取的实体：{entity_name}'
                        entity_id = self._generate_entity_id(entity_name, entity_type, entity_desc)
                        
                        if entity_id not in all_entities:
                            all_entities[entity_id] = {
                                'id': entity_id,
                                'name': entity_name,
                                'type': entity_type,
                                'description': entity_desc
                            }
                
                # 处理关系
                extracted_relationships = extraction_data.get('extracted_relationships', [])
                all_relationships.extend(extracted_relationships)
                
            except Exception as e:
                logger.error(f"读取extraction文件失败 {file_path}: {e}")
                continue
        
        # 转换为列表格式
        entities_list = list(all_entities.values())
        
        # 验证关系中的实体ID
        valid_relationships = []
        entity_names = {entity['name'] for entity in entities_list}
        
        for rel in all_relationships:
            source = rel.get('source', '')
            target = rel.get('target', '')
            
            # 检查关系的实体是否存在
            if source in entity_names and target in entity_names:
                valid_relationships.append(rel)
        
        logger.info(f"加载图数据: {len(entities_list)}个实体, {len(valid_relationships)}个关系")
        
        return {
            'entities': entities_list,
            'relationships': valid_relationships,
            'node_count': len(entities_list),
            'relationship_count': len(valid_relationships),
            'source': 'extraction_files'
        }
    
    async def _reconstruct_graph_from_texts(self, input_dir: Path) -> Dict[str, Any]:
        """从文本文件重建图数据（简化版本）
        
        Args:
            input_dir: 输入目录路径
            
        Returns:
            图数据字典
        """
        # 这是一个简化的重建方法，主要基于文件名提取实体
        entities = []
        relationships = []
        
        text_files = list(input_dir.glob("*.txt"))
        
        # 从文件名提取实体
        entity_names = set()
        for file_path in text_files:
            # 文件名格式通常是: entity_timestamp.txt
            parts = file_path.stem.split('_')
            if len(parts) >= 2:
                entity_name = parts[0]
                entity_names.add(entity_name)
        
        # 构建实体列表
        for i, entity_name in enumerate(entity_names):
            entities.append({
                'id': f'entity_{i+1}',
                'name': entity_name,
                'type': 'concept',
                'description': f'从运行记录重建的实体：{entity_name}'
            })
        
        # 简单的关系推断（基于共现）
        # 这里可以根据需要实现更复杂的关系推断逻辑
        entity_list = list(entity_names)
        for i in range(len(entity_list)):
            for j in range(i+1, min(i+3, len(entity_list))):  # 限制关系数量
                relationships.append({
                    'source': entity_list[i],
                    'target': entity_list[j],
                    'relation': 'related_to',
                    'description': '基于共现推断的关系'
                })
        
        logger.info(f"重建图数据: {len(entities)}个实体, {len(relationships)}个关系")
        
        return {
            'entities': entities,
            'relationships': relationships,
            'node_count': len(entities),
            'relationship_count': len(relationships),
            'source': 'reconstructed'
        }
    
    def _generate_entity_id(self, name: str, entity_type: str, description: str) -> str:
        """生成实体ID"""
        import hashlib
        content = f"{name}_{entity_type}_{description}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
    
    async def generate_qa_from_run(
        self, 
        run_id: str, 
        sample_size: int = 10,
        sampling_algorithm: str = "mixed",
        use_unified_qa: bool = True,
        num_questions: int = 1
    ) -> List[Dict[str, Any]]:
        """从运行记录生成问答对
        
        Args:
            run_id: 运行ID
            sample_size: 子图采样大小
            sampling_algorithm: 采样算法 ("mixed", "augmented_chain", "community_core_path", "dual_core_bridge", "max_chain", "connected_subgraph")
            use_unified_qa: 是否使用统一QA生成器
            num_questions: 生成问题数量
            
        Returns:
            问答对列表
        """
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            # 使用已有的trace
            logger.info(f"继承parent trace: {parent_trace}")
        else:
            # 创建新的trace
            start_trace(prefix="runs_qa")
            logger.info(f"创建新的runs_qa trace")
        
        try:
            # 提取图数据
            logger.info(f"从运行记录 {run_id} 提取图数据")
            graph_data = await self.extract_graph_from_run(run_id)
            
            if not graph_data.get('entities') or not graph_data.get('relationships'):
                raise ValueError(f"运行记录 {run_id} 中没有有效的图数据")
            
            qa_results = []
            
            for i in range(num_questions):
                logger.info(f"生成第 {i+1}/{num_questions} 个问答对")
                
                # 采样子图
                if sampling_algorithm == "connected_subgraph":
                    # 使用基础采样器
                    subgraph = await self.graph_sampler.sample_connected_subgraph(graph_data, sample_size)
                else:
                    # 使用增强采样器
                    algorithm_map = {
                        "mixed": SamplingAlgorithm.MIXED,
                        "augmented_chain": SamplingAlgorithm.AUGMENTED_CHAIN,
                        "community_core_path": SamplingAlgorithm.COMMUNITY_CORE_PATH,
                        "dual_core_bridge": SamplingAlgorithm.DUAL_CORE_BRIDGE,
                        "max_chain": SamplingAlgorithm.MAX_CHAIN
                    }
                    
                    algorithm = algorithm_map.get(sampling_algorithm, SamplingAlgorithm.MIXED)
                    subgraph = await self.enhanced_sampler.sample_complex_subgraph(graph_data, sample_size, algorithm)
                
                if not subgraph.get('nodes') or not subgraph.get('relations'):
                    logger.warning(f"第 {i+1} 次采样失败，跳过")
                    continue
                
                # 生成问答对
                if use_unified_qa:
                    # 构建采样信息，统一QA生成器需要这种格式
                    sample_info = {
                        'nodes': subgraph['nodes'],
                        'relations': subgraph['relations']
                    }
                    qa_result = await self.unified_qa_generator.generate_qa(
                        sample_info=sample_info,
                        sampling_algorithm=subgraph.get('algorithm', sampling_algorithm)
                    )
                else:
                    # 基础QA生成器需要匿名化的样本
                    # 这里为了简化，直接构建一个包含节点和关系的样本
                    anonymized_sample = {
                        'nodes': subgraph['nodes'],
                        'relations': subgraph['relations'],
                        'sampling_method': subgraph.get('algorithm', sampling_algorithm)
                    }
                    qa_result = await self.qa_generator.generate_complex_qa(anonymized_sample)
                
                if qa_result:
                    # 添加元信息
                    qa_result.update({
                        'source_run_id': run_id,
                        'sampling_algorithm': subgraph.get('algorithm', sampling_algorithm),
                        'subgraph_size': len(subgraph['nodes']),
                        'subgraph_relations': len(subgraph['relations']),
                        'generated_at': datetime.now().isoformat(),
                        'question_index': i + 1
                    })
                    qa_results.append(qa_result)
                    logger.info(f"成功生成第 {i+1} 个问答对")
                else:
                    logger.warning(f"第 {i+1} 次问答生成失败")
            
            logger.info(f"从运行记录 {run_id} 成功生成 {len(qa_results)} 个问答对")
            return qa_results
            
        except Exception as e:
            logger.error(f"从运行记录生成问答失败: {e}")
            raise
    
    async def batch_generate_from_multiple_runs(
        self,
        run_ids: List[str],
        sample_size: int = 10,
        sampling_algorithm: str = "mixed",
        questions_per_run: int = 1
    ) -> Dict[str, List[Dict[str, Any]]]:
        """从多个运行记录批量生成问答对
        
        Args:
            run_ids: 运行ID列表
            sample_size: 子图采样大小
            sampling_algorithm: 采样算法
            questions_per_run: 每个运行记录生成的问题数量
            
        Returns:
            按运行ID组织的问答对字典
        """
        results = {}
        
        for run_id in run_ids:
            try:
                logger.info(f"处理运行记录: {run_id}")
                qa_results = await self.generate_qa_from_run(
                    run_id=run_id,
                    sample_size=sample_size,
                    sampling_algorithm=sampling_algorithm,
                    num_questions=questions_per_run
                )
                results[run_id] = qa_results
                logger.info(f"运行记录 {run_id} 生成 {len(qa_results)} 个问答对")
                
            except Exception as e:
                logger.error(f"处理运行记录 {run_id} 失败: {e}")
                results[run_id] = []
        
        return results
    
    async def batch_generate_from_multiple_runs_with_qps_limit(
        self,
        run_ids: List[str],
        sample_size: int = 10,
        sampling_algorithm: str = "mixed",
        questions_per_run: int = 1,
        use_unified_qa: bool = True,
        qps_limit: float = 2.0,
        parallel_workers: int = 1,
        progress_callback=None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """从多个运行记录批量生成问答对（支持QPS限制和并发控制）
        
        Args:
            run_ids: 运行ID列表
            sample_size: 子图采样大小
            sampling_algorithm: 采样算法
            questions_per_run: 每个运行记录生成的问题数量
            use_unified_qa: 是否使用统一QA生成器
            qps_limit: QPS限制（每秒最大请求数，0表示无限制）
            parallel_workers: 并发工作线程数
            progress_callback: 进度回调函数
            
        Returns:
            按运行ID组织的问答对字典
        """
        import time
        from asyncio import Semaphore, Queue, gather, create_task
        
        results = {}
        total_runs = len(run_ids)
        completed_runs = 0
        
        # 创建信号量控制并发数
        semaphore = Semaphore(parallel_workers)
        
        # 创建速率限制器
        rate_limiter = AsyncRateLimiter(qps_limit) if qps_limit > 0 else None
        
        async def process_single_run(run_id: str) -> Tuple[str, List[Dict[str, Any]]]:
            """处理单个运行记录"""
            nonlocal completed_runs
            
            async with semaphore:
                try:
                    # 应用速率限制
                    if rate_limiter:
                        await rate_limiter.acquire()
                    
                    logger.info(f"处理运行记录: {run_id}")
                    
                    if progress_callback:
                        progress_callback(f"正在处理: {run_id}", int((completed_runs / total_runs) * 100))
                    
                    qa_results = await self.generate_qa_from_run(
                        run_id=run_id,
                        sample_size=sample_size,
                        sampling_algorithm=sampling_algorithm,
                        num_questions=questions_per_run,
                        use_unified_qa=use_unified_qa
                    )
                    
                    completed_runs += 1
                    
                    if progress_callback:
                        progress_callback(
                            f"完成处理: {run_id} (生成{len(qa_results)}个QA对)", 
                            int((completed_runs / total_runs) * 100)
                        )
                    
                    logger.info(f"运行记录 {run_id} 生成 {len(qa_results)} 个问答对")
                    return run_id, qa_results
                    
                except Exception as e:
                    completed_runs += 1
                    logger.error(f"处理运行记录 {run_id} 失败: {e}")
                    
                    if progress_callback:
                        progress_callback(f"处理失败: {run_id} - {str(e)}", int((completed_runs / total_runs) * 100))
                    
                    return run_id, []
        
        # 启动所有任务
        logger.info(f"开始批量处理 {total_runs} 个运行记录，QPS限制: {qps_limit}, 并发数: {parallel_workers}")
        
        tasks = [create_task(process_single_run(run_id)) for run_id in run_ids]
        
        # 等待所有任务完成
        task_results = await gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for result in task_results:
            if isinstance(result, Exception):
                logger.error(f"任务执行异常: {result}")
                continue
            
            run_id, qa_results = result
            results[run_id] = qa_results
        
        logger.info(f"批量处理完成，共处理 {len(results)} 个运行记录")
        
        if progress_callback:
            progress_callback("批量处理完成", 100)
        
        return results
    
    def save_qa_results(self, qa_results: List[Dict[str, Any]], output_file: str):
        """保存问答结果到文件
        
        Args:
            qa_results: 问答结果列表
            output_file: 输出文件路径
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存为JSONL格式
        with open(output_path, 'w', encoding='utf-8') as f:
            for qa in qa_results:
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')
        
        logger.info(f"保存 {len(qa_results)} 个问答对到: {output_path}")


class AsyncRateLimiter:
    """异步速率限制器"""
    
    def __init__(self, qps: float):
        """初始化速率限制器
        
        Args:
            qps: 每秒允许的请求数
        """
        self.qps = qps
        self.interval = 1.0 / qps if qps > 0 else 0
        self.last_called = 0
        self._lock = asyncio.Lock()
        
    async def acquire(self):
        """获取许可，如果需要会等待"""
        if self.qps <= 0:
            return
            
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_called
            
            if time_passed < self.interval:
                wait_time = self.interval - time_passed
                logger.debug(f"速率限制：等待 {wait_time:.3f} 秒")
                await asyncio.sleep(wait_time)
            
            self.last_called = time.time() 