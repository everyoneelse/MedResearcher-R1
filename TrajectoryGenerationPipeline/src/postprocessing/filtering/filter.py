#!/usr/bin/env python3
"""
Trajectory filtering module for quality control.
"""

import json
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from transformers import AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Error: transformers not available, please install: pip install transformers")

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class TrajectoryFilter:
    """
    Trajectory filter for quality control and rejection sampling.
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize the filter.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "..", "config.json")
        self.config = self._load_config()
        self.encoding = self._init_tokenizer()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
    
    def _init_tokenizer(self):
        """Initialize tokenizer for token counting."""
        tokenizer_config = self.config.get("tokenizer", {})
        tokenizer_type = tokenizer_config.get("type", "custom")
        
        if tokenizer_type == "custom" and TRANSFORMERS_AVAILABLE:
            tokenizer_path = tokenizer_config.get("path")
            if not tokenizer_path:
                raise ValueError("Tokenizer path must be specified in config.json")
            
            if not os.path.exists(tokenizer_path):
                raise FileNotFoundError(f"Tokenizer path does not exist: {tokenizer_path}")
            
            try:
                print(f"Loading custom tokenizer from: {tokenizer_path}")
                return AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
            except Exception as e:
                raise RuntimeError(f"Failed to load tokenizer: {e}")
        
        elif tokenizer_type == "tiktoken":
            # tiktoken is no longer supported, use transformers instead
            raise ValueError("tiktoken tokenizer type is deprecated, please use 'custom' type with transformers tokenizer path")
        
        else:
            raise ValueError(f"Unsupported tokenizer type: {tokenizer_type} or required libraries not available")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using transformers tokenizer."""
        try:
            # transformers tokenizer
            tokens = self.encoding.encode(text)
            return len(tokens)
        except Exception as e:
            # This should not happen with proper tokenizer setup
            raise RuntimeError(f"Tokenizer encoding failed: {e}")
    
    def count_trajectory_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Count total tokens in trajectory messages."""
        total_tokens = 0
        for message in messages:
            content = message.get("content", "")
            total_tokens += self.count_tokens(content)
        return total_tokens
    
    def count_function_calls(self, messages: List[Dict[str, Any]]) -> int:
        """Count number of function calls in trajectory."""
        function_call_count = 0
        for message in messages:
            if message.get("role") == "assistant":
                content = message.get("content", "")
                # Count <tool_call> tags
                function_call_count += len(re.findall(r'<tool_call>', content))
        return function_call_count
    
    def validate_tool_responses(self, messages: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validate that all tool calls have valid responses.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        tool_call_count = 0
        tool_response_count = 0
        tool_used = True
        for i, message in enumerate(messages):
            content = message.get("content", "")
            role = message.get("role", "")
            
            if role == "assistant":
                # Count tool calls
                tool_calls = re.findall(r'<tool_call>', content)
                tool_call_count += len(tool_calls)
                if tool_used:
                    tool_used = False
                else:
                    errors.append(
                        f"Tool call/response error: last assistant has no tool call")
                
            elif role == "user":
                # Count tool responses (should match previous tool calls)
                tool_responses = re.findall(r'<tool_response>', content)
                tool_response_count += len(tool_responses)
                if not tool_used:
                    tool_used = True

        # Check for error messages in tool responses
        for message in messages:
            if message.get("role") == "user" and "<tool_response>" in message.get("content", ""):
                content = message["content"]
                # Look for common error patterns
                if any(error_pattern in content.lower() for error_pattern in 
                       ["[|search|]", "[|read|]", "[|med_proprietary|]"]):
                    # Check if it's a legitimate "not found" result vs an error
                        errors.append(f"Tool response contains error: {content[:100]}...")
        
        return len(errors) == 0, errors
    
    def validate_answer_format(self, messages: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validate that trajectory has proper answer format.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        has_final_answer = False
        
        # Check the last assistant message for answer tags
        for message in reversed(messages):
            if message.get("role") == "assistant":
                content = message.get("content", "")
                if "<answer>" in content and "</answer>" in content:
                    has_final_answer = True
                    # Check if answer is not empty
                    answer_match = re.search(r'<answer>\s*(.*?)\s*</answer>', content, re.DOTALL)
                    if answer_match:
                        answer_content = answer_match.group(1).strip()
                        if not answer_content:
                            errors.append("Answer tag is empty")
                    else:
                        errors.append("Answer tag format is invalid")
                break
        
        if not has_final_answer:
            errors.append("No final answer found in trajectory")
        
        return len(errors) == 0, errors
    
    def validate_single_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate a single trajectory item against filtering criteria.
        
        Args:
            item: Trajectory item to validate
            
        Returns:
            Item with validation results added
        """
        result = item.copy()
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "metrics": {}
        }
        
        messages = item.get("messages", [])
        if not messages:
            validation_result["is_valid"] = False
            validation_result["errors"].append("No messages in trajectory")
            result["filtering"] = validation_result
            return result
        
        criteria = self.config["filtering"]["criteria"]
        
        # 1. Check minimum turns (skip if -1)
        if criteria["min_turns"] != -1:
            assistant_messages = [m for m in messages if m.get("role") == "assistant"]
            if len(assistant_messages) < criteria["min_turns"]:
                validation_result["is_valid"] = False
                validation_result["errors"].append(f"Too few turns: {len(assistant_messages)} < {criteria['min_turns']}")
        
        # 2. Check token length (skip if -1)
        total_tokens = self.count_trajectory_tokens(messages)
        validation_result["metrics"]["total_tokens"] = total_tokens
        if criteria["max_token_length"] != -1 and total_tokens > criteria["max_token_length"]:
            validation_result["is_valid"] = False
            validation_result["errors"].append(f"Token limit exceeded: {total_tokens} > {criteria['max_token_length']}")
        
        # 3. Check function call count (skip if -1)
        function_call_count = self.count_function_calls(messages)
        validation_result["metrics"]["function_calls"] = function_call_count
        if criteria["max_function_calls"] != -1 and function_call_count > criteria["max_function_calls"]:
            validation_result["warnings"].append(f"High function call count: {function_call_count}")
        
        # 4. Validate tool responses (only if required)
        if criteria["require_valid_tool_responses"]:
            tool_valid, tool_errors = self.validate_tool_responses(messages)
            if not tool_valid:
                validation_result["is_valid"] = False
                validation_result["errors"].extend(tool_errors)
        
        # 5. Validate answer format (only if required)
        if criteria["require_final_answer"]:
            answer_valid, answer_errors = self.validate_answer_format(messages)
            if not answer_valid:
                validation_result["is_valid"] = False
                validation_result["errors"].extend(answer_errors)
        
        # 6. Check evaluation results if available
        evaluation = item.get("evaluation", {})
        if evaluation:
            judgment = evaluation.get("judgment", "UNKNOWN")
            validation_result["metrics"]["evaluation_judgment"] = judgment
            
            # Filter based on evaluation results if required
            if criteria["require_correct_evaluation"]:
                if judgment != "CORRECT":
                    validation_result["is_valid"] = False
                    validation_result["errors"].append(f"Evaluation judgment is not CORRECT: {judgment}")
        
        elif criteria["require_correct_evaluation"]:
            # If evaluation is required but not present
            validation_result["is_valid"] = False
            validation_result["errors"].append("Evaluation result required but not found")
        
        result["filtering"] = validation_result
        return result
    
    def filter_batch(self, items: List[Dict[str, Any]], max_workers: int = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Filter a batch of trajectory items.
        
        Args:
            items: List of trajectory items
            max_workers: Number of parallel workers
            
        Returns:
            Tuple of (filtered_items, filtering_stats)
        """
        max_workers = max_workers or self.config["global"]["max_workers"]
        validated_items = []
        
        if TQDM_AVAILABLE and self.config["global"]["enable_progress_bar"]:
            progress_bar = tqdm(total=len(items), desc="Filtering")
        else:
            progress_bar = None
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(self.validate_single_item, item): item 
                for item in items
            }
            
            # Collect results
            for future in as_completed(future_to_item):
                try:
                    result = future.result()
                    validated_items.append(result)
                    
                    if progress_bar:
                        progress_bar.update(1)
                        
                except Exception as e:
                    print(f"Error validating item: {e}")
                    item = future_to_item[future]
                    item["filtering"] = {
                        "is_valid": False,
                        "errors": [f"Validation failed: {str(e)}"],
                        "warnings": [],
                        "metrics": {}
                    }
                    validated_items.append(item)
                    
                    if progress_bar:
                        progress_bar.update(1)
        
        if progress_bar:
            progress_bar.close()
        
        # Filter valid items
        valid_items = [item for item in validated_items if item.get("filtering", {}).get("is_valid", False)]
        
        # Calculate statistics
        stats = self._calculate_filtering_stats(validated_items, valid_items)
        
        return valid_items, stats
    
    def _calculate_filtering_stats(self, all_items: List[Dict[str, Any]], valid_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate filtering statistics."""
        total = len(all_items)
        valid = len(valid_items)
        
        stats = {
            "total_items": total,
            "valid_items": valid,
            "filtered_out": total - valid,
            "pass_rate": valid / total if total > 0 else 0,
            "error_breakdown": {},
            "metrics_summary": {
                "avg_tokens": 0,
                "avg_function_calls": 0,
                "max_tokens": 0,
                "max_function_calls": 0
            }
        }
        
        # Analyze errors
        error_counts = {}
        token_counts = []
        function_call_counts = []
        
        for item in all_items:
            filtering_result = item.get("filtering", {})
            errors = filtering_result.get("errors", [])
            metrics = filtering_result.get("metrics", {})
            
            # Count errors
            for error in errors:
                error_type = error.split(":")[0] if ":" in error else error
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
            
            # Collect metrics
            if "total_tokens" in metrics:
                token_counts.append(metrics["total_tokens"])
            if "function_calls" in metrics:
                function_call_counts.append(metrics["function_calls"])
        
        stats["error_breakdown"] = error_counts
        
        if token_counts:
            stats["metrics_summary"]["avg_tokens"] = sum(token_counts) / len(token_counts)
            stats["metrics_summary"]["max_tokens"] = max(token_counts)
        
        if function_call_counts:
            stats["metrics_summary"]["avg_function_calls"] = sum(function_call_counts) / len(function_call_counts)
            stats["metrics_summary"]["max_function_calls"] = max(function_call_counts)
        
        return stats
    
    def filter_file(self, input_file: str, output_file: str) -> Dict[str, Any]:
        """
        Filter trajectories from a JSONL file.
        
        Args:
            input_file: Input JSONL file path
            output_file: Output JSONL file path for valid trajectories
            
        Returns:
            Filtering statistics
        """
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
        
        # Filter
        valid_items, stats = self.filter_batch(items)
        
        # Save valid results
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in valid_items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        print(f"Filtering completed. {len(valid_items)}/{len(items)} items passed.")
        print(f"Results saved to {output_file}")
        print(f"Statistics: {stats}")
        
        return stats 