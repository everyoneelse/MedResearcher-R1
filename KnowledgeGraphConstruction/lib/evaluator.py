import asyncio
import json
import logging
import openai
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
from config import settings

# 配置日志
logger = logging.getLogger(__name__)

class Evaluator:
    """评测器，用于评估QA系统性能"""
    
    def __init__(self):
        # 创建OpenAI客户端
        self.client = openai.AsyncOpenAI(  # 使用异步客户端
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        self.r1_model = "DeepSeek-R1-0528"  # R1模型
        self.judge_model = "DeepSeek-V3"  # 判断模型
        
        # 判断提示词
        self.judge_prompt = """你是一个专业的答案质量评估师。你需要比较预测答案和标准答案，判断预测答案是否正确。

评估标准：
- A (CORRECT)：预测答案在事实上正确，与标准答案意思基本一致，即使表达方式不同
- B (INCORRECT)：预测答案在事实上错误，与标准答案意思不符
- C (NOT_ATTEMPTED)：预测答案没有尝试回答问题，如"我不知道"、"无法回答"等

请仔细比较以下内容：

问题：{question}

标准答案：{gold_answer}

预测答案：{predicted_answer}

你的回答必须只能是A、B、C中的一个字母，不包含任何其他字符、解释或括号。"""

    async def _call_r1_model(self, question: str, max_retries: int = 3) -> str:
        """调用R1模型回答问题"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                # 添加优化的prompt，要求简单明确的回答
                optimized_prompt = f"请简要，明确地回答下列问题：{question}"
                
                response = await self.client.chat.completions.create(
                    model=self.r1_model,
                    messages=[
                        {"role": "user", "content": optimized_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=10000,
                    stream=False,
                    extra_body={"enable_sec_check": False}
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                last_exception = e
                current_attempt = attempt + 1
                logger.warning(f"R1模型调用失败 (第{current_attempt}次尝试): {e}")
                
                # 如果不是最后一次尝试，等待后重试
                if current_attempt < max_retries:
                    wait_seconds = current_attempt  # 第1次重试等1秒，第2次重试等2秒，依此类推
                    logger.info(f"等待{wait_seconds}秒后进行第{current_attempt + 1}次重试...")
                    await asyncio.sleep(wait_seconds)
                else:
                    # 最后一次尝试失败，抛出异常
                    logger.error(f"R1模型调用失败，已重试{max_retries}次")
                    raise last_exception

    async def _call_judge_model(self, question: str, gold_answer: str, predicted_answer: str, max_retries: int = 3) -> str:
        """调用判断模型评估答案"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                prompt = self.judge_prompt.format(
                    question=question,
                    gold_answer=gold_answer,
                    predicted_answer=predicted_answer
                )
                
                response = await self.client.chat.completions.create(
                    model=self.judge_model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    max_tokens=50,
                    stream=False
                )
                
                result = response.choices[0].message.content.strip()
                # 确保返回值是A、B或C中的一个
                if result not in ['A', 'B', 'C']:
                    logger.warning(f"判断模型返回了无效结果: {result}, 默认为B")
                    return 'B'
                return result
            except Exception as e:
                last_exception = e
                current_attempt = attempt + 1
                logger.warning(f"判断模型调用失败 (第{current_attempt}次尝试): {e}")
                
                # 如果不是最后一次尝试，等待后重试
                if current_attempt < max_retries:
                    wait_seconds = current_attempt  # 第1次重试等1秒，第2次重试等2秒，依此类推
                    logger.info(f"等待{wait_seconds}秒后进行第{current_attempt + 1}次重试...")
                    await asyncio.sleep(wait_seconds)
                else:
                    # 最后一次尝试失败，抛出异常
                    logger.error(f"判断模型调用失败，已重试{max_retries}次")
                    raise last_exception



    def load_dataset(self, dataset_path: str) -> List[Dict[str, Any]]:
        """加载评测数据集"""
        try:
            data = []
            with open(dataset_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data.append(json.loads(line))
            return data
        except Exception as e:
            logger.error(f"加载数据集失败: {e}")
            raise

    def _save_detailed_log(self, dataset_name: str, mode: str, timestamp: str, 
                          question: str, gold_answer: str, predicted_answer: str, 
                          judgment: str, correct: bool, index: int, extra_data: dict = None):
        """保存详细的评测日志"""
        try:
            # 创建详细日志目录
            log_dir = Path("evaluation_data/detailed_logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # 构建日志文件名
            log_filename = f"detailed_{timestamp}_{dataset_name}_{mode}.jsonl"
            log_path = log_dir / log_filename
            
            # 构建日志条目
            log_entry = {
                "index": index,
                "question": question,
                "gold_answer": gold_answer,
                "predicted_answer": predicted_answer,
                "judgment": judgment,
                "correct": correct,
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
                "dataset_name": dataset_name
            }
            
            # 如果有额外数据，添加到日志中
            if extra_data:
                log_entry.update(extra_data)
            
            # 追加写入日志文件
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                
        except Exception as e:
            logger.error(f"保存详细日志失败: {e}")

    async def _process_single_task(self, task_item: Dict, progress_callback: Optional[Callable], 
                                  total_count: int, result_queue: asyncio.Queue, 
                                  mode: str = "R1-0528", dataset_name: str = "", timestamp: str = ""):
        """处理单个任务的完整流水线：模型推理 → 判断评估"""
        from .trace_manager import TraceManager, start_trace
        
        index = task_item["index"]
        question = task_item["question"]
        gold_answer = task_item["gold_answer"]
        task_id = task_item["task_id"]
        
        # 为单个评测任务创建子trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            # 创建基于父trace的子trace
            item_trace_id = TraceManager.create_batch_trace_id(parent_trace, index)
            start_trace(item_trace_id)
            logger.info(f"第{index}题: 继承评测trace: {item_trace_id}")
        else:
            # 创建独立的trace
            start_trace(prefix=f"eval_task_{index}")
            logger.info(f"第{index}题: 创建新评测trace")
        
        try:
            # 阶段1：R1模型推理
            if progress_callback:
                progress_callback(
                    f"第{index}题: R1模型推理中...", 
                    None,  # 中间状态不更新进度百分比
                    task_id=task_id,
                    status="running"
                )
            
            logger.info(f"第{index}题: 开始R1模型推理")
            
            # 调用R1模型
            predicted_answer = await self._call_r1_model(question)
                
            logger.info(f"第{index}题: R1模型推理完成")
            
            # 阶段2：判断评估
            if progress_callback:
                progress_callback(
                    f"第{index}题: 结果对比中，R1模型结果：{predicted_answer[:50]}...", 
                    None,  # 中间状态不更新进度百分比
                    task_id=task_id,
                    status="running"
                )
            
            logger.info(f"第{index}题: 开始判断评估")
            judgment = await self._call_judge_model(question, gold_answer, predicted_answer)
            logger.info(f"第{index}题: 判断评估完成")
            
            # 构建结果
            result = {
                "index": index,
                "question": question,
                "gold_answer": gold_answer,
                "predicted_answer": predicted_answer,
                "judgment": judgment,
                "correct": judgment == 'A'
            }
            
            # 保存详细日志
            self._save_detailed_log(
                dataset_name=dataset_name,
                mode=mode,
                timestamp=timestamp,
                question=question,
                gold_answer=gold_answer,
                predicted_answer=predicted_answer,
                judgment=judgment,
                correct=judgment == 'A',
                index=index,
                extra_data={}
            )
            
            logger.info(f"第{index}题: 流水线完成")
            
            # 将结果放入队列
            await result_queue.put(result)
            
            # 返回结果供worker使用
            return result
            
        except Exception as e:
            logger.error(f"第{index}题: 处理失败 - {e}")
            
            # 构建错误结果
            error_result = {
                "index": index,
                "question": question,
                "gold_answer": gold_answer,
                "predicted_answer": f"处理错误: {str(e)}",
                "judgment": "B",
                "correct": False,
                "error": str(e)
            }
            
            # 保存错误日志
            self._save_detailed_log(
                dataset_name=dataset_name,
                mode=mode,
                timestamp=timestamp,
                question=question,
                gold_answer=gold_answer,
                predicted_answer=error_result["predicted_answer"],
                judgment="B",
                correct=False,
                index=index,
                extra_data={"error": str(e)}
            )
            
            # 将错误结果放入队列
            await result_queue.put(error_result)
            
            # 返回错误结果供worker使用
            return error_result
        finally:
            # 清理trace
            from .trace_manager import end_trace
            end_trace()



    async def evaluate_dataset(self, dataset_path: str, dataset_name: str, mode: str = "R1-0528", 
                              progress_callback: Optional[Callable] = None, batch_size: int = 10) -> Dict[str, Any]:
        """评估整个数据集 - 使用流水线并发模式"""
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            logger.info(f"评测器继承trace: {parent_trace}")
        else:
            start_trace(prefix="evaluator")
            logger.info(f"评测器创建新trace")
        
        try:
            # 生成时间戳，用于日志记录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 加载数据集
            data = self.load_dataset(dataset_path)
            total_tasks = len(data)
            
            logger.info(f"开始评测数据集: {dataset_name}, 共{total_tasks}条数据，流水线并发数: {batch_size}，模式: {mode}")
            
            # 创建任务队列和结果存储
            task_queue = asyncio.Queue()
            results = [None] * total_tasks  # 预分配结果数组，确保索引对应
            
            # 创建完成计数器和锁
            completed_count = 0
            progress_lock = asyncio.Lock()
            
            # 将所有任务放入队列
            for i, item in enumerate(data):
                task_item = {
                    "index": i + 1,
                    "array_index": i,  # 添加数组索引，确保结果正确存储
                    "question": item.get("question", ""),
                    "gold_answer": item.get("answer", ""),
                    "task_id": f"task_{i + 1}"
                }
                await task_queue.put(task_item)
            
            # 添加结束信号
            for _ in range(batch_size):
                await task_queue.put(None)
            
            # 使用信号量控制并发数量
            semaphore = asyncio.Semaphore(batch_size)
            
            # 创建工作协程
            async def worker(worker_id: int):
                """工作协程 - 处理完整的流水线"""
                nonlocal completed_count
                
                while True:
                    try:
                        # 从队列获取任务
                        task_item = await task_queue.get()
                        
                        if task_item is None:  # 结束信号
                            logger.debug(f"工作协程 {worker_id} 收到结束信号，退出")
                            break
                        
                        # 检查是否已经处理完所有任务
                        async with progress_lock:
                            if completed_count >= total_tasks:
                                logger.warning(f"工作协程 {worker_id}: 已完成所有任务，跳过额外任务")
                                break
                        
                        async with semaphore:
                            # 创建一个临时的结果队列
                            temp_result_queue = asyncio.Queue()
                            result = await self._process_single_task(
                                task_item, 
                                progress_callback, 
                                total_tasks, 
                                temp_result_queue,
                                mode=mode,
                                dataset_name=dataset_name,
                                timestamp=timestamp
                            )
                            
                            # 将结果存储到正确的位置
                            if result and "array_index" in task_item:
                                array_index = task_item["array_index"]
                                if 0 <= array_index < total_tasks:
                                    results[array_index] = result
                        
                        # 更新完成计数并通知进度
                        async with progress_lock:
                            completed_count += 1
                            progress_percent = min(completed_count / total_tasks * 100, 100)  # 确保不超过100%
                            
                            # 通知任务完成
                            if progress_callback and result:
                                status = "CORRECT" if result.get("correct") else "INCORRECT" if result.get("judgment") == "B" else "ERROR"
                                progress_callback(
                                    f"第{result['index']}题: 完成 - {status} ({completed_count}/{total_tasks})", 
                                    progress_percent,
                                    task_id=task_item["task_id"],
                                    status="completed"
                                )
                                
                            logger.debug(f"工作协程 {worker_id}: 完成第{task_item['index']}题 ({completed_count}/{total_tasks})")
                        
                    except Exception as e:
                        logger.error(f"工作协程 {worker_id} 处理任务失败: {e}")
                        # 即使出错也要标记任务完成
                        async with progress_lock:
                            completed_count += 1
                            progress_percent = min(completed_count / total_tasks * 100, 100)
                            
                            # 通知任务失败
                            if progress_callback and task_item:
                                progress_callback(
                                    f"第{task_item.get('index', '?')}题: 系统错误 ({completed_count}/{total_tasks})", 
                                    progress_percent,
                                    task_id=task_item.get("task_id", "unknown"),
                                    status="completed"
                                )
            
            # 启动工作协程
            workers = [asyncio.create_task(worker(i)) for i in range(batch_size)]
            
            # 等待所有工作协程结束
            await asyncio.gather(*workers, return_exceptions=True)
            
            # 过滤掉None结果并确保连续性
            valid_results = [r for r in results if r is not None]
            
            # 验证结果完整性
            if len(valid_results) != total_tasks:
                logger.warning(f"结果数量不匹配: 期望{total_tasks}条，实际{len(valid_results)}条")
            
            # 按索引排序结果
            valid_results.sort(key=lambda x: x.get("index", 0))
            
            # 计算准确率
            correct_count = sum(1 for r in valid_results if r["correct"])
            accuracy = correct_count / len(valid_results) if valid_results else 0
            
            # 保存结果
            evaluation_id = f"eval_{timestamp}_{dataset_name}_{mode}"
            result_filename = f"{evaluation_id}.json"
            result_path = f"evaluation_data/evaluation_results/{result_filename}"
            
            # 确保目录存在
            Path("evaluation_data/evaluation_results").mkdir(parents=True, exist_ok=True)
            
            evaluation_result = {
                "evaluation_id": evaluation_id,
                "dataset_name": dataset_name,
                "mode": mode,
                "timestamp": timestamp,
                "submitted_at": datetime.now().isoformat(),
                "total_questions": len(valid_results),
                "correct_answers": correct_count,
                "accuracy": accuracy,
                "results": valid_results
            }
            
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(evaluation_result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"评测结果已保存到: {result_path}")
            logger.info(f"评测完成: {dataset_name}, 准确率: {accuracy:.2%} ({correct_count}/{len(valid_results)})")
            
            return evaluation_result
            
        except Exception as e:
            logger.error(f"评估数据集失败: {e}")
            raise

    def get_evaluation_results(self) -> List[Dict[str, Any]]:
        """获取历史评测结果"""
        try:
            results_dir = Path("evaluation_data/evaluation_results")
            if not results_dir.exists():
                return []
            
            results = []
            for file_path in results_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # 只返回摘要信息，不包含详细结果
                        summary = {
                            "dataset_name": data.get("dataset_name"),
                            "mode": data.get("mode"),
                            "timestamp": data.get("timestamp"),
                            "total_questions": data.get("total_questions"),
                            "correct_answers": data.get("correct_answers"),
                            "accuracy": data.get("accuracy"),
                            "filename": file_path.name
                        }
                        results.append(summary)
                except Exception as e:
                    logger.warning(f"读取结果文件失败: {file_path}, 错误: {e}")
            
            # 按时间戳排序，最新的在前
            results.sort(key=lambda x: x["timestamp"], reverse=True)
            return results
            
        except Exception as e:
            logger.error(f"获取评测结果失败: {e}")
            return []

    def get_evaluation_details(self, filename: str) -> Optional[Dict[str, Any]]:
        """获取评测详细结果"""
        try:
            file_path = Path(f"evaluation_data/evaluation_results/{filename}")
            if not file_path.exists():
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"读取评测详情失败: {e}")
            return None