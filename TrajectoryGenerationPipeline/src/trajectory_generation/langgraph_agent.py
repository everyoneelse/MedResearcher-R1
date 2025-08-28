#!/usr/bin/env python3

import os
import json
import sys
from typing import Dict, List, Any, Optional
from transformers import AutoTokenizer
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

# Add parent directory to path for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Add project root to path for global tools import
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, project_root)

from tools import create_tool_manager
from prompts import build_system_message, build_user_message


def fix_think_tags(content: str) -> str:
    if "<answer>" in content and "</answer>" in content and "<think>" not in content:
        answer_pos = content.find("<answer>")
        if answer_pos != -1:
            before_answer = content[:answer_pos]
            answer_and_after = content[answer_pos:]
            return f"<think>\n{before_answer}</think>\n{answer_and_after}"
        else:
            return f"<think>\n{content}\n</think>"
    
    return content


MAX_TOKEN_LENGTH = int(os.getenv('MAX_LENGTH', 40 * 1024 - 500))


class ToolServiceError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def detect_language(text: str) -> str:
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    total_chars = len(text)
    
    if total_chars == 0:
        return "en"
    
    if chinese_chars / total_chars > 0.3:
        return "zh"
    else:
        return "en"


class LangGraphReasoningAgent:
    """LangGraph-based ReAct agent using create_react_agent"""
    
    def __init__(
        self,
        model: str = None,
        generate_cfg: Dict = None,
        tool_config_path: str = None,
        enabled_tools: List[str] = None,
        system_message: str = None,
        use_cheat_sheet: bool = False,
        max_llm_calls: int = None,
        max_token_length: int = None,
        llm_config: Dict[str, Any] = None,
        tokenizer_path: str = ""
    ):
        self.model = model
        self.generate_cfg = generate_cfg or {}
        self.enabled_tools = enabled_tools or ['search', 'read']
        self.system_message = system_message
        self.use_cheat_sheet = use_cheat_sheet
        self.llm_config = llm_config or {}
        self.tokenizer_path = tokenizer_path
        
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)

        self.tool_manager = create_tool_manager(tool_config_path)
        
        self.max_llm_calls = max_llm_calls
        self.max_token_length = max_token_length
        
        self.llm = self._create_llm()
        
        self.tools = self.tool_manager.get_enabled_tools(self.enabled_tools)

        self.agent = create_react_agent(
            model=self.llm,
            tools=self.tools
        )
    
    def _create_llm(self) -> ChatOpenAI:
        api_key_env = self.llm_config.get("api_key_env")
        api_base = self.llm_config.get("api_base")
        
        api_key = os.getenv(api_key_env)
        base_url = api_base
        
        # Default fallback logic if no environment variables configured
        if not api_key:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not base_url:
                base_url = "https://openrouter.ai/api/v1"

        return ChatOpenAI(
            model=self.model,
            api_key=api_key,
            base_url=base_url,
            temperature=self.generate_cfg.get('temperature', 0.6),
            top_p=self.generate_cfg.get('top_p', 0.95),
            max_retries=self.generate_cfg.get('max_retries', 3),
            streaming=False
        )
    
    def _get_system_message(self) -> str:
        if self.system_message:
            return self.system_message
        
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        return build_system_message(use_reasoning=self.use_cheat_sheet) + f"\nCurrent date: {current_date}"
    
    def process_question(
        self,
        question: str,
        reasoning_path: str = "",
        max_iterations: int = None
    ) -> Dict[str, Any]:
        max_iterations = max_iterations or self.max_llm_calls
        
        question_language = detect_language(question)
        
        if self.use_cheat_sheet and reasoning_path:
            user_message = build_user_message(
                question, 
                question_language, 
                reasoning_path
            )
        else:
            user_message = f"Do research on the question and answer it when you finish the research. When you finish your research, you should explain first and then answer, your answer should be place inside <answer></answer>, and your answer should be direct answer without any explanation. User Question: {question}"

        system_message_for_execution = self._get_system_message()
        initial_state = {
            "messages": [
                SystemMessage(content=system_message_for_execution),
                HumanMessage(content=user_message)
            ]
        }
        
        # Store original prompts for trajectory (will be replaced by training prompts later)
        original_system_prompt = system_message_for_execution
        original_user_prompt = user_message
        
        # Run the agent
        try:
            print(f"🚀 Starting ReAct agent with question: {question[:100]}...")
            print(f"🔧 Using tools: {[tool.name for tool in self.tools]}")
            
            trajectory_messages = []
            
            original_system_msg = SystemMessage(content=original_system_prompt)
            trajectory_messages.append(original_system_msg)
            
            original_user_msg = HumanMessage(content=original_user_prompt)
            trajectory_messages.append(original_user_msg)
            
            final_state = None
            step_count = 0
            tool_calls_made = False
            last_tool_calls = []
            tool_loop_detected = False
            iterations_exceeded = False
            tokens_exceeded = False
            
            for step in self.agent.stream(initial_state, {"recursion_limit": max_iterations}):
                step_count += 1
                
                if step_count >= max_iterations:
                    iterations_exceeded = True
                    break
                
                if "__end__" in step:
                    final_state = step["__end__"]
                    break
                
                for key, value in step.items():
                    if "messages" in value:
                        for msg in value["messages"]:
                            if hasattr(msg, 'type') and msg.type in ['ai', 'tool']:
                                if msg not in trajectory_messages:
                                    trajectory_messages.append(msg)
                                    
                                    if msg.type == 'ai' and hasattr(msg, 'tool_calls') and msg.tool_calls:
                                        tool_calls_made = True
                                        current_tool_calls = [tc.get('name', '') for tc in msg.tool_calls if isinstance(tc, dict)]
                                        
                                        if len(last_tool_calls) >= 2 and current_tool_calls == last_tool_calls:
                                            tool_loop_detected = True
                                            print("🔄 Tool loop detected - same tool calls repeated")
                                            break
                                        last_tool_calls = current_tool_calls
                                
                                if self.count_tokens(trajectory_messages) > self.max_token_length:
                                    tokens_exceeded = True
                                    print(f"🚫 Token limit exceeded: {self.count_tokens(trajectory_messages)} > {self.max_token_length}")
                                    break
                    
                    if tool_loop_detected or tokens_exceeded:
                        break
                if tool_loop_detected or tokens_exceeded:
                    break
            
            if final_state and not tool_loop_detected and not tokens_exceeded and not iterations_exceeded:
                final_messages = final_state.get("messages", [])
                for msg in final_messages:
                    if hasattr(msg, 'type') and msg.type in ['ai', 'tool']:
                        if msg not in trajectory_messages:
                            trajectory_messages.append(msg)
            
            print(f"📝 Agent completed with {len(trajectory_messages)} messages")
            
            # Extract final answer and determine termination status
            final_answer = "No answer"
            has_answer_tags = False
            termination = "Abnormal completed"
            
            if trajectory_messages:
                for msg in reversed(trajectory_messages):
                    if hasattr(msg, 'type') and msg.type == 'ai' and hasattr(msg, 'content'):
                        content = msg.content
                        if "<answer>" in content and "</answer>" in content:
                            answer_start = content.find("<answer>") + len("<answer>")
                            answer_end = content.find("</answer>")
                            if answer_end > answer_start:
                                final_answer = content[answer_start:answer_end].strip()
                                has_answer_tags = True
                                break
                        elif content and not hasattr(msg, 'tool_calls'):
                            final_answer = content[:500] + "..." if len(content) > 500 else content
                            break
            
            if tool_loop_detected:
                termination = "tool_loop_detected"
            elif iterations_exceeded:
                termination = "max_iterations_exceeded"
            elif tokens_exceeded:
                termination = "max_tokens_exceeded"
            elif not tool_calls_made:
                termination = "no_tool_calls"
            elif has_answer_tags:
                termination = "answer"

            
            return {
                "prediction": final_answer,
                "termination": termination,
                "trajectory_messages": trajectory_messages,
                "step_count": step_count,
                "tool_calls_made": tool_calls_made
            }
            
        except Exception as e:
            print(f"❌ Agent execution failed: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return {
                "prediction": f"Agent execution failed: {str(e)}",
                "termination": "error",
                "trajectory_messages": [],
                "step_count": 0,
                "tool_calls_made": False
            }
    
    def get_trajectory_in_training_format(self, trajectory_messages: List[BaseMessage], standard_user_prompt: str = None, training_system_prompt: str = None) -> List[Dict]:
        """
        Convert trajectory messages to training format.
        - system: specialized system_prompt
        - user: specialized user_prompt + question (uses standard_user_prompt if provided)
        - assistant: <think>content</think>\n\n<tool_call>json</tool_call>
        - user: <tool_response>\nresult\n</tool_response>
        - assistant: <think>content</think>\n<answer>answer</answer>
        
        Args:
            trajectory_messages: List of LangChain BaseMessage objects
            standard_user_prompt: Optional standard user prompt template for training
            training_system_prompt: Optional training system prompt (overrides system message from trajectory)
        """
        training_messages = []
        
        system_content = ""
        original_user_content = ""
        
        for msg in trajectory_messages:
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                if msg.type == 'system':
                    system_content = msg.content
                elif msg.type == 'human':
                    original_user_content = msg.content
                    break
        
        system_message_content = training_system_prompt if training_system_prompt else system_content
        if system_message_content:
            training_messages.append({
                "role": "system",
                "content": system_message_content
            })
        
        if standard_user_prompt and original_user_content:
            question = original_user_content
            if "User Question: " in original_user_content:
                question = original_user_content.split("User Question: ")[-1]
            elif "用户问题：" in original_user_content:
                question = original_user_content.split("用户问题：")[-1]
            elif "\n\n" in original_user_content:
                question = original_user_content.split("\n\n")[-1]
            
            user_content = standard_user_prompt + question
        else:
            user_content = original_user_content
            
        if user_content:
            training_messages.append({
                "role": "user", 
                "content": user_content
            })
        
        for msg in trajectory_messages:
            if hasattr(msg, 'type') and hasattr(msg, 'content'):
                msg_type = msg.type
                content = msg.content
                
                if msg_type == 'ai':
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            tool_json = {}
                            if hasattr(tool_call, 'name') and hasattr(tool_call, 'args'):
                                tool_json = {
                                    "name": tool_call.name,
                                    "arguments": tool_call.args
                                }
                            elif isinstance(tool_call, dict):
                                tool_json = {
                                    "name": tool_call.get("name", ""),
                                    "arguments": tool_call.get("args", {})
                                }
                            
                            if tool_json.get("name"):
                                tool_json_str = json.dumps(tool_json, ensure_ascii=False)
                                formatted_content = f"<think>{content}</think>\n\n<tool_call>{tool_json_str}</tool_call>"
                                
                                training_messages.append({
                                    "role": "assistant",
                                    "content": formatted_content
                                })
                    else:
                        if '<answer>' in content:
                            fixed_content = fix_think_tags(content)
                            training_messages.append({
                                "role": "assistant",
                                "content": fixed_content
                            })
                        else:
                            training_messages.append({
                                "role": "assistant", 
                                "content": f"<think>{content}</think>"
                            })
                            
                elif msg_type == 'tool':
                    formatted_result = f"<tool_response>\n{content}\n</tool_response>"
                    training_messages.append({
                        "role": "user",
                        "content": formatted_result
                    })
        
        return training_messages
    
    def count_tokens(self, messages: List[BaseMessage], model: str = None) -> int:
        total_tokens = 0
        for message in messages:
            if hasattr(message, 'content') and message.content:
                tokens = self.tokenizer.encode(str(message.content))
                total_tokens += len(tokens)
        
        return total_tokens
    
    def count_tokens_from_dict(self, messages: List[Dict], model: str = None) -> int:
        total_tokens = 0
        for message in messages:
            if isinstance(message, dict) and message.get('content'):
                tokens = self.tokenizer.encode(str(message['content']))
                total_tokens += len(tokens)
        
        return total_tokens
