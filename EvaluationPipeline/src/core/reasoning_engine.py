#!/usr/bin/env python3
"""
Reasoning Engine - Model inference and tool calling system
"""

import json
import os
import sys
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from openai import OpenAI

# Add tools path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
tools_path = os.path.join(project_root, 'tools')

if os.path.exists(tools_path):
    sys.path.insert(0, tools_path)
    sys.path.insert(0, project_root)
    from tools import create_tool_manager
else:
    raise ImportError(f"Tools path not found: {tools_path}")

# Add TrajectoryGenerationPipeline path for prompts
trajectory_path = os.path.join(project_root, 'TrajectoryGenerationPipeline', 'src')
if os.path.exists(trajectory_path):
    sys.path.insert(0, trajectory_path)
    from trajectory_generation.prompts import build_training_system_prompt, build_training_user_prompt
else:
    raise ImportError(f"TrajectoryGenerationPipeline path not found: {trajectory_path}")

logger = logging.getLogger(__name__)

# 屏蔽第三方库的冗余日志（强制性设置）
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
        logger.propagate = False  # 防止向上传播

# 立即执行日志静默设置
setup_logging_silence()


class LLMClient:
    """LLM client for model inference"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_base = config.get('api_base')
        
        # Get API key from environment variable or direct config
        api_key_env = config.get('api_key_env')
        if api_key_env:  # 如果api_key_env不为空，从环境变量读取
            self.api_key = os.getenv(api_key_env)
        elif api_key_env == "":  # 如果api_key_env为空字符串，直接使用空key
            self.api_key = ""
        else:  # 如果没有api_key_env字段，从api_key字段读取
            self.api_key = config.get('api_key')  # Fallback to direct key
        
        self.model = config.get('model')
        self.temperature = config.get('temperature', 0.3)
        self.max_retries = config.get('max_retries', 3)
        
        # 只有在api_key_env不为空字符串且api_key为空或默认值时才报错
        if api_key_env != "" and (not self.api_key or self.api_key == "your-llm-api-key"):
            raise ValueError("Please set correct API key in config (llm.api_key_env)")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )
        
        logger.debug(f"LLM client initialized: {self.model}")
    
    def call(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Call LLM with optional stop words"""
        call_params = {
            'model': self.model,
            'messages': messages,
            'temperature': kwargs.get('temperature', self.temperature),
        }
        
        # Add stop words if provided
        stop_words = kwargs.get('stop', [])
        if stop_words:
            call_params['stop'] = stop_words
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(**call_params)
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise
        
        return ""





class ReasoningAgent:
    """Reasoning agent for question inference"""
    
    def __init__(self, llm_client: LLMClient, tool_manager, config: Dict[str, Any]):
        self.llm_client = llm_client
        self.tool_manager = tool_manager
        self.config = config
        self.max_llm_calls = config.get('max_llm_calls', 30)
        self.max_token_length = config.get('max_token_length', 31744)
        self.verbose = config.get('verbose', False)  # 添加verbose控制参数
        
        # Initialize tokenizer for token counting
        self.tokenizer = self._init_tokenizer()
        
        logger.debug(f"Reasoning agent initialized: max_calls={self.max_llm_calls}, max_tokens={self.max_token_length}, verbose={self.verbose}")
    
    def _init_tokenizer(self):
        """Initialize tokenizer for token counting"""
        try:
            from transformers import AutoTokenizer
            
            # Try to load tokenizer from common paths
            tokenizer_paths = [
                os.path.join(project_root, 'TrajectoryGenerationPipeline', 'tokenizers', 'Qwen2_5_32B'),
                os.path.join(project_root, 'tokenizers', 'Qwen2_5_32B'),
                'TrajectoryGenerationPipeline/tokenizers/Qwen2_5_32B'
            ]
            
            for path in tokenizer_paths:
                if os.path.exists(path):
                    try:
                        return AutoTokenizer.from_pretrained(path)
                    except:
                        continue
            
            logger.warning("Could not load local tokenizer, will use character estimation")
            return None
            
        except Exception as e:
            logger.warning(f"Tokenizer initialization failed: {e}")
            return None
        
    def run(self, question: str) -> Dict[str, Any]:
        """Run reasoning process"""
        start_time = datetime.now()
        messages = []  # 初始化messages，确保异常处理时可用
        
        try:
            system_prompt = build_training_system_prompt()
            enabled_tools = ["search", "visit"]
            user_prompt_template = build_training_user_prompt(self.tool_manager, enabled_tools)
            
            logger.debug("Starting reasoning process")
            logger.debug(f"Question: {question}")
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt_template + question}
            ]
            
            num_llm_calls_available = self.max_llm_calls
            round_count = 0
            tool_calls = 0
            last_tool_call = None
            
            while num_llm_calls_available > 0:
                round_count += 1
                num_llm_calls_available -= 1
                
                if self.verbose:
                    print(f"\n🤖 第{round_count}轮推理 (剩余调用次数: {num_llm_calls_available})")
                    print("=" * 60)
                
                logger.debug(f"Round {round_count} (remaining: {num_llm_calls_available})")
                
                # Check token count before LLM call
                token_count = self._estimate_token_count(messages)
                if self.verbose:
                    print(f"📊 当前token数量: {token_count}")
                logger.debug(f"Current token count: {token_count}")
                
                if token_count > self.max_token_length:
                    logger.warning(f"Token limit exceeded: {token_count} > {self.max_token_length}")
                    
                    force_answer_msg = "You have now reached the maximum context length you can handle. You should stop making tool calls and, based on all the information above, think again and provide what you consider the most likely answer in the following format:<think>your final thinking</think>\n<answer>your answer</answer>"
                    
                    messages[-1] = {"role": "user", "content": force_answer_msg}
                    final_response = self.llm_client.call(messages)
                    messages.append({"role": "assistant", "content": final_response.strip()})
                    
                    logger.debug("Forced answer due to token limit")
                    # 设置特殊的termination标识
                    termination = "exceed_token_length"
                    break
                
                # Call LLM with stop word
                response = self.llm_client.call(messages, stop=['<tool_response>', '\n<tool_response>'])
                
                if self.verbose:
                    print(f"\n💭 模型返回:")
                    print("-" * 40)
                    # 显示模型响应，但限制长度
                    display_response = response[:800] if len(response) <= 800 else response[:800] + f"\n... [响应过长，共{len(response)}字符，已截断显示]"
                    print(display_response)
                
                logger.debug(f"LLM response: {response[:200]}{'...' if len(response) > 200 else ''}")
                
                # Check if response was stopped by tool_response (indicates tool call)
                if '<tool_call>' in response and '</tool_call>' in response:
                    # Add the partial response (with tool call) to messages
                    messages.append({"role": "assistant", "content": response.strip()})
                    
                    try:
                        tool_call_str = response.split('<tool_call>')[1].split('</tool_call>')[0]
                        tool_call_parsed = json.loads(tool_call_str)
                        tool_name = tool_call_parsed.get('name')
                        tool_args = tool_call_parsed.get('arguments')
                        
                        if self.verbose:
                            print(f"\n🛠️  工具调用:")
                            print("-" * 40)
                            print(f"工具名称: {tool_name}")
                            print(f"调用参数: {json.dumps(tool_args, ensure_ascii=False, indent=2)}")
                        
                        logger.debug(f"Tool call: {tool_name} - {tool_args}")
                        
                        # Tool loop detection
                        current_tool_call = {"name": tool_name, "arguments": tool_args}
                        if last_tool_call is not None and current_tool_call == last_tool_call:
                            logger.warning("Tool loop detected, terminating")
                            
                            end_time = datetime.now()
                            duration = (end_time - start_time).total_seconds()
                            
                            return {
                                "messages": messages,
                                "final_response": "Tool loop detected",
                                "prediction": "Tool loop detected",
                                "tool_calls": tool_calls,
                                "duration": duration,
                                "termination": "tool_loop_detected",
                                "start_time": start_time.isoformat(),
                                "end_time": end_time.isoformat()
                            }
                        
                        last_tool_call = current_tool_call
                        tool_calls += 1
                        
                        # Execute tool call
                        tool_response = self._handle_tool_call(tool_name, tool_args)
                        
                        if self.verbose:
                            print(f"\n🔧 工具返回:")
                            print("-" * 40)
                            # 显示工具响应，但限制长度
                            if len(tool_response) > 600:
                                display_tool_response = tool_response[:600] + f"\n... [工具响应过长，共{len(tool_response)}字符，已截断显示]"
                            else:
                                display_tool_response = tool_response
                            print(display_tool_response)

                        result_content = f"<tool_response>\n{tool_response}\n</tool_response>"
                        messages.append({"role": "user", "content": result_content})
                        
                        logger.debug(f"Tool response length: {len(tool_response)} chars")
                        
                    except Exception as e:
                        logger.warning(f"Tool call parsing failed: {e}")
                        error_response = f"<tool_response>\nError: Tool call parsing failed: {str(e)}\n</tool_response>"
                        messages.append({"role": "user", "content": error_response})
                        
                    continue
                else:
                    # No tool call, add response to messages
                    messages.append({"role": "assistant", "content": response.strip()})
                
                # Check for final answer
                if '<answer>' in response:
                    if '</answer>' not in response:
                        response = response + "</answer>"
                    if self.verbose:
                        try:
                            answer_content = response.split('<answer>')[1].split('</answer>')[0].strip()
                            print(f"\n🎯 找到最终答案:")
                            print("-" * 40)
                            print(f"{answer_content}")
                        except:
                            print(f"\n🎯 推理完成，找到最终答案")
                    logger.debug("Found final answer, reasoning complete")
                    break
                
                # Check call limit
                if num_llm_calls_available <= 0 and '<answer>' not in response:
                    logger.warning("Reached LLM call limit, forcing answer")
                    force_answer_msg = "You have now reached the maximum context length you can handle. You should stop making tool calls and, based on all the information above, think again and provide what you consider the most likely answer in the following format:<think>your final thinking</think>\n<answer>your answer</answer>"
                    messages.append({"role": "user", "content": force_answer_msg})
                    final_response = self.llm_client.call(messages)
                    messages.append({"role": "assistant", "content": final_response.strip()})
                    break
            
            # Extract final prediction
            prediction = self._extract_prediction(messages)
            termination = self._determine_termination(messages, num_llm_calls_available)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.debug(f"Reasoning complete: {duration:.2f}s, {round_count} rounds, {tool_calls} tool calls")
            
            # 计算最终token数
            final_token_count = self._estimate_token_count(messages)
            
            return {
                "messages": messages,
                "final_response": messages[-1]["content"] if messages else "",
                "prediction": prediction,
                "tool_calls": tool_calls,
                "duration": duration,
                "round_count": round_count,
                "termination": termination,
                "token_count": final_token_count,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            end_time = datetime.now()
            return {
                "messages": messages,
                "final_response": "",
                "prediction": "",
                "tool_calls": 0,
                "duration": (end_time - start_time).total_seconds(),
                "token_count": 0,
                "error": str(e),
                "termination": "error",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            }
    
    def _estimate_token_count(self, messages: List[Dict[str, str]]) -> int:
        if self.tokenizer is None:
            print("tokenizer is not valid")
            total_content = ""
            for msg in messages:
                total_content += msg.get("content", "")
            return len(total_content) // 4
        
        try:
            total_tokens = 0
            for message in messages:
                content = message.get("content", "")
                if content:
                    tokens = self.tokenizer.encode(str(content))
                    total_tokens += len(tokens)
            
            return total_tokens
            
        except Exception as e:
            logger.warning(f"Token calculation failed, using character estimation: {e}")
            total_content = ""
            for msg in messages:
                total_content += msg.get("content", "")
            return len(total_content) // 4
    
    def _extract_prediction(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "No answer found."
            
        last_content = messages[-1].get("content", "")
        if '<answer>' in last_content and '</answer>' in last_content:
            try:
                return last_content.split('<answer>')[1].split('</answer>')[0].strip()
            except:
                pass
        
        return "No answer found."
    
    def _determine_termination(self, messages: List[Dict[str, str]], calls_remaining: int) -> str:
        if not messages:
            return "no_messages"
        
        last_content = messages[-1].get("content", "")
        
        if '<answer>' in last_content and '</answer>' in last_content:
            return "answer"
        elif calls_remaining == 0:
            return "exceed_llm_calls"
        else:
            return "answer_not_found"
    
    def _handle_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Handle tool call using tool manager"""
        try:
            if tool_name not in self.tool_manager.tool_instances:
                return f"Error: Tool '{tool_name}' not available"
            
            tool = self.tool_manager.tool_instances[tool_name]
            
            if tool_name == "search":
                # Check required arguments
                if "query" not in tool_args:
                    return f"Error: Missing required argument 'query' for search tool"
                
                query = tool_args["query"]
                if isinstance(query, str):
                    query = [query]
                result = tool(query)
                
            elif tool_name == "visit":
                # Check required arguments
                if "url" not in tool_args:
                    return f"Error: Missing required argument 'url' for visit tool"
                
                url = tool_args["url"]
                if isinstance(url, str):
                    url = [url]
                
                # goal is optional for visit tool
                goal = tool_args.get("goal", "Get webpage content")
                result = tool(url, goal)
                
            else:
                return f"Error: Unknown tool '{tool_name}'"
            
            return str(result)
            
        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return f"Error: {str(e)}"


def create_reasoning_agent(config_path: Optional[str] = None, verbose: bool = False) -> ReasoningAgent:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), '../../evaluation_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    tool_manager = create_tool_manager()
    
    llm_client = LLMClient(config['llm'])
    
    runtime_config = config.get('runtime', {})
    runtime_config['verbose'] = verbose  # 添加verbose参数
    reasoning_agent = ReasoningAgent(llm_client, tool_manager, runtime_config)
    
    return reasoning_agent 