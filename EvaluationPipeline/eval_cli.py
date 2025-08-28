#!/usr/bin/env python3
"""
评估管道命令行工具

使用前配置API密钥：
  在 evaluation_config.json 中设置：
  - llm.api_key_env: LLM API密钥环境变量名
  
  在 tools/tool_config.json 中设置：
  - 搜索和访问工具的API密钥配置

数据集格式要求：
- JSONL格式，每行一个JSON对象
- 必需字段：question, answer
- 可选字段：context, metadata

使用示例：
    python eval_cli.py --mode interactive                      # 交互式体验agent能力
    python eval_cli.py --mode batch --dataset sample           # 批量推理+评估（自动续跑）
    python eval_cli.py --mode batch --dataset sample --rollouts 3  # 每题推理3次
    python eval_cli.py --mode batch --dataset sample --workers 4   # 使用4个并行worker
    python eval_cli.py --list-datasets                         # 列出可用数据集
"""

import argparse
import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    print("⚠️  tqdm not available, using simple progress display")

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["LANGCHAIN_VERBOSITY"] = "error"
os.environ["OPENAI_LOG_LEVEL"] = "error"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
# 导入推理模块
try:
    from src.core.reasoning_engine import create_reasoning_agent
except ImportError:
    print("❌ 无法导入推理引擎模块")
    print("请确保在EvaluationPipeline目录下运行此脚本")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_logging_silence():
    """强制屏蔽第三方库的冗余日志"""
    silence_loggers = [
        'httpx', 'openai', 'urllib3', 'requests', 'httpcore',
        'transformers', 'langchain', 'langchain_core', 'langchain_openai',
        'langgraph', 'tiktoken', 'openai._base_client', 'httpx._client'
    ]
    
    for logger_name in silence_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    
    root_logger = logging.getLogger()
    if root_logger.level < logging.INFO:
        root_logger.setLevel(logging.INFO)

# 立即执行日志静默设置
setup_logging_silence()


def run_interactive_reasoning(reasoning_agent):
    """交互式体验agent能力"""
    print("\n🤔 交互式推理模式")
    print("=" * 60)
    print("💡 输入问题体验agent的推理能力，输入 'quit' 或 'exit' 退出")
    
    while True:
        try:
            question = input("\n请输入你的问题: ").strip()
            if not question:
                print("❌ 问题不能为空")
                continue
            
            if question.lower() in ['quit', 'exit', '退出']:
                print("👋 再见！")
                break
                
            print(f"\n🚀 开始推理: {question}")
            print("=" * 80)
            
            result = reasoning_agent.run(question)
            
            print("\n🎯 最终结果摘要:")
            print("=" * 80)
            print(f"问题: {question}")
            print(f"预测答案: {result.get('prediction', 'No answer found.')}")
            print(f"工具调用次数: {result.get('tool_calls', 0)}")
            print(f"推理耗时: {result.get('duration', 0):.2f} 秒")
            print(f"终止原因: {result.get('termination', 'unknown')}")
            
        except KeyboardInterrupt:
            print("\n👋 用户退出")
            break
        except Exception as e:
            print(f"❌ 推理失败: {e}")
            logger.error(f"交互式推理失败: {e}")


def run_batch_evaluation(reasoning_agent, dataset_name, rollouts=1, workers=10):
    """批量运行：推理+评估"""
    print(f"\n📊 批量评估模式: {dataset_name}")
    print("=" * 60)
    
    print("🔇 屏蔽第三方库日志...")
    setup_logging_silence()
    
    additional_silence = [
        'openai._base_client', 'httpx._client', 'httpcore._sync',
        'transformers.tokenization_utils', 'transformers.modeling_utils',
        'urllib3.connectionpool', 'requests.packages.urllib3'
    ]
    for logger_name in additional_silence:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
    
    # 检查数据集
    dataset_path = f"datasets/{dataset_name}.jsonl"
    if not os.path.exists(dataset_path):
        print(f"❌ 数据集不存在: {dataset_path}")
        print("💡 使用 --list-datasets 查看可用数据集")
        return
    
    # 加载数据集
    try:
        items = []
        with open(dataset_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
        
        if not items:
            print(f"❌ 数据集为空: {dataset_path}")
            return
        
        print(f"📂 数据集: {dataset_name}")
        print(f"   问题数量: {len(items)}")
        print(f"   每题推理次数: {rollouts}")
        print(f"   并行worker数: {workers}")
        print(f"   预计总推理次数: {len(items) * rollouts}")
        
        confirm = input(f"\n🚀 开始批量评估? (y/N): ")
        if confirm.lower() not in ['y', 'yes', '是']:
            print("用户取消操作")
            return
            
    except Exception as e:
        print(f"❌ 加载数据集失败: {e}")
        return
    
    try:
        os.makedirs("results", exist_ok=True)
        
        completed_tasks = set()
        trajectory_path = f"results/trajectories_{dataset_name}.jsonl"
        
        if os.path.exists(trajectory_path):
            print(f"\n🔄 续跑模式：检查已完成任务...")
            try:
                with open(trajectory_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            result = json.loads(line)
                            question = result.get('question', '').strip()
                            rollout = result.get('rollout', 1)
                            completed_tasks.add((question, rollout))
                print(f"   已完成任务: {len(completed_tasks)} 个")
            except Exception as e:
                print(f"   ⚠️  读取已完成任务失败: {e}")
                completed_tasks = set()
        
        print(f"\n🔥 开始批量推理...")
        start_time = datetime.now()
        
        tasks_to_process = []
        for i, item in enumerate(items):
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            for rollout_id in range(rollouts):
                if (question.strip(), rollout_id + 1) not in completed_tasks:
                    tasks_to_process.append({
                        'item_index': i,
                        'question': question,
                        'answer': answer,
                        'rollout': rollout_id + 1,
                        'dataset': dataset_name
                    })
        
        print(f"   需要处理的任务数: {len(tasks_to_process)}")
        print(f"   跳过的已完成任务: {len(completed_tasks)}")
        
        if not tasks_to_process:
            print("✅ 所有任务已完成，无需处理")
        else:
            trajectory_results = []
            token_stats = {'total_tokens': 0, 'token_limited_count': 0, 'max_tokens': 0}
            write_lock = threading.Lock()
            stats_lock = threading.Lock()
            
            def process_single_task(task):
                try:
                    reasoning_result = reasoning_agent.run(task['question'])
                    prediction = reasoning_result.get('prediction', 'No answer found.')
                    
                    trajectory_result = {
                        'question': task['question'],
                        'answer': task['answer'],
                        'prediction': prediction,
                        'rollout': task['rollout'],
                        'dataset': task['dataset']
                    }
                    
                    trajectory_result.update(reasoning_result)
                    
                    with write_lock:
                        with open(trajectory_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(trajectory_result, ensure_ascii=False) + '\n')
                    
                    with stats_lock:
                        if 'token_count' in reasoning_result:
                            token_count = reasoning_result['token_count']
                            token_stats['total_tokens'] += token_count

                        if reasoning_result.get('termination') == 'exceed_token_length':
                            token_stats['token_limited_count'] += 1
                    
                    return trajectory_result
                    
                except Exception as e:
                    partial_reasoning_result = {}
                    try:
                        if hasattr(e, 'partial_result'):
                            partial_reasoning_result = e.partial_result
                    except:
                        pass
                    
                    error_result = {
                        'question': task['question'],
                        'answer': task['answer'],
                        'prediction': f'Error: {str(e)}',
                        'rollout': task['rollout'],
                        'error': str(e),
                        'dataset': task['dataset'],
                        'messages': [],
                        'termination': 'error',
                        'tool_calls': 0,
                        'duration': 0,
                        'token_count': 0
                    }
                    
                    if partial_reasoning_result:
                        error_result.update(partial_reasoning_result)
                    
                    with write_lock:
                        with open(trajectory_path, 'a', encoding='utf-8') as f:
                            f.write(json.dumps(error_result, ensure_ascii=False) + '\n')
                    
                    return error_result
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_task = {
                    executor.submit(process_single_task, task): task 
                    for task in tasks_to_process
                }
                
                if TQDM_AVAILABLE:
                    progress_bar = tqdm(
                        total=len(tasks_to_process),
                        desc="🔥 批量推理",
                        unit="task",
                        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
                    )
                else:
                    progress_bar = None
                    print("   开始处理任务...")
                
                completed_count = 0
                for future in as_completed(future_to_task):
                    task = future_to_task[future]
                    try:
                        result = future.result()
                        trajectory_results.append(result)
                        completed_count += 1
                        
                        if progress_bar:
                            progress_bar.set_postfix({
                                'question': task['question'][:25] + ('...' if len(task['question']) > 25 else ''),
                                'rollout': task['rollout']
                            })
                            progress_bar.update(1)
                        else:
                            if completed_count % max(1, len(tasks_to_process) // 20) == 0 or completed_count == len(tasks_to_process):
                                progress = completed_count / len(tasks_to_process) * 100
                                print(f"   进度: {completed_count}/{len(tasks_to_process)} ({progress:.1f}%) - 最新完成: {task['question'][:30]}...")
                        
                    except Exception as e:
                        completed_count += 1
                        if progress_bar:
                            progress_bar.set_postfix({'error': str(e)[:30]})
                            progress_bar.update(1)
                        else:
                            print(f"   ❌ 任务执行异常: {e}")
                
                if progress_bar:
                    progress_bar.close()

        print(f"\n📄 推理结果已保存: {trajectory_path}")
        
        if token_stats['total_tokens'] > 0:
            avg_tokens = token_stats['total_tokens'] / len(trajectory_results) if trajectory_results else 0
            print(f"\n📊 Token使用统计:")
            print(f"   总Token数: {token_stats['total_tokens']:,}")
            print(f"   平均Token数: {avg_tokens:.1f}")
            print(f"   最大Token数: {token_stats['max_tokens']:,}")
            if token_stats['token_limited_count'] > 0:
                print(f"   ⚠️  因Token超限提前结束: {token_stats['token_limited_count']} 次")
        
        print(f"\n🔍 开始评估结果...")
        
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TrajectoryGenerationPipeline', 'src', 'postprocessing'))
        from evaluation.evaluator import AnswerEvaluator
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', 
            'TrajectoryGenerationPipeline', 'src', 'postprocessing', 'config.json'
        )
        
        evaluator = AnswerEvaluator(config_path)
        
        all_trajectory_results = []
        if os.path.exists(trajectory_path):
            with open(trajectory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        all_trajectory_results.append(json.loads(line))
        
        print(f"   从文件读取 {len(all_trajectory_results)} 个结果进行评估")
        
        print("   🔍 开始LLM评估...")
        evaluated_results = evaluator.evaluate_batch(all_trajectory_results, dataset_type=dataset_name)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        evaluation_path = f"results/evaluation_{dataset_name}_{timestamp}"
        evaluation_stats = evaluator.save_evaluation_results(evaluated_results, evaluation_path, dataset_name)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n📈 批量评估完成，用时 {duration:.1f} 秒")
        print("=" * 60)
        print(f"数据集: {dataset_name}")
        print(f"总问题数: {len(items)}")
        print(f"总推理次数: {len(all_trajectory_results)}")
        print(f"成功推理: {len([r for r in all_trajectory_results if 'error' not in r])}")
        print(f"准确率: {evaluation_stats.get('accuracy', 0):.3f} ({evaluation_stats.get('accuracy', 0)*100:.1f}%)")
        print(f"📁 详细结果保存在: {evaluation_path}/")
        
    except Exception as e:
        print(f"❌ 批量评估失败: {e}")
        logger.error(f"批量评估失败: {e}")
        import traceback
        traceback.print_exc()


def list_datasets():
    """列出可用数据集"""
    print("\n📂 可用数据集列表")
    print("=" * 60)
    
    os.makedirs("datasets", exist_ok=True)
    datasets_path = Path("datasets")
    
    datasets = []
    for jsonl_file in datasets_path.glob("*.jsonl"):
        try:
            count = sum(1 for line in open(jsonl_file, 'r') if line.strip())
            size_mb = jsonl_file.stat().st_size / (1024 * 1024)
            modified = datetime.fromtimestamp(jsonl_file.stat().st_mtime)
            
            datasets.append({
                'name': jsonl_file.stem,
                'count': count,
                'size_mb': size_mb,
                'modified': modified
            })
        except Exception as e:
            logger.warning(f"读取数据集失败 {jsonl_file}: {e}")
    
    if not datasets:
        print("📭 没有找到可用的数据集")
        print("请将JSONL格式的数据集放在 datasets/ 目录下")
        print("数据集格式要求：")
        print("  - 每行一个JSON对象")
        print("  - 必需字段：question, answer")
    else:
        print(f"找到 {len(datasets)} 个数据集:")
        print("-" * 80)
        for i, ds in enumerate(sorted(datasets, key=lambda x: x['name']), 1):
            print(f"{i:2d}. {ds['name']}")
            print(f"     问题数量: {ds['count']}")
            print(f"     文件大小: {ds['size_mb']:.2f} MB")
            print(f"     修改时间: {ds['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            print()


def create_sample_dataset(name="sample", size=5):
    """创建示例数据集"""
    print(f"\n🛠️ 创建示例数据集: {name}")
    
    os.makedirs("datasets", exist_ok=True)
    dataset_path = f"datasets/{name}.jsonl"
    
    sample_data = []
    for i in range(size):
        item = {
            'question': f'测试问题{i+1}：什么是人工智能？',
            'answer': f'人工智能是计算机科学的一个重要分支，示例答案{i+1}。',
            'context': f'这是第{i+1}个测试问题的上下文信息。',
            'metadata': {
                'difficulty': 'easy',
                'category': 'test',
                'source': 'generated'
            }
        }
        sample_data.append(item)
    
    with open(dataset_path, 'w', encoding='utf-8') as f:
        for item in sample_data:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"✅ 示例数据集创建完成: {dataset_path}")
    print(f"   包含 {size} 个问题")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="评估管道命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用前配置API密钥：
  在 evaluation_config.json 中设置：
  - llm.api_key_env: LLM API密钥环境变量名
  
  在 tools/tool_config.json 中设置：
  - 搜索和访问工具的API密钥配置

使用示例:
  %(prog)s --mode interactive                        # 交互式体验agent能力
  %(prog)s --mode batch --dataset sample             # 批量推理+评估（自动续跑）
  %(prog)s --mode batch --dataset sample --workers 4 # 使用4个并行worker
  %(prog)s --list-datasets                           # 列出数据集
  %(prog)s --create-sample                           # 创建示例数据集
        """
    )
    
    parser.add_argument('--mode', choices=['interactive', 'batch'], help='运行模式：interactive(交互式) 或 batch(批量)')
    parser.add_argument('--dataset', '-d', help='数据集名称（不包含.jsonl扩展名，用于batch模式）')
    
    parser.add_argument('--list-datasets', action='store_true', help='列出可用数据集')
    parser.add_argument('--create-sample', action='store_true', help='创建示例数据集')
    
    parser.add_argument('--rollouts', type=int, default=3, help='每题推理次数（默认: 3）')
    parser.add_argument('--workers', type=int, default=10, help='并行worker数量（默认: 10）')
    
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        if args.list_datasets:
            list_datasets()
            return
        
        if args.create_sample:
            create_sample_dataset()
            return
        
        if args.mode == 'interactive':
            print("🔧 初始化推理引擎...")
            setup_logging_silence()
            try:
                reasoning_agent = create_reasoning_agent(verbose=True)
                print("✅ 推理引擎初始化成功")
                print("📢 已启用详细输出模式，将显示推理过程中的每步详情")
            except Exception as e:
                print(f"❌ 推理引擎初始化失败: {e}")
                print("💡 请检查 evaluation_config.json 中的API密钥配置")
                print("   确保设置了正确的 llm.api_key_env 等字段")
                sys.exit(1)
            
            run_interactive_reasoning(reasoning_agent)
            
        elif args.mode == 'batch':
            if not args.dataset:
                print("❌ 批量模式需要指定 --dataset 参数")
                print("💡 使用 --list-datasets 查看可用数据集")
                sys.exit(1)
            
            print("🔧 初始化推理引擎...")
            setup_logging_silence()
            try:
                reasoning_agent = create_reasoning_agent(verbose=False)  # 批量模式不启用详细输出
                print("✅ 推理引擎初始化成功")
            except Exception as e:
                print(f"❌ 推理引擎初始化失败: {e}")
                print("💡 请检查 evaluation_config.json 中的API密钥配置")
                print("   确保设置了正确的 llm.api_key_env 等字段")
                sys.exit(1)
            
            run_batch_evaluation(reasoning_agent, args.dataset, args.rollouts, args.workers)
        else:
            print("请指定运行模式:")
            print("  --mode interactive # 交互式体验agent能力")
            print("  --mode batch       # 批量推理+评估")
            print("  --list-datasets    # 列出数据集")
            print("  --create-sample    # 创建示例数据集")
    
    except KeyboardInterrupt:
        print("\n⏹️  用户中断操作")
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        logger.error(f"执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 