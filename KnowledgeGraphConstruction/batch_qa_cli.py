#!/usr/bin/env python3
"""
命令行批量QA生成脚本

该脚本允许用户从命令行选择种子文件并进行批量QA生成，支持：
- 选择种子文件（CSV格式）
- 自定义输出路径
- 配置生成参数
- 进度显示
- 断点续传

使用示例：
    python batch_qa_cli.py                                    # 交互式选择种子文件
    python batch_qa_cli.py --seed-file medical_entities.csv   # 指定种子文件
    python batch_qa_cli.py --list-seeds                       # 列出可用的种子文件
    python batch_qa_cli.py --seed-file test.csv --output custom_output.jsonl --max-nodes 300
    python batch_qa_cli.py --seed-file entities.csv --disable-instant-save  # 禁用即时保存
    python batch_qa_cli.py --seed-file entities.csv --force-overwrite       # 强制覆盖重新开始
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# 项目导入
from config import setup_global_logging
from lib.run_manager import RunManager
from lib.trace_manager import start_trace

# 配置日志
log_filename = setup_global_logging()
logger = logging.getLogger(__name__)

class AsyncRateLimiter:
    """异步速率限制器"""
    
    def __init__(self, qps: float):
        self.qps = qps
        self.interval = 1.0 / qps if qps > 0 else 0
        self.last_request = 0.0
        self.lock = asyncio.Lock()
    
    async def acquire(self):
        """获取访问权限，确保不超过QPS限制"""
        if self.qps <= 0:
            return
            
        async with self.lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self.last_request
            
            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                await asyncio.sleep(sleep_time)
            
            self.last_request = asyncio.get_event_loop().time()

class BatchQACLI:
    """命令行批量QA生成器"""
    
    def __init__(self):
        self.seed_files_dir = "evaluation_data/entity_sets"
        self.default_output_dir = "qa_output"
        
        # 确保目录存在
        os.makedirs(self.seed_files_dir, exist_ok=True)
        os.makedirs(self.default_output_dir, exist_ok=True)
    
    def list_available_seed_files(self) -> List[str]:
        """列出可用的种子文件"""
        seed_files = []
        if os.path.exists(self.seed_files_dir):
            for file in os.listdir(self.seed_files_dir):
                if file.endswith('.csv'):
                    seed_files.append(file)
        return sorted(seed_files)
    
    def load_entities_from_csv(self, csv_file: str) -> List[str]:
        """从CSV文件加载实体列表"""
        csv_path = os.path.join(self.seed_files_dir, csv_file)
        
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"种子文件不存在: {csv_path}")
        
        entities = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 支持多种列名
                    entity = row.get('entity') or row.get('name') or row.get('实体') or row.get('名称')
                    if entity and entity.strip():
                        entities.append(entity.strip())
        except Exception as e:
            logger.error(f"读取CSV文件失败: {e}")
            raise
        
        if not entities:
            raise ValueError("CSV文件中没有有效的实体数据")
        
        return entities
    
    def interactive_select_seed_file(self) -> str:
        """交互式选择种子文件"""
        seed_files = self.list_available_seed_files()
        
        if not seed_files:
            print("❌ 没有找到种子文件！")
            print(f"请将CSV格式的种子文件放在 {self.seed_files_dir} 目录下")
            print("CSV文件应包含 'entity' 或 'name' 列")
            sys.exit(1)
        
        print("\n📂 可用的种子文件:")
        print("=" * 50)
        for i, file in enumerate(seed_files, 1):
            # 尝试读取文件信息
            try:
                entities = self.load_entities_from_csv(file)
                print(f"{i:2d}. {file} ({len(entities)} 个实体)")
            except Exception as e:
                print(f"{i:2d}. {file} (读取失败: {e})")
        
        print("=" * 50)
        
        while True:
            try:
                choice = input("\n请选择种子文件编号 (1-{}): ".format(len(seed_files)))
                choice_num = int(choice)
                if 1 <= choice_num <= len(seed_files):
                    return seed_files[choice_num - 1]
                else:
                    print("❌ 无效的选择，请输入正确的编号")
            except ValueError:
                print("❌ 请输入数字")
            except KeyboardInterrupt:
                print("\n用户取消操作")
                sys.exit(0)
    
    def generate_default_output_path(self, seed_file: str, entities_count: int) -> str:
        """生成默认输出路径"""
        # 移除文件扩展名
        base_name = os.path.splitext(seed_file)[0]
        # 添加时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base_name}_{entities_count}entities_{timestamp}.jsonl"
        return os.path.join(self.default_output_dir, filename)
    
    def load_existing_results(self, output_path: str) -> Dict[str, Any]:
        """加载已存在的结果文件，用于断点续传"""
        if not os.path.exists(output_path):
            return {}
        
        existing_results = {}
        completed_entities = set()
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        qa_data = json.loads(line)
                        source_entity = qa_data.get('source_entity', '')
                        if source_entity:
                            existing_results[source_entity] = qa_data
                            completed_entities.add(source_entity)
                    except json.JSONDecodeError as e:
                        logger.warning(f"跳过无效JSON行 {line_num}: {e}")
                        continue
            
            logger.info(f"加载已存在结果: {len(existing_results)} 个QA对")
            logger.info(f"已完成实体: {sorted(list(completed_entities))}")
            return existing_results
            
        except Exception as e:
            logger.error(f"加载已存在结果失败: {e}")
            return {}
    
    def save_single_qa(self, qa_result: Dict[str, Any], output_path: str):
        """即时保存单个QA结果"""
        try:
            # 确保输出目录存在
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 添加完成时间戳和顺序信息
            qa_result['completed_at'] = datetime.now().isoformat()
            qa_result['save_order'] = datetime.now().timestamp()  # 用于排序
            
            # 追加写入JSONL文件
            with open(output_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(qa_result, ensure_ascii=False) + '\n')
                f.flush()  # 强制写入磁盘
            
            logger.debug(f"即时保存QA结果: {qa_result.get('source_entity', 'unknown')}")
            
        except Exception as e:
            logger.error(f"即时保存失败: {e}")
    
    def get_processing_status(self, entities: List[str], output_path: str) -> Dict[str, Any]:
        """获取详细的处理状态信息"""
        existing_results = self.load_existing_results(output_path)
        
        completed_entities = set(existing_results.keys())
        remaining_entities = [entity for entity in entities if entity not in completed_entities]
        
        # 按原始顺序分析完成情况
        completion_map = {}
        for i, entity in enumerate(entities, 1):
            completion_map[entity] = {
                'index': i,
                'completed': entity in completed_entities,
                'status': '✅' if entity in completed_entities else '⏳'
            }
        
        return {
            'total_entities': len(entities),
            'completed_count': len(completed_entities),
            'remaining_count': len(remaining_entities),
            'completion_rate': len(completed_entities) / len(entities) if entities else 0,
            'completed_entities': sorted(list(completed_entities)),
            'remaining_entities': remaining_entities,
            'completion_map': completion_map
        }
    
    async def batch_generate_qa(
        self, 
        entities: List[str],
        output_path: str,
        sampling_algorithm: str = "max_chain",
        use_unified_qa: bool = True,
        max_nodes: int = 200,
        max_iterations: int = 10,
        parallel_workers: int = 20,
        qps_limit: float = 20,
        enable_resume: bool = True,
        enable_instant_save: bool = True
    ) -> Dict[str, Any]:
        """批量生成QA - 支持真正的并行处理"""
        start_trace(prefix="batch_cli")
        
        logger.info(f"开始批量生成QA: {len(entities)} 个实体")
        logger.info(f"输出路径: {output_path}")
        logger.info(f"采样算法: {sampling_algorithm}")
        logger.info(f"QPS限制: {qps_limit}, 并发数: {parallel_workers}")
        logger.info(f"即时保存: {enable_instant_save}, 断点续传: {enable_resume}")
        
        # 断点续传: 加载已存在的结果
        existing_results = {}
        entities_to_process = entities[:]
        skipped_entities = []
        
        if enable_resume:
            existing_results = self.load_existing_results(output_path)
            if existing_results:
                # 获取详细状态信息
                status = self.get_processing_status(entities, output_path)
                
                # 过滤掉已经处理的实体（基于实体名称，而非顺序）
                entities_to_process = status['remaining_entities']
                skipped_entities = status['completed_entities']
                
                print(f"\n🔄 断点续传模式:")
                print(f"   总实体数: {status['total_entities']} 个")
                print(f"   已完成: {status['completed_count']} 个 ({status['completion_rate']*100:.1f}%)")
                print(f"   待处理: {status['remaining_count']} 个")
                
                # 显示完成状态图
                print(f"\n📊 完成状态:")
                status_line = ""
                for i, entity in enumerate(entities, 1):
                    status_info = status['completion_map'][entity]
                    status_line += status_info['status']
                    if i % 20 == 0:  # 每20个换行
                        print(f"   {status_line}")
                        status_line = ""
                if status_line:
                    print(f"   {status_line}")
                
                print(f"\n   ✅ = 已完成, ⏳ = 待处理")
                logger.info(f"断点续传: 跳过 {len(skipped_entities)} 个已完成实体")
        
        # 统计信息
        total_entities = len(entities)
        entities_to_process_count = len(entities_to_process)
        successful_qa = len(existing_results)  # 已存在的结果
        failed_entities = []
        all_qa_results = list(existing_results.values())  # 已存在的结果
        
        # 创建信号量来控制并发数
        semaphore = asyncio.Semaphore(parallel_workers)
        
        # 创建速率限制器
        rate_limiter = AsyncRateLimiter(qps_limit) if qps_limit > 0 else None
        
        # 进度跟踪
        processed_count = 0
        lock = asyncio.Lock()
        
        async def process_single_entity(entity: str, index: int) -> Optional[Dict[str, Any]]:
            """处理单个实体的异步函数"""
            nonlocal processed_count, successful_qa
            
            async with semaphore:  # 控制并发数
                try:
                    if rate_limiter:
                        await rate_limiter.acquire()  # 控制QPS
                    
                    print(f"\n🔄 [{index:3d}/{total_entities}] 开始处理: {entity}")
                    logger.info(f"开始处理实体 {index}/{total_entities}: {entity}")
                    
                    # 创建运行管理器
                    run_manager = RunManager()
                    run_name = f"cli_batch_{entity}_{index}"
                    run_id = run_manager.create_new_run(run_name)
                    
                    print(f"    📁 创建运行记录: {run_id}")
                    logger.info(f"为实体 '{entity}' 创建运行记录: {run_id}")
                    
                    # 获取运行专用配置
                    run_paths = run_manager.get_run_paths()
                    
                    try:
                        # 构建知识图谱（已经包含QA生成）
                        print(f"    🏗️  构建知识图谱并生成QA...")
                        logger.info(f"开始为实体 '{entity}' 构建知识图谱并生成QA")
                        
                        from config import create_run_settings
                        from lib.graphrag_builder import GraphRagBuilder
                        
                        run_settings = create_run_settings(run_paths)
                        graphrag_builder = GraphRagBuilder(settings_instance=run_settings)
                        
                        # 构建知识图谱（内部会自动生成QA）
                        result = await graphrag_builder.build_knowledge_graph(
                            entity,
                            sampling_algorithm=sampling_algorithm,
                            use_unified_qa=use_unified_qa
                        )
                        
                        print(f"    ✅ 知识图谱构建和QA生成完成")
                        logger.info(f"实体 '{entity}' 知识图谱构建和QA生成完成")
                        
                        # 保存运行结果
                        run_manager.save_result(result, "knowledge_graph_result.json")
                        run_manager.complete_run(success=True)
                        
                        # 直接使用GraphRag构建过程中生成的QA结果
                        qa_pair = result.get('qa_pair', {})
                        
                        if qa_pair and qa_pair.get('question') and qa_pair.get('answer'):
                            # 转换为标准格式
                            qa_result = {
                                'question': qa_pair.get('question', ''),
                                'answer': qa_pair.get('answer', ''),
                                'reasoning_path': qa_pair.get('reasoning_path', ''),
                                'entity_mapping': qa_pair.get('entity_mapping', {}),
                                'generation_metadata': qa_pair.get('generation_metadata', {}),
                                'source_entity': entity,
                                'run_id': run_id,
                                'sampling_algorithm': sampling_algorithm,
                                'timestamp': datetime.now().isoformat()
                            }
                            
                            # 计算当前完成进度（包括之前已完成的）
                            current_progress = processed_count + 1 + len(existing_results)
                            print(f"    🎯 QA已生成! 总进度: {current_progress}/{total_entities} ({current_progress/total_entities*100:.1f}%)")
                            logger.info(f"实体 '{entity}' QA生成成功，总进度: {current_progress}/{total_entities}")
                            
                            # 清理GraphRag构建器
                            if 'graphrag_builder' in locals():
                                graphrag_builder.cleanup()
                            
                            # 即时保存
                            if enable_instant_save:
                                self.save_single_qa(qa_result, output_path)
                                print(f"    💾 即时保存完成")
                            
                            # 更新统计
                            async with lock:
                                processed_count += 1
                                all_qa_results.append(qa_result)
                                successful_qa += 1
                            
                            return qa_result
                        else:
                            print(f"    ⚠️  QA生成为空")
                            logger.warning(f"实体 '{entity}' QA生成结果为空")
                            
                            # 清理GraphRag构建器
                            if 'graphrag_builder' in locals():
                                graphrag_builder.cleanup()
                            
                            # 更新统计
                            async with lock:
                                processed_count += 1
                            
                            return None
                        
                    except Exception as e:
                        print(f"    ❌ 处理失败: {str(e)}")
                        logger.error(f"处理实体 '{entity}' 失败: {e}")
                        
                        async with lock:
                            processed_count += 1
                            failed_entities.append({'entity': entity, 'error': str(e), 'index': index})
                        
                        run_manager.complete_run(success=False, error_message=str(e))
                        return None
                        
                except Exception as e:
                    print(f"    💥 未预期错误: {str(e)}")
                    logger.error(f"处理实体 '{entity}' 时发生未预期错误: {e}")
                    
                    async with lock:
                        processed_count += 1
                        failed_entities.append({'entity': entity, 'error': str(e), 'index': index})
                    
                    return None
        
        try:
            if entities_to_process_count == 0:
                print(f"\n✅ 所有实体已处理完成，无需继续处理!")
                print(f"📊 总计: {total_entities} 个实体，已完成: {len(existing_results)} 个")
            else:
                print(f"\n🚀 开始并行处理 {entities_to_process_count} 个实体...")
                print(f"📊 并发数: {parallel_workers}, QPS限制: {qps_limit}")
                if enable_resume and existing_results:
                    print(f"🔄 断点续传: 跳过 {len(existing_results)} 个已完成实体")
                print("=" * 80)
                
                # 创建要处理的任务
                tasks = []
                for i, entity in enumerate(entities_to_process, 1):
                    # 使用全局索引来显示正确的进度
                    global_index = entities.index(entity) + 1
                    task = asyncio.create_task(process_single_entity(entity, global_index))
                    tasks.append(task)
                
                # 等待所有任务完成
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
            print(f"\n" + "=" * 80)
            
            # 最终保存结果
            if not enable_instant_save:
                print(f"\n\n💾 保存 {len(all_qa_results)} 个QA结果到: {output_path}")
                self.save_qa_results(all_qa_results, output_path)
            else:
                print(f"\n\n✅ 已通过即时保存完成 {len(all_qa_results)} 个QA结果: {output_path}")
            
            # 保存失败记录
            if failed_entities:
                failed_path = output_path.replace('.jsonl', '_failed.json')
                with open(failed_path, 'w', encoding='utf-8') as f:
                    json.dump(failed_entities, f, ensure_ascii=False, indent=2)
                print(f"❌ 失败记录保存到: {failed_path}")
            
            # 统计结果
            result_summary = {
                'total_entities': total_entities,
                'processed_entities': processed_count,
                'successful_qa': successful_qa,
                'failed_entities': len(failed_entities),
                'success_rate': successful_qa / total_entities if total_entities > 0 else 0,
                'output_path': output_path,
                'timestamp': datetime.now().isoformat()
            }
            
            return result_summary
            
        except Exception as e:
            logger.error(f"批量生成QA失败: {e}")
            raise
    
    def save_qa_results(self, qa_results: List[Dict[str, Any]], output_path: str):
        """保存QA结果到文件"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存为JSONL格式
        with open(output_file, 'w', encoding='utf-8') as f:
            for qa in qa_results:
                f.write(json.dumps(qa, ensure_ascii=False) + '\n')
        
        logger.info(f"保存 {len(qa_results)} 个QA结果到: {output_path}")
    
    def print_summary(self, summary: Dict[str, Any]):
        """打印生成总结"""
        print("\n" + "=" * 60)
        print("📊 批量QA生成总结")
        print("=" * 60)
        print(f"总实体数量: {summary['total_entities']}")
        print(f"已处理实体: {summary['processed_entities']}")
        print(f"成功生成QA: {summary['successful_qa']}")
        print(f"失败实体数: {summary['failed_entities']}")
        print(f"成功率: {summary['success_rate']:.2%}")
        print(f"输出文件: {summary['output_path']}")
        print(f"完成时间: {summary['timestamp']}")
        print("=" * 60)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="命令行批量QA生成脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                                           # 交互式选择种子文件
  %(prog)s --seed-file medical_entities.csv         # 指定种子文件
  %(prog)s --list-seeds                             # 列出可用种子文件
  %(prog)s --seed-file test.csv --output custom.jsonl --sample-size 10
  %(prog)s --seed-file entities.csv --qps-limit 1.5 --parallel-workers 1

输出文件说明:
  - 默认输出到 qa_output/ 目录
  - 文件名格式: {种子文件名}_{实体数量}entities_{时间戳}.jsonl
  - 失败记录会保存到 {输出文件}_failed.json
        """
    )
    
    # 基本参数
    parser.add_argument('--seed-file', '-s', help='种子文件名（CSV格式）')
    parser.add_argument('--output', '-o', help='输出文件路径（默认自动生成）')
    parser.add_argument('--list-seeds', action='store_true', help='列出可用的种子文件')
    parser.add_argument('--status', action='store_true', help='查看指定文件的处理状态（需要同时指定seed-file和output）')
    
    # 生成参数

    parser.add_argument('--sampling-algorithm', choices=['mixed', 'augmented_chain', 'community_core_path', 'dual_core_bridge', 'max_chain'], 
                       default='max_chain', help='采样算法（默认: max_chain）')
    parser.add_argument('--max-nodes', type=int, default=200, help='最大节点数（默认: 200）')
    parser.add_argument('--max-iterations', type=int, default=10, help='最大迭代数（默认: 10）')
    parser.add_argument('--use-traditional-qa', action='store_true', help='使用传统两步QA生成（默认使用统一生成器）')
    
    # 性能参数
    parser.add_argument('--parallel-workers', type=int, default=20, help='并发工作线程数（默认: 20')
    parser.add_argument('--qps-limit', type=float, default=20, help='QPS限制（默认: 20')
    
    # 即时保存和断点续传参数
    parser.add_argument('--disable-instant-save', action='store_true', help='禁用即时保存（默认启用）')
    parser.add_argument('--disable-resume', action='store_true', help='禁用断点续传（默认启用）')
    parser.add_argument('--force-overwrite', action='store_true', help='强制覆盖已存在的文件，禁用断点续传')
    
    # 调试参数
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 创建CLI实例
    cli = BatchQACLI()
    
    # 列出种子文件
    if args.list_seeds:
        seed_files = cli.list_available_seed_files()
        print(f"\n📂 在 {cli.seed_files_dir} 目录下找到 {len(seed_files)} 个种子文件:")
        print("=" * 60)
        for i, file in enumerate(seed_files, 1):
            try:
                entities = cli.load_entities_from_csv(file)
                print(f"{i:2d}. {file} ({len(entities)} 个实体)")
            except Exception as e:
                print(f"{i:2d}. {file} (读取失败: {e})")
        print("=" * 60)
        return
    
    # 查看处理状态
    if args.status:
        if not args.seed_file or not args.output:
            print("❌ --status 选项需要同时指定 --seed-file 和 --output 参数")
            sys.exit(1)
        
        seed_file = args.seed_file
        if not seed_file.endswith('.csv'):
            seed_file += '.csv'
        
        try:
            entities = cli.load_entities_from_csv(seed_file)
            status = cli.get_processing_status(entities, args.output)
            
            print(f"\n📊 处理状态报告")
            print("=" * 60)
            print(f"种子文件: {seed_file}")
            print(f"输出文件: {args.output}")
            print(f"总实体数: {status['total_entities']}")
            print(f"已完成: {status['completed_count']} 个 ({status['completion_rate']*100:.1f}%)")
            print(f"待处理: {status['remaining_count']} 个")
            
            if status['completed_count'] > 0:
                print(f"\n✅ 已完成的实体:")
                for entity in status['completed_entities']:
                    index = status['completion_map'][entity]['index']
                    print(f"   [{index:3d}] {entity}")
            
            if status['remaining_count'] > 0:
                print(f"\n⏳ 待处理的实体:")
                for entity in status['remaining_entities']:
                    index = status['completion_map'][entity]['index']
                    print(f"   [{index:3d}] {entity}")
            
            # 显示完成状态图
            print(f"\n📊 完成状态图:")
            status_line = ""
            for i, entity in enumerate(entities, 1):
                status_info = status['completion_map'][entity]
                status_line += status_info['status']
                if i % 20 == 0:  # 每20个换行
                    print(f"   {status_line}")
                    status_line = ""
            if status_line:
                print(f"   {status_line}")
            
            print(f"\n   ✅ = 已完成, ⏳ = 待处理")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 查看状态失败: {e}")
            sys.exit(1)
        
        return
    
    # 选择种子文件
    if args.seed_file:
        seed_file = args.seed_file
        if not seed_file.endswith('.csv'):
            seed_file += '.csv'
    else:
        seed_file = cli.interactive_select_seed_file()
    
    # 加载实体
    try:
        entities = cli.load_entities_from_csv(seed_file)
        print(f"\n✅ 成功加载种子文件: {seed_file}")
        print(f"📊 包含 {len(entities)} 个实体")
    except Exception as e:
        print(f"❌ 加载种子文件失败: {e}")
        sys.exit(1)
    
    # 确定输出路径
    if args.output:
        output_path = args.output
    else:
        output_path = cli.generate_default_output_path(seed_file, len(entities))
    
    print(f"📁 输出路径: {output_path}")
    
    # 处理强制覆盖选项
    enable_resume = not args.disable_resume and not args.force_overwrite
    enable_instant_save = not args.disable_instant_save
    
    if args.force_overwrite and os.path.exists(output_path):
        print(f"\n⚠️  强制覆盖模式: 将删除已存在的文件 {output_path}")
        try:
            os.remove(output_path)
        except Exception as e:
            print(f"❌ 删除文件失败: {e}")
            sys.exit(1)
    
    # 显示配置
    print(f"\n⚙️  生成配置:")
    print(f"   采样算法: {args.sampling_algorithm}")
    print(f"   最大节点数: {args.max_nodes}")
    print(f"   最大迭代数: {args.max_iterations}")
    print(f"   QA生成方式: {'传统两步法' if args.use_traditional_qa else '统一生成器'}")
    print(f"   并发工作数: {args.parallel_workers}")
    print(f"   QPS限制: {args.qps_limit}")
    print(f"   即时保存: {'启用' if enable_instant_save else '禁用'}")
    print(f"   断点续传: {'启用' if enable_resume else '禁用'}")
    print(f"   模糊化概率: 默认0.3 (暂不支持自定义)")
    print(f"   采样大小: 由GraphRag内部智能决定")
    
    # 确认开始
    try:
        confirm = input(f"\n🚀 是否开始生成? (y/N): ")
        if confirm.lower() not in ['y', 'yes', '是']:
            print("用户取消操作")
            sys.exit(0)
    except KeyboardInterrupt:
        print("\n用户取消操作")
        sys.exit(0)
    
    # 开始生成
    try:
        print(f"\n🔥 开始批量QA生成...")
        summary = asyncio.run(cli.batch_generate_qa(
            entities=entities,
            output_path=output_path,
            sampling_algorithm=args.sampling_algorithm,
            use_unified_qa=not args.use_traditional_qa,
            max_nodes=args.max_nodes,
            max_iterations=args.max_iterations,
            parallel_workers=args.parallel_workers,
            qps_limit=args.qps_limit,
            enable_resume=enable_resume,
            enable_instant_save=enable_instant_save
        ))
        
        cli.print_summary(summary)
        
        if summary['successful_qa'] > 0:
            print(f"\n🎉 批量QA生成完成！生成了 {summary['successful_qa']} 个QA对")
        else:
            print(f"\n⚠️  批量QA生成完成，但没有成功生成任何QA对")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n\n⏹️  用户中断操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 批量QA生成失败: {e}")
        logger.error(f"批量QA生成失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
