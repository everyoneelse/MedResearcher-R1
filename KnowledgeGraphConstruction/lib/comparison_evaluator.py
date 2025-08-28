import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import openai
from config import settings

# 配置日志
logger = logging.getLogger(__name__)

class ComparisonEvaluator:
    """对比评测器，用于比较两个数据集的QA质量"""
    
    def __init__(self):
        # 创建OpenAI客户端
        self.client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        self.judge_model = "deepseek-v3-250324"  # 判断模型
        
        # 对比评测的提示词
        self.comparison_prompt = """任务目标：
我们的竞赛旨在寻找“中文互联网下，高检索难度QA问题”。请牢记，我们的核心标准是问题的**“结构复杂度”，而非“语言复杂度”。一个优秀的问题，应该像一个精巧的“多米诺骨牌”或“寻宝地图”，其难度体现在推理链条的长度、跨度以及线索的巧妙性**上。它的答案是明确且容易验证的。

核心评价原则：“推理链”标准
请将每个问题视为一个“推理链”（A → B → C → ... → 答案）。评价的重点是这个链条的质量。请避免被问题的专业术语、句式难度或主题的“高大上”程度所影响。一个用简单语言连接了体育、音乐和地理的问题，远胜于一个用复杂术语描述单一技术概念的问题。

数据集A的QA对：
问题：{question_a}
答案：{answer_a}

数据集B的QA对：
问题：{question_b}
答案：{answer_b}

以下是评分标准指导：
一个理想的高难度QA问题，其难度应主要源于推理结构的复杂性，而非单一的知识壁垒或文字晦涩性。一个设计精良的问题能有效地区分出用户解决复杂问题的能力。本框架旨在提供一个平衡的视角，全面评估QA问题的设计质量，并识别其优势与可改进之处。

第一步：推理路径还原
在评估前，请先将问题的解答路径完整地、客观地还原出来。这是后续所有分析的基础。
对A进行还原： 写出解答问题A所必须的每一个推理步骤或信息节点。
格式：初始线索 → 识别实体X → 利用X的属性跳转 → 识别实体Y → ... → 最终答案
对B进行还原： 用同样的方式，还原问题B的解答路径。

第二步：核心维度评估
请依据以下四个维度，结合还原的推理路径，对每个QA对进行分析。

1. 推理结构 (Reasoning Structure)
评估要点： 考察问题内在的逻辑链条的长度、深度与复杂度。
评判指南：
优秀设计： 具有清晰且环环相扣的多级推理步骤（通常≥3步），每一步都是下一步的必要基础，形成一个完整的逻辑闭环。
中等设计： 具备一定的推理步骤，但链条较短，或步骤间关联性不强。
待改进设计： 本质上是“单步推理”，即通过解读一段复杂描述来直接识别答案，缺乏真正的逻辑递进。

2. 知识广度 (Knowledge Scope)
评估要点： 考察问题所涉及的知识领域的广度与关联方式。
评判指南：
优秀设计： 巧妙地横跨多个（≥3个）不相关的知识领域（如：艺术→地理→科技），要求用户具备广阔的知识视野和信息整合能力。
中等设计： 涉及两个领域的关联，或在同一领域内的不同分支间跳转。
待改进设计： 问题的所有线索和推理过程都局限在单一、垂直的专业领域内。这更多考验的是用户的专业深度，而非广度。

3. 信息设计 (Information Design)
评估要点： 考察问题文本中线索的有效性、精确性和“信噪比”。
评判指南：
优秀设计： 问题中的绝大部分文字都是解开谜题的必要线索，语言精炼且带有巧妙的“伪装”，能有效引导推理方向，信噪比高。
中等设计： 包含有效线索，但也夹杂了一些非必要的迷惑性信息或冗余描述。
待改进设计： 问题文本充斥着大量与核心推理无关的、仅为提升阅读难度的专业术语或复杂句式，信噪比低，有效信息被淹没。

4. 答案品质 (Answer Quality)
评估要点： 考察最终答案的确定性、精确性以及与问题起点的关联度。
评判指南：
优秀设计： 答案是唯一的、明确的、易于验证的实体（如具体人名、事件名、数字），且与问题的初始描述存在强烈的“意外感”和认知反差。
中等设计： 答案较为明确，但与问题起点的关联度较高，容易被预测。
待改进设计： 答案是一个宽泛的概念、模棱两可，或其验证过程本身就充满争议，不符合“答案明确易于验证”的基本要求。

回答格式：
胜者：A/B/T
A的路径： [复制第一步中对A的还原结果]
B的路径： [复制第一步中对B的还原结果]
理由：[详细说明为什么选择这个答案，从上述维度进行分析，提出改进建议]"""

    async def _call_judge_model(self, question_a: str, answer_a: str, question_b: str, answer_b: str) -> tuple[str, str]:
        """调用判断模型进行对比评估"""
        try:
            prompt = self.comparison_prompt.format(
                question_a=question_a,
                answer_a=answer_a,
                question_b=question_b,
                answer_b=answer_b
            )
            
            response = await self.client.chat.completions.create(
                model=self.judge_model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            result = response.choices[0].message.content.strip()
            
            # 解析结果
            lines = result.split('\n')
            winner = 'T'  # 默认平局
            reason = result  # 默认整个回复作为理由
            
            for line in lines:
                if line.startswith('胜者：') or line.startswith('胜者:'):
                    winner_text = line.split('：')[-1].split(':')[-1].strip()
                    if winner_text in ['A', 'B', 'T']:
                        winner = winner_text
                elif line.startswith('理由：') or line.startswith('理由:'):
                    reason = line.split('：', 1)[-1].split(':', 1)[-1].strip()
                    # 如果理由后面还有内容，也包含进来
                    rest_lines = lines[lines.index(line) + 1:]
                    if rest_lines:
                        reason += '\n' + '\n'.join(rest_lines)
                    break
            
            return winner, reason
            
        except Exception as e:
            logger.error(f"判断模型调用失败: {e}")
            return 'T', f"评估失败: {str(e)}"

    def load_dataset_file(self, file_id: str, file_type: str) -> List[Dict[str, Any]]:
        """加载数据集文件"""
        try:
            # 确定文件路径
            if file_type == 'standard':
                file_path = f'evaluation_data/standard_datasets/{file_id}'
            elif file_type == 'generated':
                file_path = f'evaluation_data/generated_datasets/{file_id}'
            else:
                raise ValueError(f"不支持的文件类型: {file_type}")
            
            if not Path(file_path).exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            data = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data.append(json.loads(line))
            
            return data
            
        except Exception as e:
            logger.error(f"加载数据集文件失败: {e}")
            raise

    def sample_qa_pairs(self, dataset: List[Dict[str, Any]], sample_count: int) -> List[Dict[str, Any]]:
        """从数据集中随机采样QA对"""
        if len(dataset) <= sample_count:
            return dataset.copy()
        
        return random.sample(dataset, sample_count)

    def _save_comparison_log(self, comparison_id: str, config: Dict[str, Any], 
                           question_a: str, answer_a: str, question_b: str, answer_b: str, 
                           winner: str, reason: str, index: int):
        """保存详细的对比日志"""
        try:
            # 创建对比日志目录
            log_dir = Path("evaluation_data/comparison_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 构建日志文件名
            log_filename = f"comparison_{comparison_id}.jsonl"
            log_path = log_dir / log_filename
            
            # 构建日志条目
            log_entry = {
                "index": index,
                "datasetA_qa": {
                    "question": question_a,
                    "answer": answer_a
                },
                "datasetB_qa": {
                    "question": question_b,
                    "answer": answer_b
                },
                "winner": winner,
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "comparison_id": comparison_id,
                "config": config
            }
            
            # 追加写入日志文件
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.error(f"保存对比日志失败: {e}")

    async def _process_single_comparison(self, task_item: Dict, config: Dict[str, Any], 
                                       progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """处理单次对比任务"""
        index = task_item["index"]
        qa_a = task_item["qa_a"]
        qa_b = task_item["qa_b"]
        comparison_id = config.get("comparison_id", "unknown")
        
        try:
            # 提取问题和答案
            question_a = qa_a.get('question', '')
            answer_a = qa_a.get('answer', '')
            question_b = qa_b.get('question', '')
            answer_b = qa_b.get('answer', '')
            
            if progress_callback:
                progress_callback(
                    f"第{index}题: 评判中...", 
                    None,
                    task_id=f"comparison_{index}",
                    status="running"
                )
            
            logger.info(f"第{index}题: 开始对比评估")
            
            # 调用判断模型（现在比较两个不同的QA对）
            winner, reason = await self._call_judge_model(question_a, answer_a, question_b, answer_b)
            
            logger.info(f"第{index}题: 对比评估完成，获胜者: {winner}")
            
            # 构建结果
            result = {
                "index": index,
                "datasetA_qa": {
                    "question": question_a,
                    "answer": answer_a
                },
                "datasetB_qa": {
                    "question": question_b,
                    "answer": answer_b
                },
                "winner": winner,  # 'A', 'B', 'T'
                "reason": reason
            }
            
            # 保存详细日志
            self._save_comparison_log(
                comparison_id=comparison_id,
                config=config,
                question_a=question_a,
                answer_a=answer_a,
                question_b=question_b,
                answer_b=answer_b,
                winner=winner,
                reason=reason,
                index=index
            )
            
            return result
            
        except Exception as e:
            logger.error(f"第{index}题: 对比失败 - {e}")
            
            # 构建错误结果
            error_result = {
                "index": index,
                "datasetA_qa": {
                    "question": qa_a.get('question', ''),
                    "answer": qa_a.get('answer', '')
                },
                "datasetB_qa": {
                    "question": qa_b.get('question', ''),
                    "answer": qa_b.get('answer', '')
                },
                "winner": "T",  # 错误时默认平局
                "reason": f"评估出错: {str(e)}",
                "error": str(e)
            }
            
            return error_result

    async def compare_datasets(self, config: Dict[str, Any], 
                             progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """比较两个数据集"""
        try:
            # 生成对比ID
            comparison_id = f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            config['comparison_id'] = comparison_id
            
            # 加载数据集
            dataset_a_info = config['datasetA']
            dataset_b_info = config['datasetB']
            
            logger.info(f"开始对比评测: {dataset_a_info['name']} vs {dataset_b_info['name']}")
            
            dataset_a = self.load_dataset_file(dataset_a_info['id'], dataset_a_info['type'])
            dataset_b = self.load_dataset_file(dataset_b_info['id'], dataset_b_info['type'])
            
            # 采样QA对
            sample_count = config['sampleCount']
            sampled_a = self.sample_qa_pairs(dataset_a, sample_count)
            sampled_b = self.sample_qa_pairs(dataset_b, sample_count)
            
            # 确保采样数量一致
            min_count = min(len(sampled_a), len(sampled_b))
            sampled_a = sampled_a[:min_count]
            sampled_b = sampled_b[:min_count]
            
            logger.info(f"采样完成，每个数据集 {min_count} 条数据")
            
            # 创建对比任务
            tasks = []
            for i in range(min_count):
                task_item = {
                    "index": i + 1,
                    "qa_a": sampled_a[i],
                    "qa_b": sampled_b[i],
                    "task_id": f"comparison_{i + 1}"
                }
                tasks.append(task_item)
            
            # 并发执行对比任务
            workers = config.get('workers', 2)
            results = []
            
            # 使用信号量控制并发数量
            semaphore = asyncio.Semaphore(workers)
            completed_count = 0
            total_count = len(tasks)
            
            async def worker_task(task_item):
                nonlocal completed_count
                async with semaphore:
                    result = await self._process_single_comparison(task_item, config, progress_callback)
                    
                    completed_count += 1
                    if progress_callback:
                        progress_percent = (completed_count / total_count) * 100
                        
                        # 计算当前胜负情况
                        datasetA_wins = sum(1 for r in results if r.get('winner') == 'A')
                        datasetB_wins = sum(1 for r in results if r.get('winner') == 'B')
                        ties = sum(1 for r in results if r.get('winner') == 'T')
                        
                        progress_callback(
                            f"第{result['index']}题: 完成 - 获胜者: {result['winner']} ({completed_count}/{total_count})",
                            progress_percent,
                            task_id=task_item["task_id"],
                            status="completed",
                            details={
                                "completed": completed_count,
                                "total": total_count,
                                "datasetA_wins": datasetA_wins,
                                "datasetB_wins": datasetB_wins,
                                "ties": ties
                            }
                        )
                    
                    return result
            
            # 并发执行所有任务
            results = await asyncio.gather(*[worker_task(task) for task in tasks])
            
            # 计算最终统计
            datasetA_wins = sum(1 for r in results if r.get('winner') == 'A')
            datasetB_wins = sum(1 for r in results if r.get('winner') == 'B')
            ties = sum(1 for r in results if r.get('winner') == 'T')
            
            # 确定总体获胜者
            overall_winner = 'datasetA' if datasetA_wins > datasetB_wins else \
                           'datasetB' if datasetB_wins > datasetA_wins else 'tie'
            
            # 保存对比结果
            comparison_result = {
                "comparison_id": comparison_id,
                "datasetA_name": dataset_a_info['name'],
                "datasetB_name": dataset_b_info['name'],
                "datasetA_id": dataset_a_info['id'],
                "datasetB_id": dataset_b_info['id'],
                "config": config,
                "timestamp": datetime.now().strftime('%Y%m%d_%H%M%S'),
                "completed_at": datetime.now().isoformat(),
                "total_comparisons": len(results),
                "datasetA_wins": datasetA_wins,
                "datasetB_wins": datasetB_wins,
                "ties": ties,
                "overall_winner": overall_winner,
                "results": results
            }
            
            # 保存到文件
            results_dir = Path("evaluation_data/comparison_results")
            results_dir.mkdir(parents=True, exist_ok=True)
            
            result_file = results_dir / f"{comparison_id}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(comparison_result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"对比评测完成: {dataset_a_info['name']} vs {dataset_b_info['name']}")
            logger.info(f"结果: A={datasetA_wins}, B={datasetB_wins}, 平局={ties}, 总体获胜者={overall_winner}")
            
            return comparison_result
            
        except Exception as e:
            logger.error(f"对比评测失败: {e}")
            raise

    def get_comparison_history(self) -> List[Dict[str, Any]]:
        """获取对比评测历史记录"""
        try:
            results_dir = Path("evaluation_data/comparison_results")
            if not results_dir.exists():
                return []
            
            history = []
            for file_path in results_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # 提取摘要信息
                    summary = {
                        "id": data.get("comparison_id"),
                        "datasetA_name": data.get("datasetA_name"),
                        "datasetB_name": data.get("datasetB_name"),
                        "completed_at": data.get("completed_at", "").replace('T', ' ').split('.')[0],
                        "datasetA_score": data.get("datasetA_wins", 0),
                        "datasetB_score": data.get("datasetB_wins", 0),
                        "ties": data.get("ties", 0),
                        "winner": data.get("overall_winner", "tie"),
                        "total_comparisons": data.get("total_comparisons", 0)
                    }
                    history.append(summary)
                    
                except Exception as e:
                    logger.warning(f"读取对比结果文件失败: {file_path}, 错误: {e}")
            
            # 按完成时间倒序排列
            history.sort(key=lambda x: x["completed_at"], reverse=True)
            return history
            
        except Exception as e:
            logger.error(f"获取对比历史失败: {e}")
            return []

    def get_comparison_details(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        """获取对比评测详细结果"""
        try:
            file_path = Path(f"evaluation_data/comparison_results/{comparison_id}.json")
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"读取对比详情失败: {e}")
            return None 