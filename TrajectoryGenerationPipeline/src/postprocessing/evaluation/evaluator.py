#!/usr/bin/env python3
"""
Answer evaluation module using configurable judge prompts.
"""

import json
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from datetime import datetime
from collections import defaultdict
from pathlib import Path

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: OpenAI not available, evaluation will be disabled")

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class AnswerEvaluator:
    """
    Answer evaluator using configurable judge prompts.
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize the evaluator.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "..", "config.json")
        self.config = self._load_config()
        self.llm_client = self._init_llm_client()
        self.lock = threading.Lock()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
    
    def _init_llm_client(self) -> Optional[OpenAI]:
        """Initialize OpenAI client."""
        if not OPENAI_AVAILABLE:
            return None
        
        # Get API configuration from config
        llm_config = self.config["evaluation"]["llm_config"]
        api_key_env = llm_config.get("api_key_env", "OPENAI_API_KEY")
        api_base = llm_config.get("api_base", "https://api.openai.com/v1")
        
        api_key = os.getenv(api_key_env)
        if not api_key:
            print(f"Warning: {api_key_env} not found, evaluation will be disabled")
            return None
        
        return OpenAI(api_key=api_key, base_url=api_base)
    
    def get_judge_prompt(self, dataset_type: str) -> str:
        """
        Get appropriate judge prompt based on dataset type.
        
        Args:
            dataset_type: Type of dataset
            
        Returns:
            Judge prompt template
        """
        mappings = self.config["evaluation"]["dataset_mappings"]
        
        # Find the best match
        prompt_type = None
        for pattern, ptype in mappings.items():
            if pattern == "_default":
                continue
            if pattern in dataset_type.lower() or dataset_type.lower().startswith(pattern):
                prompt_type = ptype
                break
        
        # Use default if no match found
        if not prompt_type:
            prompt_type = mappings["_default"]
        
        prompt_config = self.config["evaluation"]["judge_prompts"].get(prompt_type)
        if not prompt_config:
            raise ValueError(f"Judge prompt type '{prompt_type}' not found in config")
            
        return prompt_config["template"]
    
    def call_llm_judge(self, question: str, correct_answer: str, response: str, dataset_type: str = None) -> Optional[str]:
        """
        Call LLM to judge the answer.
        
        Args:
            question: The original question
            correct_answer: The ground truth answer
            response: The model's predicted answer
            dataset_type: Type of dataset for prompt selection
            
        Returns:
            LLM judgment response or None if failed
        """
        if not self.llm_client:
            return None
            
        try:
            # Get appropriate judge prompt
            judge_prompt = self.get_judge_prompt(dataset_type or "base")
            
            # Format the prompt
            formatted_prompt = judge_prompt.format(
                question=question,
                correct_answer=correct_answer,
                response=response
            )
            
            # Call LLM
            llm_config = self.config["evaluation"]["llm_config"]
            
            # Build API call parameters, only include configured values
            api_params = {
                "model": llm_config["model"],
                "messages": [{"role": "user", "content": formatted_prompt}]
            }
            
            # Add optional parameters if configured
            if "temperature" in llm_config:
                api_params["temperature"] = llm_config["temperature"]
            if "max_tokens" in llm_config:
                api_params["max_tokens"] = llm_config["max_tokens"]
            if "timeout" in llm_config:
                api_params["timeout"] = llm_config["timeout"]
            
            with self.lock:
                completion = self.llm_client.chat.completions.create(**api_params)
            
            return completion.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Error in LLM judge call: {e}")
            return None
    
    def extract_judgment(self, llm_response: str, dataset_type: str = None) -> Tuple[str, Optional[str]]:
        """
        Extract judgment from LLM response.
        
        Args:
            llm_response: Raw LLM response
            dataset_type: Type of dataset for extraction method
            
        Returns:
            Tuple of (judgment, reasoning)
        """
        if not llm_response:
            return "UNKNOWN", None
            
        # For GAIA-style prompts
        if "gaia" in (dataset_type or "").lower():
            if "Correct" in llm_response:
                return "CORRECT", llm_response
            elif "Incorrect" in llm_response:
                return "INCORRECT", llm_response
            else:
                return "UNKNOWN", llm_response
        
        # For base/QA prompts (A/B/C format)
        if re.search(r'\bA\b', llm_response):
            return "CORRECT", llm_response
        elif re.search(r'\bB\b', llm_response):
            return "INCORRECT", llm_response
        elif re.search(r'\bC\b', llm_response):
            return "NOT_ATTEMPTED", llm_response
        
        # For browsecomp/medical prompts (yes/no format)
        if "correct: yes" in llm_response.lower():
            return "CORRECT", llm_response
        elif "correct: no" in llm_response.lower():
            return "INCORRECT", llm_response
        
        # Fallback: try to find explicit keywords
        response_lower = llm_response.lower()
        if "correct" in response_lower and "incorrect" not in response_lower:
            return "CORRECT", llm_response
        elif "incorrect" in response_lower:
            return "INCORRECT", llm_response
        elif "not_attempted" in response_lower or "not attempted" in response_lower:
            return "NOT_ATTEMPTED", llm_response
        
        return "UNKNOWN", llm_response
    
    def evaluate_single_item(self, item: Dict[str, Any], dataset_type: str = None) -> Dict[str, Any]:
        """
        Evaluate a single trajectory item.
        
        Args:
            item: Trajectory item with question, ground_truth, prediction
            dataset_type: Type of dataset
            
        Returns:
            Item with evaluation results added
        """
        result = item.copy()
        
        # Extract required fields
        question = item.get("question", "")
        # Try both ground_truth and answer fields for compatibility
        correct_answer = item.get("ground_truth", "") or item.get("answer", "")
        prediction = item.get("prediction", "")
        
        if not all([question, correct_answer, prediction]):
            result["evaluation"] = {
                "judgment": "UNKNOWN",
                "reasoning": "Missing required fields",
                "error": "Missing question, answer/ground_truth, or prediction"
            }
            return result
        
        # Check exact match first to avoid unnecessary LLM calls
        if self._exact_match(prediction, correct_answer):
            result["evaluation"] = {
                "judgment": "CORRECT",
                "reasoning": "Exact match with ground truth answer",
                "llm_response": "Skipped - exact match",
                "dataset_type": dataset_type,
                "prompt_type": self._get_prompt_type(dataset_type),
                "exact_match": True
            }
            return result
        
        # Call LLM judge
        llm_response = self.call_llm_judge(question, correct_answer, prediction, dataset_type)
        
        if not llm_response:
            result["evaluation"] = {
                "judgment": "UNKNOWN", 
                "reasoning": "LLM call failed",
                "error": "Failed to get LLM response"
            }
            return result
        
        # Extract judgment
        judgment, reasoning = self.extract_judgment(llm_response, dataset_type)
        
        result["evaluation"] = {
            "judgment": judgment,
            "reasoning": reasoning,
            "llm_response": llm_response,
            "dataset_type": dataset_type,
            "prompt_type": self._get_prompt_type(dataset_type),
            "exact_match": False  # LLM was used, so not exact match
        }
        
        return result
    
    def _exact_match(self, predicted: str, ground_truth: str) -> bool:
        """Check if predicted answer exactly matches ground truth answer."""
        if not predicted or not ground_truth:
            return False
        
        pred_clean = predicted.lower().strip()
        truth_clean = ground_truth.lower().strip()
        
        return pred_clean == truth_clean
    
    def _get_prompt_type(self, dataset_type: str) -> str:
        """Get the prompt type used for a dataset."""
        mappings = self.config["evaluation"]["dataset_mappings"]
        for pattern, ptype in mappings.items():
            if pattern == "_default":
                continue
            if pattern in (dataset_type or "").lower():
                return ptype
        return mappings["_default"]
    
    def evaluate_batch(self, items: List[Dict[str, Any]], dataset_type: str = None, max_workers: int = None) -> List[Dict[str, Any]]:
        """
        Evaluate a batch of trajectory items.
        
        Args:
            items: List of trajectory items
            dataset_type: Type of dataset
            max_workers: Number of parallel workers
            
        Returns:
            List of items with evaluation results
        """
        max_workers = max_workers or self.config["global"]["max_workers"]
        results = []
        
        if TQDM_AVAILABLE and self.config["global"]["enable_progress_bar"]:
            progress_bar = tqdm(total=len(items), desc="Evaluating")
        else:
            progress_bar = None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(self.evaluate_single_item, item, dataset_type): item 
                for item in items
            }
            
            # Collect results
            for future in as_completed(future_to_item):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if progress_bar:
                        progress_bar.update(1)
                        
                except Exception as e:
                    print(f"Error evaluating item: {e}")
                    # Add error result
                    item = future_to_item[future]
                    item["evaluation"] = {
                        "judgment": "UNKNOWN",
                        "reasoning": f"Evaluation failed: {str(e)}",
                        "error": str(e)
                    }
                    results.append(item)
                    
                    if progress_bar:
                        progress_bar.update(1)
        
        if progress_bar:
            progress_bar.close()
            
        return results
    
    def save_evaluation_results(self, items: List[Dict[str, Any]], output_dir: str, dataset_type: str = None) -> Dict[str, Any]:
        """
        Save evaluation results in the format compatible with evaluate_v2.py for frontend viewing.
        
        Args:
            items: Evaluated items
            output_dir: Output directory
            dataset_type: Dataset type
            
        Returns:
            Evaluation statistics
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Aggregate results by question (similar to evaluate_v2.py)
        question_results = defaultdict(lambda: {
            "question": "",
            "answer": "",
            "rollouts": [],
            "statistics": {}
        })
        
        for item in items:
            question = item.get("question", "")
            answer = item.get("answer", "")
            prediction = item.get("prediction", "")
            evaluation = item.get("evaluation", {})
            messages = item.get("messages", [])
            
            # Extract rollout information
            rollout_id = item.get("rollout", "1")
            
            # Set question and answer if not already set
            if not question_results[question]["question"]:
                question_results[question]["question"] = question
                question_results[question]["answer"] = answer
            
            # Detect warnings
            answer_warn = self.detect_answer_warnings(item)
            
            # Add rollout data
            rollout_data = {
                "rollout_id": str(rollout_id),
                "messages": messages,
                "prediction": prediction,
                "is_answer_correct": evaluation.get("judgment") == "CORRECT",
                "answer_warn": answer_warn,
                "judgement": evaluation.get("judgment", "UNKNOWN"),
                "llm_response_full": evaluation.get("llm_response", ""),
                "termination": item.get("termination", ""),
                "assistant_turns": self._count_assistant_turns(messages),
                "search_count": self._count_search_calls(messages),
                "read_count": self._count_read_calls(messages),
                "total_tool_calls": self._count_tool_calls(messages),
                "evaluation": evaluation
            }
            
            question_results[question]["rollouts"].append(rollout_data)
        
        # Convert to regular dict
        question_results = dict(question_results)
        
        # Calculate metrics
        pass_at_1_scores = {}
        all_rollouts = []
        for data in question_results.values():
            all_rollouts.extend(data["rollouts"])
        
        # Calculate individual rollout pass@1
        rollout_ids = set(r["rollout_id"] for r in all_rollouts)
        for rollout_id in sorted(rollout_ids):
            correct_count = 0
            total_count = 0
            for data in question_results.values():
                for rollout in data["rollouts"]:
                    if rollout["rollout_id"] == rollout_id:
                        total_count += 1
                        if rollout["is_answer_correct"]:
                            correct_count += 1
                        break
            
            if total_count > 0:
                pass_at_1_scores[f"Rollout{rollout_id}_Pass@1"] = round(correct_count / total_count * 100, 2)
        
        # Calculate pass@3
        pass_at_3 = 0
        if question_results:
            correct_questions = 0
            for data in question_results.values():
                rollouts = data["rollouts"][:3]  # Take first 3 rollouts
                if any(r["is_answer_correct"] for r in rollouts):
                    correct_questions += 1
            pass_at_3 = round(correct_questions / len(question_results) * 100, 2)
        
        # Calculate highest and average pass@1
        rollout_scores = list(pass_at_1_scores.values())
        highest_pass_at_1 = max(rollout_scores) if rollout_scores else 0
        average_pass_at_1 = round(sum(rollout_scores) / len(rollout_scores), 2) if rollout_scores else 0
        
        # Calculate warnings statistics
        total_warnings = sum(len(r["answer_warn"]) for r in all_rollouts)
        avg_warnings_per_rollout = round(total_warnings / len(all_rollouts), 2) if all_rollouts else 0
        
        # Count warning types
        warning_counts = defaultdict(int)
        for rollout in all_rollouts:
            for warning in rollout["answer_warn"]:
                warning_counts[warning] += 1
        
        top_warnings = sorted(warning_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Calculate termination rate
        answer_terminated = sum(1 for r in all_rollouts if r["termination"] == "answer")
        answer_termination_rate = round(answer_terminated / len(all_rollouts) * 100, 2) if all_rollouts else 0
        
        # Prepare evaluation results
        evaluation_results = {
            "metadata": {
                "dataset_type": dataset_type or "unknown",
                "evaluation_time": datetime.now().isoformat(),
                "total_questions": len(question_results),
                "total_rollouts": len(all_rollouts)
            },
            "metrics": {
                "Highest_Pass@1": highest_pass_at_1,
                "Pass@3": pass_at_3,
                "Average_Pass@1": average_pass_at_1,
                **pass_at_1_scores
            },
            "statistics": {
                "total_rollouts": len(all_rollouts),
                "correct_answers": sum(1 for r in all_rollouts if r["is_answer_correct"]),
                "overall_accuracy": round(sum(1 for r in all_rollouts if r["is_answer_correct"]) / len(all_rollouts) * 100, 2) if all_rollouts else 0,
                "answer_termination_rate": answer_termination_rate,
                "avg_assistant_turns": round(sum(r["assistant_turns"] for r in all_rollouts) / len(all_rollouts), 2) if all_rollouts else 0,
                "avg_search_count": round(sum(r["search_count"] for r in all_rollouts) / len(all_rollouts), 2) if all_rollouts else 0,
                "avg_read_count": round(sum(r["read_count"] for r in all_rollouts) / len(all_rollouts), 2) if all_rollouts else 0,
                "avg_total_tool_calls": round(sum(r["total_tool_calls"] for r in all_rollouts) / len(all_rollouts), 2) if all_rollouts else 0,
                "total_warnings": total_warnings,
                "avg_warnings_per_rollout": avg_warnings_per_rollout,
                "top_warnings": top_warnings
            },
            "question_results": question_results
        }
        
        # Save files (compatible with evaluate_v2.py and frontend)
        
        # 1. Comprehensive results
        results_file = output_dir / "evaluation_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation_results, f, ensure_ascii=False, indent=2)
        
        # 2. Question-rollout pairs (for frontend)
        question_rollouts_file = output_dir / "question_rollouts.jsonl"
        with open(question_rollouts_file, 'w', encoding='utf-8') as f:
            for question, data in question_results.items():
                record = {
                    "question": data["question"],
                    "answer": data["answer"],
                    "rollouts": data["rollouts"]
                }
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        
        # 3. Summary (for quick overview)
        summary_file = output_dir / "evaluation_summary.json"
        summary = {
            "metadata": evaluation_results["metadata"],
            "metrics": evaluation_results["metrics"],
            "statistics": evaluation_results["statistics"]
        }
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 4. Intermediate results (temporary, for consistency with evaluate_v2.py - will be cleaned up)
        intermediate_file = output_dir / "intermediate_results.jsonl"
        with open(intermediate_file, 'w', encoding='utf-8') as f:
            # Convert rollouts back to individual items for intermediate format
            for question, data in question_results.items():
                for rollout in data["rollouts"]:
                    intermediate_item = {
                        "question": data["question"],
                        "answer": data["answer"],
                        "rollout_id": rollout["rollout_id"],
                        "messages": rollout["messages"],
                        "prediction": rollout["prediction"],
                        "is_answer_correct": rollout["is_answer_correct"],
                        "answer_warn": rollout["answer_warn"],
                        "judgement": rollout["judgement"],
                        "llm_response_full": rollout["llm_response_full"],
                        "termination": rollout["termination"],
                        "assistant_turns": rollout["assistant_turns"],
                        "search_count": rollout["search_count"],
                        "read_count": rollout["read_count"],
                        "total_tool_calls": rollout["total_tool_calls"]
                    }
                    f.write(json.dumps(intermediate_item, ensure_ascii=False) + '\n')
        
        # Return simple stats for backward compatibility
        stats = {
            "total_items": len(items),
            "processed_items": len([item for item in items if item.get("evaluation", {}).get("judgment") != "UNKNOWN"]),
            "total": len(items),
            "correct": sum(1 for item in items if item.get("evaluation", {}).get("judgment") == "CORRECT"),
            "incorrect": sum(1 for item in items if item.get("evaluation", {}).get("judgment") == "INCORRECT"),
            "not_attempted": sum(1 for item in items if item.get("evaluation", {}).get("judgment") == "NOT_ATTEMPTED"),
            "unknown": sum(1 for item in items if item.get("evaluation", {}).get("judgment") == "UNKNOWN"),
            "accuracy": 0,
            "success_rate": 0
        }
        
        if stats["total"] > 0:
            stats["accuracy"] = stats["correct"] / stats["total"]
            stats["success_rate"] = (stats["correct"] + stats["incorrect"]) / stats["total"]
        
        return stats
    
    def _count_assistant_turns(self, messages: List[Dict[str, Any]]) -> int:
        """Count assistant turns in messages."""
        return sum(1 for msg in messages if msg.get("role") == "assistant")
    
    def _count_tool_calls(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tool calls in messages."""
        tool_call_count = 0
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                tool_call_count += len(re.findall(r'<tool_call>', content))
        return tool_call_count
    
    def _count_search_calls(self, messages: List[Dict[str, Any]]) -> int:
        """Count search tool calls in messages."""
        search_count = 0
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "<tool_call>" in content and "</tool_call>" in content:
                    try:
                        tool_call_str = content.split("<tool_call>")[1].split("</tool_call>")[0].strip()
                        tool_call = json.loads(tool_call_str)
                        if tool_call.get("name") == "search":
                            search_count += 1
                    except (json.JSONDecodeError, IndexError):
                        pass
        return search_count
    
    def _count_read_calls(self, messages: List[Dict[str, Any]]) -> int:
        """Count read tool calls in messages."""
        read_count = 0
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "<tool_call>" in content and "</tool_call>" in content:
                    try:
                        tool_call_str = content.split("<tool_call>")[1].split("</tool_call>")[0].strip()
                        tool_call = json.loads(tool_call_str)
                        if tool_call.get("name") == "read":
                            read_count += 1
                    except (json.JSONDecodeError, IndexError):
                        pass
        return read_count
    
    def evaluate_file(self, input_file: str, output_file: str, dataset_type: str = None) -> Dict[str, Any]:
        """
        Evaluate trajectories from a JSONL file.
        
        Args:
            input_file: Input JSONL file path
            output_file: Output JSONL file path or output directory
            dataset_type: Type of dataset for prompt selection
            
        Returns:
            Evaluation statistics
        """
        # Determine output directory
        output_path = Path(output_file)
        if output_path.suffix != '.jsonl':
            # If no .jsonl extension, treat as directory
            output_dir = output_path
        else:
            # If .jsonl extension, create evaluation_results in parent directory
            output_dir = output_path.parent / "evaluation_results"
        
        # Load data
        items = []
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        items.append(json.loads(line))
        except Exception as e:
            raise ValueError(f"Error loading input file {input_file}: {e}")
        
        print(f"Loaded {len(items)} items from {input_file}")
        
        # Evaluate
        evaluated_items = self.evaluate_batch(items, dataset_type)
        
        # Save comprehensive results in evaluation_results format (compatible with evaluate_v2.py)
        stats = self.save_evaluation_results(evaluated_items, str(output_dir), dataset_type)
        
        print(f"Evaluation completed. Results saved to {output_dir}")
        print(f"Statistics: {stats}")
        
        return stats 

    def detect_answer_warnings(self, record: Dict[str, Any]) -> List[str]:
        """Detect various issues in the conversation and tool usage."""
        warnings = []
        messages = record.get("messages", [])
        termination = record.get("termination", "")
        
        if not messages:
            return ["No messages found"]
        
        # Check termination status
        if termination != "answer":
            if termination:
                warnings.append(f"Non-standard termination: '{termination}' (not 'answer')")
            else:
                warnings.append("Missing termination status")
        
        # Track searches to detect duplicates
        search_queries = []
        read_urls = []
        first_user = True
        
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "assistant":
                # Check for tool call format issues
                if "<tool_call>" in content and "</tool_call>" in content:
                    try:
                        tool_call_str = content.split("<tool_call>")[1].split("</tool_call>")[0].strip()
                        tool_call = json.loads(tool_call_str)
                        tool_name = tool_call.get("name", "")
                        tool_args = tool_call.get("arguments", {})
                        
                        if tool_name == "search":
                            query = tool_args.get("query", [])
                            if isinstance(query, list):
                                for q in query:
                                    if q.lower() in [sq.lower() for sq in search_queries]:
                                        warnings.append(f"Duplicate search query detected: '{q}'")
                                    search_queries.append(q)
                            else:
                                warnings.append("Search query should be an array")
                        
                        elif tool_name == "read":
                            url = tool_args.get("url", [])
                            if isinstance(url, list):
                                for u in url:
                                    if u in read_urls:
                                        warnings.append(f"Duplicate read URL detected: '{u}'")
                                    read_urls.append(u)
                            elif isinstance(url, str):
                                if url in read_urls:
                                    warnings.append(f"Duplicate read URL detected: '{url}'")
                                read_urls.append(url)
                            
                            # Check if goal is provided
                            if not tool_args.get("goal"):
                                warnings.append("Read tool call missing goal parameter")
                        
                    except (json.JSONDecodeError, IndexError, KeyError):
                        warnings.append("Invalid tool call JSON format")
            
            elif role == "user" and not first_user:  # Skip first user message
                # Check tool response format
                if content.startswith("<tool_response>") and content.endswith("</tool_response>"):
                    response_content = content[len("<tool_response>"):-len("</tool_response>")].strip()
                    
                    # Check for proper tool response format
                    if not response_content:
                        warnings.append("Empty tool response")
                    elif any(error_pattern in content.lower() for error_pattern in ["[|search|]", "[|read|]", "[|med_proprietary|]"]):
                        warnings.append("Tool response contains error")
                elif "<tool_response>" in content or "</tool_response>" in content:
                    warnings.append("Malformed tool response tags")
            elif role == "user" and first_user:
                first_user = False
        
        # Check final answer format
        final_msg = messages[-1].get("content", "") if messages else ""
        if messages and messages[-1].get("role") == "assistant":
            if "<answer>" not in final_msg or "</answer>" not in final_msg:
                warnings.append("Missing proper answer format")
            else:
                try:
                    answer_content = final_msg.split("<answer>")[1].split("</answer>")[0].strip()
                    if not answer_content:
                        warnings.append("Empty answer content")
                except (IndexError, AttributeError):
                    warnings.append("Malformed answer tags")
        
        return warnings 