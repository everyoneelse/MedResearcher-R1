import openai
import json
import random
import logging
import asyncio
from typing import List, Dict, Any, Optional
from config import settings

# 配置日志
logger = logging.getLogger(__name__)

class LLMClient:
    """LLM客户端，用于与大语言模型交互"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(  # 使用异步客户端
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        self.model = settings.OPENAI_MODEL
    
    async def generate_search_queries(self, entity: str, context: str = "") -> List[str]:
        """为给定实体生成搜索查询词"""
        prompt = f"""
        给定实体: {entity}
        上下文: {context}
        
        请生成3-5个与该实体相关的搜索查询词，用于获取具体的、可验证的信息。
        
        要求：
        1. 搜索词应该能够获得具体的事实信息
        2. 避免过于宽泛的查询
        3. 重点关注具体的关系、属性、特征
        4. 确保搜索结果能提供唯一、明确的答案
        
        返回格式：JSON数组，例如：["具体搜索词1", "具体搜索词2", "具体搜索词3"]
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的知识图谱构建助手，擅长生成能获得具体、可验证信息的搜索查询词。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # 降低温度以获得更稳定的结果
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # 改进JSON解析
            try:
                if content.startswith('```json'):
                    content = content.replace('```json', '').replace('```', '').strip()
                elif content.startswith('```'):
                    content = content.replace('```', '').strip()
                
                queries = json.loads(content)
                return queries if isinstance(queries, list) else [content]
            except json.JSONDecodeError:
                # 如果返回的不是JSON格式，尝试手动解析
                lines = content.split('\n')
                queries = []
                for line in lines:
                    line = line.strip(' -"[],"')
                    if line and not line.startswith('[') and not line.startswith(']'):
                        queries.append(line)
                return queries[:5] if queries else [f"{entity} 定义", f"{entity} 用途", f"{entity} 特点"]
                
        except Exception as e:
            logger.error(f"生成搜索查询词失败: {e}")
            # 返回针对性更强的默认搜索词
            return [
                f"{entity} 是什么",
                f"{entity} 作用机制", 
                f"{entity} 主要用途",
                f"{entity} 相关研究"
            ]
    
    async def generate_complex_question(self, sample_info: Dict[str, Any]) -> Dict[str, str]:
        """基于采样信息生成简单、唯一、可验证的问题和答案"""
        nodes = sample_info.get("nodes", [])
        relations = sample_info.get("relations", [])
        
        nodes_str = ", ".join([f"{node['name']}({node['type']})" for node in nodes])
        relations_str = "; ".join([f"{rel['head']} -> {rel['tail']} ({rel['relation']})" for rel in relations])
        
        prompt = f"""
        基于以下知识图谱样本信息，生成一个简单明确、可验证的问题和答案。
        
        节点信息: {nodes_str}
        关系信息: {relations_str}
        
        要求：
        1. 问题必须简单明确，有唯一答案
        2. 答案必须具体、可验证，避免模糊表述
        3. 问题应该基于给定的实体和关系信息
        4. 答案长度控制在100字以内
        5. 避免使用过于直接的单一决定性线索（如"中国西南部的唯一直辖市"、"世界上最高的山峰"等）
        6. 问题应该需要综合多个信息要素才能确定答案，而不是依赖单一明显特征
        7. 确保所有提供的信息都对回答问题有意义，避免冗余信息
        
        良好问题示例：
        - 结合地理位置、功能特点、历史背景等多个维度
        - 基于多个实体关系的组合推断
        - 需要整合不同类型属性的综合判断
        
        避免的问题类型：
        - 仅基于单一地理特征就能确定的问题
        - 仅基于单一时间特征就能确定的问题
        - 包含"唯一"、"最"等绝对性描述的问题
        
        返回格式：JSON对象
        {{
            "question": "简单明确但需要综合信息的问题",
            "answer": "具体可验证的答案"
        }}
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的知识图谱问答专家，擅长生成简单、具体、可验证的问题和答案。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,  # 降低温度以获得更稳定的结果
                max_tokens=800
            )
            
            content = response.choices[0].message.content.strip()
            
            # 改进JSON解析
            try:
                if content.startswith('```json'):
                    content = content.replace('```json', '').replace('```', '').strip()
                elif content.startswith('```'):
                    content = content.replace('```', '').strip()
                
                result = json.loads(content)
                return result
            except json.JSONDecodeError:
                # 如果解析失败，生成默认的简单问答
                if nodes:
                    first_node = nodes[0]
                    return {
                        "question": f"{first_node['name']}属于什么类型的实体？",
                        "answer": f"{first_node['name']}属于{first_node['type']}类型的实体。"
                    }
                else:
                    return {
                        "question": "给定的知识图谱包含哪些类型的实体？",
                        "answer": "无法确定实体类型信息。"
                    }
                
        except Exception as e:
            logger.error(f"生成问题失败: {e}")
            # 生成基本的问答
            if nodes:
                first_node = nodes[0]
                return {
                    "question": f"{first_node['name']}是什么类型？",
                    "answer": f"{first_node['name']}是{first_node['type']}类型。"
                }
            else:
                return {
                    "question": "知识图谱中有多少个节点？",
                    "answer": f"知识图谱中有{len(nodes)}个节点。"
                }
    
    async def generate_response(self, prompt: str, max_retries: int = 5) -> str:
        """生成响应的通用方法"""
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        # {"role": "system", "content": "你是一个有用的AI助手，能够提供准确和有用的信息。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=10000,
                    extra_body={"enable_sec_check": False}
                )
                
                logger.info(f"llm response: {response.choices[0].message.content.strip()}")
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                # 检查是否为400状态码错误，如果是则不重试
                if hasattr(e, 'status_code') and e.status_code == 400:
                    logger.error(f"收到400状态码，不再重试: {e}")
                    return ""
                
                # 检查OpenAI特定的错误类型
                if hasattr(e, 'response') and hasattr(e.response, 'status_code') and e.response.status_code == 400:
                    logger.error(f"收到400状态码，不再重试: {e}")
                    return ""
                
                # 通过错误消息判断是否为400错误
                error_msg = str(e).lower()
                if "400" in error_msg and ("bad request" in error_msg or "client error" in error_msg):
                    logger.error(f"检测到400错误，不再重试: {e}")
                    return ""
                
                logger.error(f"生成响应失败 (尝试 {attempt + 1}/{max_retries})，文本长度：{len(prompt)}，错误信息: {e}")
                # logger.error(f"prompt: {prompt}")
                
                # 如果是最后一次尝试，直接返回空字符串
                if attempt == max_retries - 1:
                    logger.error(f"达到最大重试次数，生成响应失败")
                    return ""
                
                # 等待重试次数*10秒后重试
                await asyncio.sleep((attempt + 1) * 10)
        
        return ""

    async def anonymize_text(self, text: str) -> str:
        """对文本进行模糊化处理"""
        prompt = f"""
        对以下文本进行模糊化处理：
        {text}
        
        模糊化规则：
        1. 将具体的时间（如"2024年5月"）替换为模糊时间（如"21世纪某一年的春夏之交"）
        2. 将具体的地名替换为更笼统的地理描述
        3. 将具体的人名替换为职业或角色描述
        4. 将具体的数字替换为大概的范围
        5. 保持文本的核心信息不变
        
        返回模糊化后的文本：
        """
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的文本模糊化专家，擅长在保持信息核心含义的同时进行适当的模糊化处理。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=10000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"文本模糊化失败: {e}")
            return text  # 失败时返回原文本 

class OpenRouterLLMClient:
    """OpenRouter专用LLM客户端，用于QA生成和信息泄漏检测"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=settings.QA_API_KEY,
            base_url=settings.QA_API_BASE
        )
        self.model = settings.QA_MODEL
        logger.info(f"初始化OpenRouter客户端: {self.model} @ {settings.QA_API_BASE}")
    
    async def generate_response(self, prompt: str, max_retries: int = 5) -> str:
        """生成响应的通用方法"""
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000
                )
                
                result = response.choices[0].message.content.strip()
                logger.info(f"OpenRouter LLM response: {result[:200]}...")
                return result
                
            except Exception as e:
                logger.warning(f"OpenRouter API调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"OpenRouter API调用最终失败: {e}")
                    raise e
                await asyncio.sleep(2 ** attempt)  # 指数退避
    
    def call_llm(self, prompt: str) -> str:
        """同步调用LLM的方法，兼容现有代码"""
        try:
            # 创建新的事件循环或使用现有的
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果已有运行中的事件循环，使用asyncio.create_task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.generate_response(prompt))
                        return future.result()
                else:
                    return loop.run_until_complete(self.generate_response(prompt))
            except RuntimeError:
                # 没有事件循环，创建新的
                return asyncio.run(self.generate_response(prompt))
        except Exception as e:
            logger.error(f"OpenRouter LLM调用失败: {e}")
            raise e
    
    async def detect_information_leakage(self, question: str, reasoning_map: str, entity_mapping: dict) -> dict:
        """检测信息泄漏的专用方法"""
        prompt = f"""请分析以下推理路径是否泄漏了问题中未提到的具体信息。

问题: {question}

推理路径: {reasoning_map}

实体映射: {json.dumps(entity_mapping, ensure_ascii=False, indent=2)}

要求:
1. 检查推理路径中是否包含了问题中没有明确提到的具体信息（如具体的人名、地名、数值、时间等）
2. 推理路径应该只包含变量名和逻辑关系，具体信息应该在entity_mapping中
3. 如果发现泄漏，请生成一个不泄漏信息的修正版本，同时更新entity_mapping，确保所有实际信息都在其中

请以JSON格式返回结果：
{{
    "has_leakage": true/false,
    "leaked_info": ["泄漏的具体信息1", "泄漏的具体信息2"],
    "fixed_reasoning_map": "修正后的推理路径",
    "fixed_entity_mapping": {{修正后的实体映射}}
}}"""

        try:
            response = await self.generate_response(prompt)
            logger.info(f"OpenRouter LLM response: {response}")
            # 尝试解析JSON响应
            try:
                # 提取JSON部分
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                    return result
                else:
                    # 如果没找到JSON，返回默认结果
                    return {'has_leakage': False}
                    
            except json.JSONDecodeError:
                logger.warning(f"无法解析LLM响应为JSON: {response}")
                return {'has_leakage': False}
                
        except Exception as e:
            logger.error(f"调用OpenRouter检测信息泄漏失败: {e}")
            return {'has_leakage': False}

def get_qa_llm_client():
    """获取QA专用的LLM客户端（OpenRouter）"""
    return OpenRouterLLMClient()

def get_llm_client():
    """获取常规LLM客户端"""
    return LLMClient() 