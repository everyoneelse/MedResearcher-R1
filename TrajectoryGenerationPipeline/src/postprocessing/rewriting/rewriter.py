#!/usr/bin/env python3
"""
Think content rewriter for improved training data.
"""

import json
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    from transformers import AutoTokenizer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Error: transformers not available, please install: pip install transformers")

from .rewrite_prompts import RewritePrompts


class ThinkRewriter:
    """Think content rewriter for trajectory optimization."""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "..", "config.json")
        self.config = self._load_config()
        self.llm_client = self._init_llm_client()
        self.lock = threading.Lock()
        self.encoding = self._init_tokenizer()
        
    def _load_config(self) -> Dict[str, Any]:
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _init_llm_client(self) -> Optional[OpenAI]:
        if not OPENAI_AVAILABLE:
            return None
        
        # Get API configuration from config
        llm_config = self.config["rewriting"]["llm_config"]
        api_key_env = llm_config.get("api_key_env", "OPENAI_API_KEY")
        api_base = llm_config.get("api_base", "https://api.openai.com/v1")
        
        api_key = os.getenv(api_key_env)
        if not api_key:
            print(f"Warning: {api_key_env} not found, rewriting will be disabled")
            return None
        
        return OpenAI(api_key=api_key, base_url=api_base)
    
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
    
    def detect_language(self, text: str) -> str:
        return "zh" if re.search(r'[\u4e00-\u9fff]', text) else "en"
    
    def rewrite_think_content(self, original_think: str, question: str, history_text: str, 
                             current_action: str, language: str = None, is_final_answer: bool = False) -> Optional[str]:
        """Rewrite think content using LLM."""
        if not self.llm_client:
            return None
            
        language = language or self.detect_language(question + original_think)
        max_retries = self.config["rewriting"]["rewrite_config"]["max_retries"]
        
        # Use unified prompt management
        if is_final_answer:
            if language == "zh":
                prompt = RewritePrompts.get_answer_prompt_zh(question, history_text, original_think, current_action)
            else:
                prompt = RewritePrompts.get_answer_prompt_en(question, history_text, original_think, current_action)
        else:
            if language == "zh":
                prompt = RewritePrompts.get_tool_call_prompt_zh(question, history_text, original_think, current_action)
            else:
                prompt = RewritePrompts.get_tool_call_prompt_en(question, history_text, original_think, current_action)
        
        # Try rewriting with retries
        for attempt in range(max_retries):
            try:
                llm_config = self.config["rewriting"]["llm_config"]
                
                # Build API call parameters, only include configured values
                api_params = {
                    "model": llm_config["model"],
                    "messages": [{"role": "user", "content": prompt}]
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
                
                rewritten = completion.choices[0].message.content.strip()
                
                # Validate rewritten content
                if self._validate_rewritten_content(rewritten, original_think):
                    return rewritten
                    
            except Exception as e:
                print(f"Rewrite attempt {attempt + 1} failed: {e}")
                
        return None
    
    def _validate_rewritten_content(self, rewritten: str, original: str) -> bool:
        """Validate rewritten content meets requirements."""
        # Check forbidden content and minimum length
        if (len(rewritten.strip()) < 10 or
            any(tag in rewritten for tag in ['<tool_call>', '<think>', '<answer>', '<tool_response>'])):
            return False
        return True
    
    def rewrite_trajectory(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Rewrite think contents in a trajectory."""
        result = item.copy()
        messages = result.get("messages", [])
        
        if not messages:
            return result
        
        question = item.get("question", "")
        language = self.detect_language(question)
        simplified_history = []
        rewrite_stats = {"total_thinks": 0, "rewritten_thinks": 0, "failed_rewrites": 0, "compression_ratios": []}
        
        # Process each assistant message
        for i, message in enumerate(messages):
            if message.get("role") != "assistant":
                continue
                
            content = message.get("content", "")
            think_matches = list(re.finditer(r'<think>(.*?)</think>', content, re.DOTALL))
            if not think_matches:
                continue
            
            new_content = content
            offset = 0
            
            for match in think_matches:
                rewrite_stats["total_thinks"] += 1
                original_think = match.group(1).strip()
                
                # Determine current action
                remaining_content = content[match.end():]
                current_action = ""
                is_final_answer = False
                
                if "<tool_call>" in remaining_content:
                    tool_call_match = re.search(r'<tool_call>(.*?)</tool_call>', remaining_content, re.DOTALL)
                    if tool_call_match:
                        current_action = tool_call_match.group(1).strip()
                elif "<answer>" in remaining_content:
                    answer_match = re.search(r'<answer>(.*?)</answer>', remaining_content, re.DOTALL)
                    if answer_match:
                        current_action = answer_match.group(1).strip()
                        is_final_answer = True
                
                # Rewrite think content
                history_text = "\n".join(simplified_history)
                rewritten_think = self.rewrite_think_content(
                    original_think=original_think,
                    question=question,
                    history_text=history_text,
                    current_action=current_action,
                    language=language,
                    is_final_answer=is_final_answer
                )
                
                if rewritten_think:
                    # Replace in content
                    start_pos = match.start(1) + offset
                    end_pos = match.end(1) + offset
                    new_content = new_content[:start_pos] + rewritten_think + new_content[end_pos:]
                    offset += len(rewritten_think) - len(original_think)
                    
                    simplified_history.append(rewritten_think)
                    rewrite_stats["rewritten_thinks"] += 1
                    
                    # Calculate compression ratio
                    original_tokens = self.count_tokens(original_think)
                    rewritten_tokens = self.count_tokens(rewritten_think)
                    if original_tokens > 0:
                        rewrite_stats["compression_ratios"].append(rewritten_tokens / original_tokens)
                else:
                    simplified_history.append(original_think)
                    rewrite_stats["failed_rewrites"] += 1
            
            messages[i]["content"] = new_content
        
        result["rewriting"] = rewrite_stats
        if rewrite_stats["compression_ratios"]:
            result["rewriting"]["avg_compression_ratio"] = sum(rewrite_stats["compression_ratios"]) / len(rewrite_stats["compression_ratios"])
        
        return result
    
    def rewrite_file(self, input_file: str, output_file: str) -> Dict[str, Any]:
        """Rewrite think contents in trajectories from a JSONL file."""
        # Load data
        items = []
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    items.append(json.loads(line))
        
        print(f"Loaded {len(items)} items from {input_file}")
        
        # Process items
        results = []
        for item in (tqdm(items, desc="Rewriting") if TQDM_AVAILABLE else items):
            try:
                result = self.rewrite_trajectory(item)
                results.append(result)
            except Exception as e:
                print(f"Error rewriting item: {e}")
                item["rewriting"] = {"error": str(e), "total_thinks": 0, "rewritten_thinks": 0, "failed_rewrites": 1}
                results.append(item)
        
        # Save results
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for item in results:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # Calculate statistics
        stats = self._calculate_rewrite_stats(results)
        print(f"Rewriting completed. Results saved to {output_file}")
        print(f"Statistics: {stats}")
        return stats
    
    def _calculate_rewrite_stats(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate rewriting statistics."""
        total_items = len(items)
        total_thinks = sum(item.get("rewriting", {}).get("total_thinks", 0) for item in items)
        rewritten_thinks = sum(item.get("rewriting", {}).get("rewritten_thinks", 0) for item in items)
        failed_rewrites = sum(item.get("rewriting", {}).get("failed_rewrites", 0) for item in items)
        
        compression_ratios = []
        for item in items:
            ratios = item.get("rewriting", {}).get("compression_ratios", [])
            compression_ratios.extend(ratios)
        
        return {
            "total_items": total_items,
            "total_thinks": total_thinks,
            "rewritten_thinks": rewritten_thinks,
            "failed_rewrites": failed_rewrites,
            "success_rate": rewritten_thinks / total_thinks if total_thinks > 0 else 0,
            "avg_compression_ratio": sum(compression_ratios) / len(compression_ratios) if compression_ratios else 0
        } 