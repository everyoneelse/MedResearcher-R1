#!/usr/bin/env python3
"""
问答生成器
基于模糊化后的采样信息生成复杂的问答对
"""

import logging
import json
import random
from typing import Dict, List, Any, Tuple
import openai

from config import settings

logger = logging.getLogger(__name__)

class QAGenerator:
    """问答生成器"""
    
    def __init__(self):
        """初始化生成器"""
        self.client = openai.AsyncOpenAI(  # 使用异步客户端
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        
        # 问题类型模板
        self.question_types = [
            "multi_hop_reasoning",  # 多跳推理
            "causal_analysis",      # 因果分析
            "comparative_analysis", # 对比分析
            "temporal_reasoning",   # 时序推理
            "complex_synthesis",    # 复杂综合
            "hypothetical_scenario" # 假设情景
        ]
        
        # 问题复杂度等级
        self.complexity_levels = {
            "high": "需要整合多个节点和关系的信息",
            "very_high": "需要深度推理和多层次分析",
            "extreme": "需要复杂的逻辑推理和全面的知识整合"
        }
    
    async def generate_complex_qa(self, anonymized_sample: Dict[str, Any]) -> Dict[str, str]:
        """生成复杂问答对"""
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            logger.info(f"基础QA生成器继承trace: {parent_trace}")
        else:
            start_trace(prefix="qa_gen")
            logger.info(f"基础QA生成器创建新trace")
        
        try:
            nodes = anonymized_sample.get('nodes', [])
            relations = anonymized_sample.get('relations', [])
            
            if not nodes or not relations:
                logger.warning("没有足够的节点或关系来生成问答对")
                return await self._generate_fallback_qa()
            
            # 基于具体的知识图谱信息生成问答对
            qa_pair = await self._generate_graph_based_qa(nodes, relations)
            
            return qa_pair
            
        except Exception as e:
            logger.error(f"生成复杂问答对失败: {e}")
            return await self._generate_fallback_qa()
    
    async def _analyze_graph_structure(self, nodes: List[Dict], relations: List[Dict]) -> Dict[str, Any]:
        """分析图结构"""
        try:
            # 统计节点类型
            node_types = {}
            for node in nodes:
                node_type = node.get('type', 'unknown')
                node_types[node_type] = node_types.get(node_type, 0) + 1
            
            # 统计关系类型
            relation_types = {}
            for relation in relations:
                rel_type = relation.get('type') or relation.get('relation') or 'unknown'
                relation_types[rel_type] = relation_types.get(rel_type, 0) + 1
            
            # 构建连接图
            connectivity = {}
            for relation in relations:
                source = relation.get('source') or relation.get('head') or relation.get('from')
                target = relation.get('target') or relation.get('tail') or relation.get('to')
                
                if source:
                    connectivity[source] = connectivity.get(source, 0) + 1
                if target:
                    connectivity[target] = connectivity.get(target, 0) + 1
            
            # 找出关键节点
            key_nodes = sorted(connectivity.items(), key=lambda x: x[1], reverse=True)[:3]
            
            analysis = {
                'node_types': node_types,
                'relation_types': relation_types,
                'connectivity': connectivity,
                'key_nodes': [node[0] for node in key_nodes],
                'total_nodes': len(nodes),
                'total_relations': len(relations)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析图结构失败: {e}")
            return {}
    
    async def _generate_qa_by_type(self, question_type: str, nodes: List[Dict], relations: List[Dict], graph_analysis: Dict[str, Any]) -> Dict[str, str]:
        """根据类型生成问答对"""
        try:
            # 构建上下文
            context = await self._build_context(nodes, relations, graph_analysis)
            
            # 根据问题类型选择合适的提示
            prompt = await self._get_question_prompt(question_type, context)
            
            # 生成问答对
            response = await self._generate_response(prompt)
            
            # 解析响应
            qa_pair = self._parse_qa_response(response)
            
            qa_pair['question_type'] = question_type
            qa_pair['complexity'] = 'high'
            
            return qa_pair
            
        except Exception as e:
            logger.error(f"根据类型生成问答对失败: {e}")
            return await self._generate_fallback_qa()
    
    async def _generate_response(self, prompt: str) -> str:
        """生成响应"""
        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个专业的问答生成专家，擅长基于知识图谱生成复杂的问答对。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"生成响应失败: {e}")
            return ""
    
    async def _build_context(self, nodes: List[Dict], relations: List[Dict], graph_analysis: Dict[str, Any]) -> str:
        """构建上下文"""
        context_parts = []
        
        # 添加节点信息
        context_parts.append("实体信息:")
        for i, node in enumerate(nodes, 1):
            name = node.get('name', f'实体{i}')
            node_type = node.get('type', 'unknown')
            description = node.get('description', '无描述')
            context_parts.append(f"{i}. {name} ({node_type}): {description}")
        
        # 添加关系信息
        context_parts.append("\n关系信息:")
        for i, relation in enumerate(relations, 1):
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            rel_type = relation.get('type') or relation.get('relation') or 'related_to'
            description = relation.get('description', '')
            
            rel_desc = f"{source} --[{rel_type}]--> {target}"
            if description:
                rel_desc += f" ({description})"
            context_parts.append(f"{i}. {rel_desc}")
        
        # 添加图分析
        context_parts.append(f"\n图结构分析:")
        context_parts.append(f"- 总节点数: {graph_analysis.get('total_nodes', 0)}")
        context_parts.append(f"- 总关系数: {graph_analysis.get('total_relations', 0)}")
        context_parts.append(f"- 关键节点: {', '.join(graph_analysis.get('key_nodes', []))}")
        
        return "\n".join(context_parts)
    
    async def _get_question_prompt(self, question_type: str, context: str) -> str:
        """获取问题提示"""
        base_prompt = f"""
        基于以下知识图谱信息，生成一个复杂的问答对。

        知识图谱信息:
        {context}

        要求:
        1. 问题必须使用图中的所有或大部分实体和关系
        2. 问题应该需要多步推理才能回答
        3. 答案应该综合多个信息源
        4. 问题应该具有挑战性，难以直接回答
        5. 答案应该详细且有逻辑性

        """
        
        type_prompts = {
            "multi_hop_reasoning": """
            问题类型: 多跳推理
            生成一个需要通过多个实体和关系进行推理的问题。问题应该要求从一个实体出发，通过多个关系链到达另一个实体，并分析这种连接的意义。
            """,
            
            "causal_analysis": """
            问题类型: 因果分析
            生成一个分析因果关系的问题。问题应该探讨实体之间的因果关系，分析某个实体或事件如何影响其他实体。
            """,
            
            "comparative_analysis": """
            问题类型: 对比分析
            生成一个需要对比分析的问题。问题应该比较不同实体的特点、作用或影响，并分析它们之间的异同。
            """,
            
            "temporal_reasoning": """
            问题类型: 时序推理
            生成一个涉及时间顺序的问题。问题应该分析实体或事件的时间关系，探讨发展过程或演变趋势。
            """,
            
            "complex_synthesis": """
            问题类型: 复杂综合
            生成一个需要综合多个角度的问题。问题应该整合所有实体和关系的信息，形成一个全面的分析或结论。
            """,
            
            "hypothetical_scenario": """
            问题类型: 假设情景
            生成一个假设性问题。问题应该基于现有信息，探讨假设情况下的可能结果或影响。
            """
        }
        
        specific_prompt = type_prompts.get(question_type, type_prompts["complex_synthesis"])
        
        return base_prompt + specific_prompt + """
        
        请返回 JSON 格式的结果：
        {
            "question": "生成的问题",
            "answer": "详细的答案",
            "reasoning": "推理过程",
            "entities_used": ["使用的实体列表"],
            "relationships_used": ["使用的关系列表"]
        }
        """
    
    def _parse_qa_response(self, response: str) -> Dict[str, str]:
        """解析问答响应"""
        try:
            # 清理响应，移除可能的markdown代码块标记
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # 尝试解析 JSON
            parsed = json.loads(cleaned_response)
            
            return {
                'question': parsed.get('question', ''),
                'answer': parsed.get('answer', ''),
                'reasoning': parsed.get('reasoning', ''),  # 保持兼容性
                'reasoning_path': parsed.get('reasoning_path', ''),  # 新增推理路径字段
                'question_type': parsed.get('question_type', 'complex_synthesis'),
                'complexity': parsed.get('complexity', 'high'),
                'entities_used': parsed.get('entities_used', []),
                'relationships_used': parsed.get('relationships_used', [])
            }
            
        except json.JSONDecodeError:
            logger.warning(f"无法解析JSON响应，尝试简单解析: {response[:200]}...")
            
            # 如果不是 JSON 格式，尝试简单解析
            lines = response.strip().split('\n')
            
            question = ""
            answer = ""
            reasoning = ""
            
            for line in lines:
                line = line.strip()
                if line.startswith('问题:') or line.startswith('Question:'):
                    question = line.split(':', 1)[1].strip()
                elif line.startswith('答案:') or line.startswith('Answer:'):
                    answer = line.split(':', 1)[1].strip()
                elif line.startswith('推理:') or line.startswith('Reasoning:'):
                    reasoning = line.split(':', 1)[1].strip()
            
            return {
                'question': question or '基于给定的知识图谱信息生成的问题',
                'answer': answer or '相关实体',
                'reasoning': reasoning or '解析失败',
                'question_type': 'complex_synthesis',
                'complexity': 'moderate',
                'entities_used': [],
                'relationships_used': []
            }
    
    async def _optimize_qa_pair(self, qa_pair: Dict[str, str]) -> Dict[str, str]:
        """优化问答对"""
        try:
            # 检查问题和答案的质量
            question = qa_pair.get('question', '')
            answer = qa_pair.get('answer', '')
            
            if not question or not answer:
                return await self._generate_fallback_qa()
            
            # 优化问题
            optimized_question = await self._optimize_question(question)
            
            # 优化答案
            optimized_answer = await self._optimize_answer(answer)
            
            return {
                'question': optimized_question,
                'answer': optimized_answer,
                'reasoning': qa_pair.get('reasoning', ''),  # 保持兼容性
                'reasoning_path': qa_pair.get('reasoning_path', ''),  # 新增推理路径字段
                'entities_used': qa_pair.get('entities_used', []),
                'relationships_used': qa_pair.get('relationships_used', []),
                'question_type': qa_pair.get('question_type', ''),
                'complexity': qa_pair.get('complexity', '')
            }
            
        except Exception as e:
            logger.error(f"优化问答对失败: {e}")
            return qa_pair
    
    async def _optimize_question(self, question: str) -> str:
        """优化问题"""
        try:
            # 确保问题以问号结尾
            if not question.endswith('?') and not question.endswith('？'):
                question += '?'
            
            # 添加复杂性提示
            complexity_phrases = [
                "请详细分析",
                "请综合考虑",
                "请深入探讨",
                "请全面评估"
            ]
            
            if not any(phrase in question for phrase in complexity_phrases):
                question = f"请详细分析：{question}"
            
            return question
            
        except Exception as e:
            logger.error(f"优化问题失败: {e}")
            return question
    
    async def _optimize_answer(self, answer: str) -> str:
        """优化答案"""
        try:
            # 确保答案有足够的长度和结构
            if len(answer) < 100:
                # 如果答案太短，添加结构性结尾
                answer += "\n\n综上所述，这个问题涉及多个实体和关系的复杂交互，需要综合分析各个方面的信息才能得出全面的结论。"
            
            return answer
            
        except Exception as e:
            logger.error(f"优化答案失败: {e}")
            return answer
    
    async def _generate_fallback_qa(self) -> Dict[str, str]:
        """生成后备问答对"""
        fallback_qa = {
            'question': '基于给定的知识图谱信息，请分析其中实体之间的关系网络，并探讨这些关系对整个系统的影响？',
            'answer': '根据知识图谱中的实体和关系，我们可以看到一个复杂的网络结构。每个实体都通过不同类型的关系与其他实体相连，形成了一个相互依赖的系统。这种网络结构表明了各实体之间的复杂交互，对理解整个系统的运作机制具有重要意义。',
            'reasoning': '这是一个基于图结构的综合分析问题。',
            'entities_used': [],
            'relationships_used': [],
            'question_type': 'complex_synthesis',
            'complexity': 'moderate'
        }
        
        return fallback_qa
    
    async def generate_multiple_qa_pairs(self, anonymized_sample: Dict[str, Any], num_pairs: int = 3) -> List[Dict[str, str]]:
        """生成多个问答对"""
        try:
            qa_pairs = []
            
            for i in range(num_pairs):
                qa_pair = await self.generate_complex_qa(anonymized_sample)
                qa_pairs.append(qa_pair)
            
            return qa_pairs
            
        except Exception as e:
            logger.error(f"生成多个问答对失败: {e}")
            return [await self._generate_fallback_qa()]
    
    async def _generate_graph_based_qa(self, nodes: List[Dict], relations: List[Dict]) -> Dict[str, str]:
        """基于知识图谱生成问答对"""
        try:
            # 构建详细的知识图谱信息
            graph_context = self._build_detailed_context(nodes, relations)
            
            # 生成问答对的prompt
            prompt = f"""
你是一个专业的复杂问答对生成专家。请基于以下知识图谱信息生成一个高质量的问答对。

参考示例1:
问题: "A comic series featuring a protagonist with supernatural attributes is authored and illustrated by a creator known for imaginative settings. The series has appeared in a Japanese youth magazine published by a major company that has also applied for intellectual property related to information retrieval systems, co-applying with a large Japanese IT enterprise. What is the title of the published invention by this company related to an associative retrieval system and method?"
答案: "Associative retrieval system and associative retrieval method"

参考示例2:
问题: "一位生物科学家，他隶属于南美某国首都的一所顶尖公立大学。该大学也与一位著名法学家有渊源——这位法学家出生于第一次世界大战前后，并为一首重要的地方颂歌创作了歌词。这位科学家带领的团队在土壤微生物领域开展合作研究，并与当地农民紧密合作，落实田间实地实验。因在共生真菌与植物相关的应用性实验中，能够提供关键的农艺见解和后勤协调，这一团队受到了认可。在这些研究中，这位科学家的团队发挥着什么核心作用?"
答案: "Alia Rodriguez Villate教授的研究团队在菌根共生研究的田间实施过程中，提供了关键的农学专业支持、物流保障，并负责与农民的沟通与合作。"

知识图谱信息:
{graph_context}

生成要求:
1. 问题必须复杂曲折，通过多个实体的关系链进行追踪
2. 问题要对实体信息进行模糊化处理（使用模糊化后的名称，不直接提及原始名称）
3. 问题要综合利用知识图谱中的多个实体和关系
4. **答案必须是"原始实体清单"中的一个确切名称**，不能是模糊化的名称
5. 答案必须简洁、具体、唯一，是一个真实的实体名称
6. 答案不能是泛泛的描述，必须是具体的、可验证的信息

请生成一个符合要求的问答对，返回JSON格式：
{{
    "question": "生成的复杂问题",
    "answer": "简洁具体的答案",
    "reasoning": "问题设计的推理过程",
    "question_type": "complex_synthesis",
    "complexity": "high"
}}
"""
            
            # 生成问答对
            response = await self._generate_response(prompt)
            
            # 解析响应
            qa_pair = self._parse_qa_response(response)
            
            # 验证答案质量
            qa_pair = await self._validate_answer_quality(qa_pair, nodes, relations)
            
            return qa_pair
            
        except Exception as e:
            logger.error(f"基于知识图谱生成问答对失败: {e}")
            return await self._generate_fallback_qa()
    
    def _build_detailed_context(self, nodes: List[Dict], relations: List[Dict]) -> str:
        """构建详细的知识图谱上下文"""
        context_parts = []
        
        # 添加实体信息（区分模糊化和原始名称）
        context_parts.append("实体信息:")
        original_entities = []  # 收集所有原始实体名称
        
        for i, node in enumerate(nodes, 1):
            name = node.get('name', f'实体{i}')
            node_type = node.get('type', 'unknown')
            description = node.get('description', '无描述')
            is_anonymized = node.get('is_anonymized', False)
            original_name = node.get('original_name', name)
            
            if is_anonymized and original_name:
                context_parts.append(f"{i}. {name} (原名: {original_name}, 类型: {node_type}, 已模糊化)")
                original_entities.append(original_name)
            else:
                context_parts.append(f"{i}. {name} (类型: {node_type}, 未模糊化)")
                original_entities.append(name)
            
            if description != '无描述':
                context_parts.append(f"   描述: {description}")
        
        # 添加关系信息
        context_parts.append("\n关系信息:")
        for i, relation in enumerate(relations, 1):
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            rel_type = relation.get('type') or relation.get('relation') or 'related_to'
            weight = relation.get('weight', 0.0)
            
            rel_desc = f"{source} --[{rel_type}]--> {target}"
            context_parts.append(f"{i}. {rel_desc}")
        
        # 添加原始实体清单（用于答案生成）
        context_parts.append("\n原始实体清单（用于答案）:")
        for entity in original_entities:
            context_parts.append(f"- {entity}")
        
        return "\n".join(context_parts)
    
    def _analyze_relationship_chains(self, nodes: List[Dict], relations: List[Dict]) -> List[str]:
        """分析关系链"""
        chains = []
        
        # 构建关系图
        graph = {}
        for relation in relations:
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            rel_type = relation.get('type') or relation.get('relation') or 'related_to'
            
            if source not in graph:
                graph[source] = []
            graph[source].append((target, rel_type))
        
        # 查找2-3跳的关系链
        for start_node in graph:
            for target1, rel1 in graph.get(start_node, []):
                chains.append(f"{start_node} --[{rel1}]--> {target1}")
                
                # 继续查找下一跳
                for target2, rel2 in graph.get(target1, []):
                    chains.append(f"{start_node} --[{rel1}]--> {target1} --[{rel2}]--> {target2}")
        
        return chains[:5]  # 返回前5个关系链
    
    async def _validate_answer_quality(self, qa_pair: Dict[str, str], nodes: List[Dict], relations: List[Dict]) -> Dict[str, str]:
        """验证答案质量"""
        try:
            answer = qa_pair.get('answer', '')
            
            # 检查答案是否来自知识图谱，优先使用原始名称
            is_valid_answer = False
            original_answer = None
            
            # 首先检查原始实体名称
            for node in nodes:
                original_name = node.get('original_name', '')
                current_name = node.get('name', '')
                
                # 如果答案包含模糊化名称，替换为原始名称
                if current_name in answer and original_name:
                    answer = answer.replace(current_name, original_name)
                    original_answer = original_name
                    is_valid_answer = True
                elif original_name in answer:
                    original_answer = original_name
                    is_valid_answer = True
                elif current_name in answer:
                    # 如果没有原始名称，使用当前名称
                    original_answer = current_name
                    is_valid_answer = True
            
            # 如果答案仍然无效，选择一个未模糊化的实体作为答案
            if not is_valid_answer and nodes:
                # 优先选择未模糊化的实体
                target_entity = None
                for node in nodes:
                    if not node.get('is_anonymized', False):
                        target_entity = node.get('name', '')
                        break
                
                # 如果所有实体都被模糊化，使用第一个实体的原始名称
                if not target_entity:
                    first_node = nodes[0]
                    target_entity = first_node.get('original_name') or first_node.get('name', '')
                
                qa_pair['answer'] = target_entity
                qa_pair['reasoning'] = f"答案修正为知识图谱中的具体实体: {target_entity}"
            else:
                # 确保答案是具体的原始名称
                if original_answer:
                    qa_pair['answer'] = original_answer
            
            return qa_pair
            
        except Exception as e:
            logger.error(f"验证答案质量失败: {e}")
            return qa_pair 