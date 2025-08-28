#!/usr/bin/env python3
"""
Rewrite prompts for think content reconstruction.
Unified prompt management for both rewriter.py and api_server.py.
"""

class RewritePrompts:
    """Unified prompt management for think content rewriting."""
    
    @staticmethod
    def get_tool_call_prompt_zh(question: str, history_text: str, original_think: str, current_action: str) -> str:
        """获取中文工具调用场景的重构prompt"""
        return f"""重构思考内容：基于问题分析，清晰说明工具调用的必要性。

问题：{question}
历史：{history_text or "无"}
原始思考：{original_think}
当前工具调用：{current_action}

要求：
1. 紧密结合工具调用必要性
2. 提高表达清晰度
3. 删除冗余表述，但不强制缩短长度
4. 不能包含XML标签，只输出纯文本思考

重构后的思考："""
    
    @staticmethod
    def get_answer_prompt_zh(question: str, history_text: str, original_think: str, current_action: str) -> str:
        """获取中文最终答案场景的重构prompt"""
        return f"""重构思考内容：基于推理历史，清晰说明答案推导过程。

问题：{question}
历史：{history_text or "无"}
原始思考：{original_think}
当前答案：{current_action}

要求：
1. 保持核心推理逻辑
2. 提高表达清晰度
3. 删除冗余表述，但不强制缩短长度
4. 不能包含XML标签，只输出纯文本思考

重构后的思考："""
    
    @staticmethod
    def get_tool_call_prompt_en(question: str, history_text: str, original_think: str, current_action: str) -> str:
        """获取英文工具调用场景的重构prompt"""
        return f"""Rebuild thinking content: based on question analysis, clearly explain tool call necessity.

Question: {question}
History: {history_text or "None"}
Original thinking: {original_think}
Current tool call: {current_action}

Requirements:
1. Tightly relate to tool call necessity
2. Improve expression clarity
3. Remove redundancy, but don't force shorter length
4. No XML tags, only output plain text thinking

Rebuilt thinking:"""
    
    @staticmethod
    def get_answer_prompt_en(question: str, history_text: str, original_think: str, current_action: str) -> str:
        """获取英文最终答案场景的重构prompt"""
        return f"""Rebuild thinking content: based on reasoning history, clearly explain answer derivation process.

Question: {question}
History: {history_text or "None"}
Original thinking: {original_think}
Current answer: {current_action}

Requirements:
1. Preserve core reasoning logic
2. Improve expression clarity
3. Remove redundancy, but don't force shorter length
4. No XML tags, only output plain text thinking

Rebuilt thinking:""" 