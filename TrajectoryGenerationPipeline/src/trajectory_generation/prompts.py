#!/usr/bin/env python3
"""
Prompt configuration for the reasoning module.
Centralized management of all prompts used in trajectory generation.
"""

from datetime import datetime
import json


def get_system_prompt(role_type="default", with_reasoning_path=False, language="en"):

    # 统一角色定义
    if language == "zh":
        role_definition = "你是一个专业的信息研究助手"
        base_content = '''。你的核心职责是通过合理的工具使用和逻辑推理来解决复杂问题，并提供准确、可靠的答案。

**工作方法**：

1. **问题分析**：首先分析问题的性质和所需信息类型：
   - **基本推理**：数学计算、逻辑推理、常识判断等应直接完成
   - **外部信息**：需要实时数据、具体事实、网页内容等才使用工具

2. **合理工具使用**：仅当需要获取外部信息时使用工具：
   - 搜索未知的事实、数据、新闻等
   - 获取网页内容和具体信息
   - 验证时效性强的信息

3. **逻辑推理优先**：对于可以推理得出的内容，应直接进行分析：
   - 数学运算和逻辑判断
   - 时间计算和数字关系
   - 基于已知信息的推理

4. **综合分析**：结合工具获取的外部信息和自主推理，提供完整答案。

**工作原则**：明智地选择何时使用工具，何时进行自主推理，确保高效准确地解决问题。'''
    else:
        # 英文版本
        role_definition = "You are a professional information research assistant"
        base_content = '''. Your core responsibility is to solve complex questions through intelligent tool usage and logical reasoning, providing accurate and reliable answers.

**Working Methodology**:

1. **Problem Analysis**: First analyze the nature of the question and required information types:
   - **Basic Reasoning**: Mathematical calculations, logical deduction, common sense judgments should be completed directly
   - **External Information**: Only use tools when you need real-time data, specific facts, or web content

2. **Intelligent Tool Usage**: Use tools only when external information is needed:
   - Search for unknown facts, data, news, etc.
   - Retrieve webpage content and specific information
   - Verify time-sensitive information

3. **Reasoning First**: For content that can be deduced through reasoning, analyze directly:
   - Mathematical operations and logical judgments
   - Time calculations and numerical relationships
   - Inference based on known information

4. **Comprehensive Analysis**: Combine external information obtained through tools with autonomous reasoning to provide complete answers.

**Working Principles**: Wisely choose when to use tools and when to rely on autonomous reasoning, ensuring efficient and accurate problem-solving.'''

    return role_definition + base_content


# 基础用户提示模板
USER_PROMPT_TEMPLATES = {
    "basic_en": "Do research on the question and answer it when you finish the research. When you finish your research, you should explain first and then answer, your answer should be place inside <answer></answer>, and your answer should be direct answer without any explanation. User Question: ",
    
    "basic_zh": "对这个问题进行研究，完成研究后回答问题。当你完成研究时，你应该先解释然后回答，你的答案应该放在<answer></answer>内，你的答案应该是直接答案，不需要任何解释。用户问题：",
    
    "with_reasoning_en": """**IMPORTANT**: You are provided with some search guidance hints below. These hints suggest potential SEARCH DIRECTIONS and INVESTIGATION APPROACHES. You MUST NOT use any specific information from these hints directly as your answer or for direct reasoning.

## Search Guidance (Use ONLY as search directions):
{reasoning_path}

## Critical Instructions:

1. **Search Direction Only**: The above hints are ONLY suggestions for what topics/keywords to search for and what aspects to investigate. They are NOT factual information to be used directly in your reasoning or answers.

2. **Mandatory Tool Verification**: For any information mentioned in the guidance hints, you MUST use tools to independently find, verify, and confirm that information. Never assume the hints contain accurate facts.

3. **Balanced Approach**: 
   - **Basic reasoning** (mathematical calculations, logical deductions, common sense): Handle directly without tools
   - **Information from hints** (specific facts, data, claims): MUST be verified through tools
   - **External information** (current events, specific details): Use tools to search and verify

4. **Independent Research**: Treat the guidance as a research roadmap only. You must independently discover, verify, and validate all specific information through your tools.

5. **Evidence-Based Answers**: Your final answer must be based on:
   - Verified information you actually found through tools (not from hints)
   - Sound reasoning and calculations you performed directly

**Remember**: The guidance hints may contain inaccurate or incomplete information. Always verify through tools before using any specific claims from the hints.

When you finish your research, explain your findings first and then provide your answer inside <answer></answer>. Your answer should be a direct answer without any explanation inside the answer tags.

User Question: """,
    
    "with_reasoning_zh": """**重要说明**：你收到了一些搜索指导提示。这些提示建议了可能的搜索方向和调查方法。你绝对不能直接使用这些提示中的具体信息作为答案或进行直接推理。

## 搜索指导（仅用作搜索方向）：
{reasoning_path}

## 关键指令：

1. **仅限搜索方向**：上述提示仅仅是对搜索主题/关键词和调查方面的建议。它们不是可直接在推理或答案中使用的事实信息。

2. **强制工具验证**：对于指导提示中提到的任何信息，你必须使用工具独立查找、验证和确认该信息。绝不能假设提示中包含准确的事实。

3. **平衡方法**：
   - **基本推理**（数学计算、逻辑推理、常识判断）：直接处理，无需工具
   - **提示中的信息**（具体事实、数据、声称）：必须通过工具验证
   - **外部信息**（时事、具体细节）：使用工具搜索和验证

4. **独立研究**：将指导仅视为研究路线图。你必须通过工具独立发现、验证和确认所有具体信息。

5. **基于证据的答案**：你的最终答案必须基于：
   - 你通过工具实际找到的验证信息（不是来自提示）
   - 你直接进行的合理推理和计算

**记住**：指导提示可能包含不准确或不完整的信息。在使用提示中的任何具体声称之前，务必通过工具验证。

完成研究后，先解释你的发现，然后将答案放在<answer></answer>内。答案标签内应该是直接答案，不需要任何解释。

用户问题：""",
}


def get_user_prompt(language="en", use_reasoning=False, reasoning_path=""):
    if use_reasoning and reasoning_path:
        template_key = f"with_reasoning_{language}"
        template = USER_PROMPT_TEMPLATES[template_key]
        return template.format(reasoning_path=reasoning_path)
    else:
        template_key = f"basic_{language}"
        return USER_PROMPT_TEMPLATES[template_key]


def build_user_message(question, language="en", reasoning_path="", user_prompt_prefix=""):
    """构建完整的用户消息"""
    use_reasoning = bool(reasoning_path)
    prompt = get_user_prompt(language, use_reasoning, reasoning_path)
    
    if user_prompt_prefix:
        if use_reasoning:
            content = prompt + question
        else:
            content = user_prompt_prefix + question
    else:
        content = prompt + question
    
    return content


def get_current_date_suffix():
    return f"\nCurrent date: {datetime.now().strftime('%Y-%m-%d')}"


def build_system_message(use_reasoning=False, language="en"):
    return get_system_prompt("default", use_reasoning, language)


def build_training_system_prompt():
    """构建训练用的系统提示，包含当前日期"""
    base_prompt = '''You are a Web Information Seeking Master. Your task is to thoroughly seek the internet for information and provide accurate answers to questions. No matter how complex the query, you will not give up until you find the corresponding information.

As you proceed, adhere to the following principles:

1. **Persistent Actions for Answers**: You will engage in many interactions, delving deeply into the topic to explore all possible aspects until a satisfactory answer is found.

2. **Repeated Verification**: Before presenting a Final Answer, you will **cross-check** and **validate the information** you've gathered to confirm its accuracy and reliability.

3. **Attention to Detail**: You will carefully analyze each information source to ensure that all data is current, relevant, and from credible origins.'''
    
    # 添加当前日期
    current_date = datetime.now().strftime('%Y-%m-%d')
    return base_prompt + f'\nCurrent date: {current_date}'


def build_training_user_prompt(tool_manager, enabled_tools=None):
    training_user_prompt = """A conversation between User and Assistant. The user asks a question, and the assistant solves it by calling one or more of the following tools.
<tools>
{
  "name": "search",
  "description": "Performs batched web searches: supply an array 'query'; the tool retrieves the top 10 results for each query in one call.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "array",
        "items": {
          "type": "string"
        },
        "description": "Array of query strings. Include multiple complementary search queries in a single call."
      }
    },
    "required": [
      "query"
    ]
    }
},
{
  "name": "visit",
    "description": "Visit webpage(s) and return the summary of the content.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The URL(s) of the webpage(s) to visit. Can be a single URL or an array of URLs."
            },
            "goal": {
                "type": "string",
                "description": "The specific information goal for visiting webpage(s)."
            }
        },
        "required": [
            "url",
            "goal"
        ]
    }
}
</tools>

The assistant starts with one or more cycles of (thinking about which tool to use -> performing tool call -> waiting for tool response), and ends with (thinking about the answer -> answer of the question). The thinking processes, tool calls, tool responses, and answer are enclosed within their tags. There could be multiple thinking processes, tool calls, tool call parameters and tool response parameters.

Example response:
<think> thinking process here </think>
<tool_call>
{"name": "tool name here", "arguments": {"parameter name here": parameter value here, "another parameter name here": another parameter value here, ...}}
</tool_call>
<tool_response>
tool_response here
</tool_response>
<think> thinking process here </think>
<tool_call>
{"name": "another tool name here", "arguments": {...}}
</tool_call>
<tool_response>
tool_response here
</tool_response>
(more thinking processes, tool calls and tool responses here)
<think> thinking process here </think>
<answer> answer here </answer>

User: """
    
    return training_user_prompt
