#!/usr/bin/env python3
"""
统一QA生成器
将信息模糊化和问题生成整合为一个强大的LLM指令包
支持两种模糊化范式：概念本身模糊化和属性指代模糊化
"""

import logging
import json
import random
from typing import Dict, List, Any, Optional
import openai
from config import settings

logger = logging.getLogger(__name__)

class UnifiedQAGenerator:
    """统一的模糊化+QA生成器"""
    
    def __init__(self):
        """初始化生成器"""
        # 常规LLM客户端（用于一般处理）
        self.client = openai.AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )
        
        # QA专用模型客户端（用于最终问题生成）
        self.qa_client = openai.AsyncOpenAI(
            api_key=settings.QA_API_KEY,
            base_url=settings.QA_API_BASE
        )
        
        logger.info(f"初始化QA专用模型: {settings.QA_MODEL} @ {settings.QA_API_BASE}")
        
        # 深度模糊化范式配置
        self.obfuscation_config = {
            'deep_concept_obfuscation_examples': {
                'extreme_time': {
                    'original': '1985年3月15日',
                    'obfuscated': '冷战后期某个春季，当时正值某个十年期的中段'
                },
                'deep_number': {
                    'original': '45,000人',
                    'obfuscated': '规模介于某个大型体育场容量与小型城市人口之间的群体'
                },
                'multi_organization': {
                    'original': '斯坦福大学',
                    'obfuscated': '位于西海岸硅谷核心区域的一所以创新闻名的私立研究机构'
                }
            },
            'attribute_obfuscation_examples': {
                'location': {
                    'entity': '苏轼',
                    'attribute': '四川眉山',
                    'obfuscated': '一位出生于蜀地的文学家'
                },
                'time': {
                    'entity': '爱因斯坦',
                    'attribute': '1879年出生',
                    'obfuscated': '一位19世纪末出生的物理学家'
                },
                'profession': {
                    'entity': '贝多芬',
                    'attribute': '作曲家',
                    'obfuscated': '一位以音乐创作闻名的艺术家'
                }
            },
            'quantitative_reasoning_examples': {
                'numerical_range': {
                    'original': '发行了2000万份',
                    'obfuscated': '销量突破了某个里程碑数字，超过了1000万但少于5000万'
                },
                'chronological_logic': {
                    'original': '2024年8月20日发布',
                    'obfuscated': '在疫情后的第四年、某个夏季月份的下旬发布'
                },
                'comparative_quantity': {
                    'original': '用时3年开发',
                    'obfuscated': '开发周期比大多数同类产品更长，但少于一个奥运周期'
                },
                'conditional_logic': {
                    'original': '获得了多个奖项',
                    'obfuscated': '如果以获奖数量衡量，该项目在同期发布的作品中排名前列'
                }
            }
        }
    
    async def generate_qa(
        self, 
        sample_info: Dict[str, Any],
        target_entity_for_answer: Optional[str] = None,
        sampling_algorithm: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        统一生成：模糊化处理 + 复杂问题构建
        
        Args:
            sample_info: 采样的子图信息
            target_entity_for_answer: 指定作为答案的目标实体（可选，现在主要用于兼容性）
            
        Returns:
            包含问题、答案、推理过程的完整结果
        """
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            logger.info(f"UnifiedQA继承trace: {parent_trace}")
        else:
            start_trace(prefix="unified_qa")
            logger.info(f"UnifiedQA创建新trace")
        
        try:
            nodes = sample_info.get('nodes', [])
            relations = sample_info.get('relations', [])
            
            if not nodes or not relations:
                logger.warning("子图信息不足，无法生成复杂QA")
                return await self._generate_fallback_qa()
            
            # 构建子图信息JSON
            subgraph_json = self._build_subgraph_json(nodes, relations, sampling_algorithm)
            
            # 使用智能答案选择模式：让OpenRouter模型自主选择最佳答案
            # 如果没有指定target_entity_for_answer，则传入空字符串让模型自己选择
            placeholder_answer = target_entity_for_answer or "待智能选择"
            
            logger.info("使用智能答案选择模式：让OpenRouter模型自主选择最佳答案实体")
            
            # 生成完整的QA指令包
            qa_prompt = self._build_master_prompt(subgraph_json, placeholder_answer)
            
            # 执行统一生成
            logger.info(f"使用QA专用模型生成问题: {settings.QA_MODEL}")
            response = await self._generate_response(qa_prompt)
            if not response:
                return {}
            # 解析和验证结果
            qa_result = self._parse_and_validate_response(response, nodes, placeholder_answer)
            
            # 如果模型选择了新的答案，使用智能选择的答案
            selected_answer = qa_result.get('answer', '')
            if selected_answer and selected_answer != placeholder_answer:
                logger.info(f"OpenRouter模型智能选择的答案: {selected_answer}")
                # 确保answer字段与selected_answer一致
                qa_result['answer'] = selected_answer
                logger.info("使用OpenRouter模型智能选择的答案")
            else:
                logger.info(f"使用默认/预设答案: {qa_result.get('answer', '')}")
            
            # 记录最终QA结果
            final_question = qa_result.get('question', '')
            final_answer = qa_result.get('answer', '')
            logger.info(f"最终生成结果: 问题长度={len(final_question)}, 答案={final_answer}")
            
            return qa_result
            
        except Exception as e:
            logger.error(f"统一QA生成失败: {e}")
            return await self._generate_fallback_qa()
    
    def _build_subgraph_json(self, nodes: List[Dict], relations: List[Dict], sampling_algorithm: Optional[str] = None) -> str:
        """构建结构化的子图信息JSON"""
        # 构建实体列表
        entities_info = []
        for i, node in enumerate(nodes):
            entity_info = {
                'id': f'entity_{i+1}',
                'name': node.get('name', f'实体{i+1}'),
                'type': node.get('type', 'unknown'),
                'description': node.get('description', ''),
                'attributes': node.get('attributes', {}),
                'original_name': node.get('original_name', node.get('name', ''))
            }
            entities_info.append(entity_info)
        
        # 构建关系列表
        relations_info = []
        for i, rel in enumerate(relations):
            relation_info = {
                'id': f'relation_{i+1}',
                'source': rel.get('source') or rel.get('head') or rel.get('from'),
                'target': rel.get('target') or rel.get('tail') or rel.get('to'),
                'type': rel.get('type') or rel.get('relation') or 'related_to',
                'description': rel.get('description', ''),
                'weight': rel.get('weight', 1.0)
            }
            relations_info.append(relation_info)
        
        # 构建完整的子图JSON
        subgraph_data = {
            'entities': entities_info,
            'relations': relations_info,
            'graph_stats': {
                'total_entities': len(entities_info),
                'total_relations': len(relations_info),
                'sampling_algorithm': sampling_algorithm or (nodes[0].get('sampling_algorithm', 'unknown') if nodes else 'unknown')
            }
        }
        
        return json.dumps(subgraph_data, ensure_ascii=False, indent=2)
    
    def _select_answer_target(self, nodes: List[Dict]) -> str:
        """智能选择答案目标实体（优先选择简单明确的实体）"""
        candidates = []
        
        for node in nodes:
            name = node.get('name', '')
            original_name = node.get('original_name', name)
            entity_type = node.get('type', '').lower()
            attributes = node.get('attributes', {})
            description = node.get('description', '')
            
            # 计算实体的"简洁性得分"（名称越短越好）
            name_length = len(name)
            word_count = len(name.split())
            
            # 计算实体类型优先级
            type_priority = self._get_type_priority(entity_type)
            
            # 检查是否是事件类实体（通常包含较长描述性名称）
            is_event_like = any(keyword in name.lower() for keyword in [
                '发布', '发行', '启动', '举办', '突破', '演示', '预告', '贺岁', '短片',
                '试玩', '销量', '开发', '首发', '虚幻引擎', '剧情', '线下'
            ]) or entity_type == 'event'
            
            # 简洁性得分：越简洁分数越高
            simplicity_score = 100 - name_length - (word_count * 5)
            if is_event_like:
                simplicity_score -= 50  # 事件类实体大幅降低得分
            
            candidates.append({
                'name': original_name or name,
                'simplicity_score': simplicity_score,
                'type_priority': type_priority,
                'is_event_like': is_event_like,
                'has_original': bool(original_name and original_name != name),
                'entity_type': entity_type
            })
        
        # 按优先级排序：类型优先级 > 简洁性得分 > 有原始名称
        candidates.sort(
            key=lambda x: (x['type_priority'], x['simplicity_score'], x['has_original']), 
            reverse=True
        )
        
        logger.info(f"选择答案目标实体: {candidates[0]['name']} (类型: {candidates[0]['entity_type']}, 简洁性: {candidates[0]['simplicity_score']}, 事件类: {candidates[0]['is_event_like']})")
        
        return candidates[0]['name'] if candidates else nodes[0].get('name', '未知实体')
    
    def _get_type_priority(self, entity_type: str) -> int:
        """获取实体类型的优先级（越高越适合作为答案）"""
        priority_map = {
            'person': 100,       # 人物 - 最适合
            'organization': 95,  # 组织
            'location': 90,      # 地点
            'technology': 85,    # 技术产品
            'concept': 80,       # 概念
            'time': 60,         # 时间 - 不太适合
            'event': 30,        # 事件 - 最不适合
            'unknown': 50       # 未知类型
        }
        return priority_map.get(entity_type.lower(), 50)
    
    def _build_master_prompt(self, subgraph_json: str, target_answer: str) -> str:
        """构建主控QA生成指令包"""
        
        # 检测采样算法类型
        import json
        try:
            subgraph_data = json.loads(subgraph_json)
            sampling_algorithm = subgraph_data.get('graph_stats', {}).get('sampling_algorithm', 'unknown')
        except:
            sampling_algorithm = 'unknown'
        
        # 针对最长链采样算法的特殊要求
        max_chain_requirement = ""
        if sampling_algorithm == 'max_chain':
            max_chain_requirement = f"""
### 🔗 **最长链采样特殊要求 (MAX CHAIN SAMPLING)**

由于子图使用了最长链采样算法，你必须：
1. **识别并利用最长的逻辑链条**：找到子图中最长的实体关系链（至少4-5个实体的连续关系）
2. **构建链式推理问题**：问题必须强制要求沿着这条长链进行逐步推理
3. **增强推理复杂度**：每一步推理都需要从前一步的结果推导下一步，形成严密的逻辑链条
4. **多层模糊化**：对链条上的每个实体都进行不同程度的模糊化，增加识别难度
5. **最终收敛**：经过长链推理最终必须精确指向你智能选择的最佳答案实体

**链式推理模式示例：**
"通过实体A的属性X → 识别关联实体B → 基于B的特征Y → 追踪到实体C → 结合C的关系Z → 最终定位实体D"

---
"""
        
        prompt = f"""# 任务：基于子图生成多跳推理问题

你是一个专业的问题生成器，需要根据提供的子图信息生成一个需要多跳推理的问题。

## 子图信息
```json
{subgraph_json}
```

## 生成要求

1. **选择答案实体**：从子图中智能选择一个合适的实体作为答案，答案必须是明确无歧义的信息
2. **模糊化描述**：对实体进行适度模糊化，不直接使用实体名称
3. **多跳推理**：构建需要多步推理的问题
4. **推理路径**：生成解答问题的完整推理、查询路径，使用参数名代替实际信息

## 推理路径要求

reasoning_path必须详细描述如何一步步解答问题，包括：
- **推理步骤**：说明每一步的逻辑推导过程
- **查询需求**：指出需要查找哪些外部信息来验证推理
- **信息关联**：解释如何将不同线索组合起来
- **最终收敛**：说明如何从多条线索最终确定唯一答案

**【重要】参数化表达要求**：
- **严禁出现任何实际信息**：包括实体名称、具体数据、时间信息、人名、地名等
- **必须使用参数名**：Entity_A、Entity_B、Target_Entity、Clue_1、Clue_2、Data_X等
- **完全参数化**：reasoning_path中的每一个具体信息都必须用对应的参数名代替
- **示例**：写成"通过Entity_A的Attribute_1特征，查询Data_X信息，关联到Entity_B"，而不是"通过糖尿病的症状特征，查询血糖数据，关联到胰岛素"

## 答案选择标准

- **明确性**：答案必须是具体、明确的实体名称，避免模糊或歧义的概念
- **唯一性**：答案在给定子图中必须是唯一确定的，不会与其他实体混淆
- **具体性**：优先选择具体的实体（如人名、药物名、疾病名）而非抽象概念

## 模糊化策略

- **时间模糊化**："2019年" → "某个以9结尾的年份"
- **机构模糊化**："清华大学" → "位于北京的知名理工科大学"  
- **人物模糊化**："张三教授" → "某位在该领域有重要贡献的学者"
- **数值模糊化**："50万人" → "规模约为中等城市人口的群体"

## 输出格式

请严格按照以下JSON格式输出：

```json
{{
    "question": "生成的多跳推理问题（使用模糊化描述）",
    "answer": "选择的实体名称",
    "reasoning_path": "详细的解答步骤，包括推理过程、查询需求、信息关联等（严禁出现任何实际信息，必须全部使用Entity_A、Entity_B、Clue_1等参数名）",
    "entity_mapping": {{
        "Entity_A": "第一个相关实体的实际名称",
        "Entity_B": "第二个相关实体的实际名称",
        "Target_Entity": "答案实体的实际名称",
        "Clue_1": "第一个线索的实际内容"
    }}
}}
```

请生成一个清晰、有逻辑的多跳推理问题。

**重要提醒**：
- 答案必须是子图中明确无歧义的实体名称，不能是模糊概念或描述性内容
- reasoning_path必须提供完整的解答路径，包括每一步推理、需要查询的信息、如何关联线索等详细步骤
- **reasoning_path严禁出现任何实际信息**：不能有实体名称、具体数据、人名、地名等，必须全部用参数名（Entity_A、Clue_1等）代替"""

        return prompt
    
    async def _generate_response(self, prompt: str) -> str:
        """生成LLM响应 - 使用QA专用模型"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"OpenRouter API调用 (尝试 {attempt + 1}/{max_retries})")
                
                # 使用QA专用模型客户端
                response = await self.qa_client.chat.completions.create(
                    model=settings.QA_MODEL,
                    messages=[
                        {
                            "role": "system", 
                            "content": "你是一位问题设计专家，专精于构建需要多步推理的复杂问题。你精通信息模糊化技术和干扰设计，能够将简单直接的信息转化为需要复杂的逻辑推理+多重信息查证才能解决的谜题。你的问题设计原则是：最大化推理步骤数量，最大化信息查找依赖，最小化直接线索，确保答案的唯一性和强验证性。"
                        },
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.9,  # 更高的温度以增加创造性和复杂度
                    max_tokens=8192,  # 大幅增加token限制，支持超复杂问题生成
                    stream=False,  # 确保不使用流式输出
                    top_p=0.85,  # 适当降低top_p增加多样性
                    presence_penalty=0.2,  # 增加避免重复的力度
                    frequency_penalty=0.15,  # 更强鼓励多样性和创新表达
                    timeout=120  # 增加超时时间到2分钟
                )
                
                # 记录API响应详情
                logger.info(f"OpenRouter API响应成功:")
                logger.info(f"  - Model: {response.model if hasattr(response, 'model') else 'N/A'}")
                logger.info(f"  - Usage: {response.usage if hasattr(response, 'usage') else 'N/A'}")
                
                # 提取内容，兼容openrouter的返回格式
                content = response.choices[0].message.content
                if not content:
                    logger.warning(f"尝试 {attempt + 1}: 响应内容为空")
                    if attempt < max_retries - 1:
                        continue
                    return ""
                
                content = content.strip()
                logger.info(f"原始响应长度: {len(content)} 字符")
            
                # 截取</think>后的部分作为真正的响应内容
                if '</think>' in content:
                    think_end_index = content.find('</think>')
                    content = content[think_end_index + len('</think>'):].strip()
                    logger.info("检测到</think>标记，截取后续内容作为响应")
                
                # 检查响应完整性
                if not self._is_response_complete(content):
                    logger.warning(f"尝试 {attempt + 1}: 响应不完整 (长度: {len(content)})")
                    logger.warning(f"响应末尾: ...{content[-100:] if len(content) > 100 else content}")
                    logger.info(f"不完整响应:\n{content}")
                    if attempt < max_retries - 1:
                        logger.info(f"重试获取完整响应...")
                        continue
                    else:
                        logger.error("多次尝试后仍获得不完整响应，使用当前响应")
                
                return content
                
            except Exception as e:
                logger.error(f"OpenRouter API调用失败 (尝试 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    logger.info("等待1秒后重试...")
                    import asyncio
                    await asyncio.sleep(1)
                    continue
                    
                # logger.error("QA专用模型响应生成失败，回退到常规模型...")
                break
        
        # 回退到常规模型
        # try:
        #     logger.info("使用常规模型作为备用...")
        #     response = await self.client.chat.completions.create(
        #         model=settings.OPENAI_MODEL,
        #         messages=[
        #             {
        #                 "role": "system", 
        #                 "content": "你是一位世界级的复杂问题设计专家，专精于构建需要5-6步推理的超高难度问题。"
        #             },
        #             {"role": "user", "content": prompt}
        #         ],
        #         temperature=0.8,
        #         max_tokens=6144,  # 增加token限制
        #         timeout=120  # 增加超时时间
        #     )
        #     content = response.choices[0].message.content
        #     return content.strip() if content else ""
        # except Exception as fallback_e:
        #     logger.error(f"回退模型也失败: {fallback_e}")
        #     return ""
        return ""
    
    def _is_response_complete(self, content: str) -> bool:
        """检查响应是否完整"""
        if not content:
            return False
            
        # 检查是否是有效的JSON格式
        content_clean = content.strip()
        if content_clean.startswith('```json'):
            content_clean = content_clean.replace('```json', '').replace('```', '').strip()
        elif content_clean.startswith('```'):
            content_clean = content_clean.replace('```', '').strip()
        
        # 基本完整性检查
        if not content_clean.startswith('{'):
            return False
            
        if not content_clean.endswith('}'):
            return False
        
        # 检查关键字段是否存在
        required_fields = ['"question":', '"answer":', '"reasoning_path":']
        for field in required_fields:
            if field not in content_clean:
                logger.warning(f"缺少必需字段: {field}")
                return False
        
        # 尝试JSON解析
        try:
            import json
            json.loads(content_clean)
            return True
        except json.JSONDecodeError as e:
            logger.warning(f"JSON格式检查失败: {e}")
            return False
    
    def _robust_extract_qa(self, content: str, target_answer: str) -> Dict[str, Any]:
        """从不完整的JSON中强制提取QA信息"""
        logger.info("执行强制QA信息提取...")
        
        result = {
            'selected_answer': '',
            'question': '',
            'answer': target_answer,
            'reasoning_path': '',
            'entity_mapping': {},
        }
        
        try:
            # 清理内容
            content_clean = content.strip()
            if content_clean.startswith('```json'):
                content_clean = content_clean.replace('```json', '').replace('```', '').strip()
            elif content_clean.startswith('```'):
                content_clean = content_clean.replace('```', '').strip()
            
            # 使用正则表达式提取关键字段
            import re
            
            # 提取selected_answer
            selected_match = re.search(r'"selected_answer"\s*:\s*"([^"]+)"', content_clean)
            if selected_match:
                result['selected_answer'] = selected_match.group(1)
                result['answer'] = selected_match.group(1)  # 保持一致
                logger.info(f"提取到selected_answer: {result['selected_answer']}")
            
            # 提取question - 支持多行文本
            question_match = re.search(r'"question"\s*:\s*"([^"]+(?:\\.|[^"\\])*)"', content_clean, re.DOTALL)
            if question_match:
                question_text = question_match.group(1)
                # 处理转义字符
                question_text = question_text.replace('\\"', '"').replace('\\n', '\n')
                result['question'] = question_text
                logger.info(f"提取到question: {question_text[:100]}...")
            
            # 提取answer（作为备用）
            if not result.get('answer') or result['answer'] == target_answer:
                answer_match = re.search(r'"answer"\s*:\s*"([^"]+)"', content_clean)
                result['answer'] = answer_match.group(1)
                if answer_match:
                    result['answer'] = answer_match.group(1)
                    logger.info(f"提取到answer: {result['answer']}")
            
            # 提取reasoning_path - 支持多行文本
            reasoning_match = re.search(r'"reasoning_path"\s*:\s*"([^"]+(?:\\.|[^"\\])*)"', content_clean, re.DOTALL)
            if reasoning_match:
                reasoning_text = reasoning_match.group(1)
                # 处理转义字符
                reasoning_text = reasoning_text.replace('\\"', '"').replace('\\n', '\n')
                result['reasoning_path'] = reasoning_text
                logger.info(f"提取到reasoning_path: {reasoning_text[:100]}...")
            
            # 提取entity_mapping - 支持嵌套JSON对象
            mapping_match = re.search(r'"entity_mapping"\s*:\s*(\{[^}]+\})', content_clean)
            if mapping_match:
                try:
                    mapping_str = mapping_match.group(1)
                    # 简单的JSON解析尝试
                    import json
                    mapping_obj = json.loads(mapping_str)
                    result['entity_mapping'] = mapping_obj
                    logger.info(f"提取到entity_mapping: {mapping_obj}")
                except Exception as mapping_e:
                    logger.warning(f"entity_mapping解析失败: {mapping_e}")
                    # 尝试简单的键值对提取
                    mapping_pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', mapping_str)
                    if mapping_pairs:
                        result['entity_mapping'] = dict(mapping_pairs)
                        logger.info(f"通过简单解析提取到entity_mapping: {result['entity_mapping']}")
            
            # 验证提取结果
            if result['question'] and result['answer'] and result['answer'] != target_answer:
                logger.info("强制提取成功：获得完整的问题和答案")
                return result
            else:
                logger.warning("强制提取部分成功，但缺少关键信息")
                
        except Exception as e:
            logger.error(f"强制提取过程出错: {e}")
        
        # 如果强制提取失败，尝试更简单的文本匹配
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if '问题' in line or 'question' in line.lower():
                # 尝试提取问题文本
                if ':' in line:
                    question_part = line.split(':', 1)[1].strip().strip('"').strip(',')
                    if len(question_part) > 20:  # 问题应该足够长
                        result['question'] = question_part
                        
            if '答案' in line or 'answer' in line.lower():
                # 尝试提取答案
                if ':' in line:
                    answer_part = line.split(':', 1)[1].strip().strip('"').strip(',')
                    if answer_part and answer_part != target_answer:
                        result['answer'] = answer_part
                        result['selected_answer'] = answer_part
        
        logger.info(f"最终提取结果: question={bool(result['question'])}, answer={result['answer']}, reasoning_path={bool(result['reasoning_path'])}")
        return result
    
    def _parse_and_validate_response(
        self, 
        response: str, 
        nodes: List[Dict], 
        target_answer: str
    ) -> Dict[str, Any]:
        """解析和验证LLM响应"""
        try:
            # === 详细记录原始响应信息 ===
            logger.info("=== OpenRouter原始响应分析 ===")
            logger.info(f"响应长度: {len(response) if response else 0} 字符")
            logger.info(f"响应为空: {not response}")
            if response:
                logger.info(f"响应前100字符: {repr(response[:100])}")
                logger.info(f"响应后100字符: {repr(response[-100:])}")
                logger.info(f"响应是否以```开头: {response.startswith('```')}")
                logger.info(f"响应是否以{{开头: {response.strip().startswith('{')}")
                logger.info(f"响应是否以}}结尾: {response.strip().endswith('}')}")
            logger.info("=== 完整原始响应内容 ===")
            logger.info(f"原始响应:\n{response}")
            logger.info("=== 原始响应内容结束 ===")
            
            # 清理响应文本
            original_response = response  # 保存原始响应用于错误日志
            response = response.strip()
            if response.startswith('```json'):
                response = response.replace('```json', '').replace('```', '').strip()
                logger.info("移除了```json标记")
            elif response.startswith('```'):
                response = response.replace('```', '').strip()
                logger.info("移除了```标记")
            
            logger.info("=== 清理后的响应 ===")
            logger.info(f"清理后长度: {len(response)} 字符")
            logger.info(f"清理后响应:\n{response}")
            logger.info("=== 清理后响应结束 ===")
            
            # 解析JSON
            try:
                logger.info("开始JSON解析...")
                result = json.loads(response)
                logger.info("JSON解析成功!")
                logger.info(f"解析结果类型: {type(result)}")
                if isinstance(result, dict):
                    logger.info(f"JSON字典键: {list(result.keys())}")
            except json.JSONDecodeError as e:
                logger.error("=== JSON解析失败详细信息 ===")
                logger.error(f"JSON解析错误: {e}")
                logger.error(f"错误位置: 行{e.lineno}, 列{e.colno}, 字符位置{e.pos}")
                logger.error(f"原始响应长度: {len(original_response)}")
                logger.error(f"清理后响应长度: {len(response)}")
                logger.error("错误位置附近的内容:")
                if hasattr(e, 'pos') and e.pos > 0:
                    start = max(0, e.pos - 50)
                    end = min(len(response), e.pos + 50)
                    logger.error(f"位置{start}-{end}: {repr(response[start:end])}")
                logger.error("=== JSON解析失败信息结束 ===")
                
                # 容错解析：尝试从不完整的JSON中提取核心信息
                logger.info("开始容错解析，尝试提取核心QA信息...")
                result = self._robust_extract_qa(original_response, target_answer)
                
                # 如果容错解析成功提取到了question、answer和reasoning_path，认为解析成功
                if result.get('question') and result.get('answer') and result.get('answer') != target_answer:
                    logger.info(f"容错解析成功! 提取到问题和答案: {result.get('answer')}")
                    # 推理路径是可选的，不强制要求
                    if not result.get('reasoning_path'):
                        logger.info("未提取到推理路径，将在后续验证中生成")
                else:
                    # 最后的备用方案
                    result = self._extract_qa_from_text(original_response, target_answer)
            
            # 验证和补充必要字段
            validated_result = self._validate_qa_result(result, target_answer, nodes)
            
            return validated_result
                 
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            logger.error(f"原始响应: {response}")
            return self._create_fallback_result(target_answer, nodes)
    
    def _extract_qa_from_text(self, text: str, target_answer: str) -> Dict[str, Any]:
        """从文本中提取问答信息（JSON解析失败时的备用方法）"""
        result = {
            'selected_answer': '',
            'question': '',
            'answer': target_answer,
            'reasoning_path': '',
            'entity_mapping': {},
        }
        
        # 尝试提取问题
        lines = text.split('\n')
        for line in lines:
            if 'question' in line.lower() and ':' in line:
                question_part = line.split(':', 1)[1].strip().strip('"')
                if len(question_part) > 10:
                    result['question'] = question_part
                    break
        
        # 如果没找到问题，生成一个基本问题
        if not result['question']:
            result['question'] = f"基于给定的复杂知识网络，请推理出最终指向的核心实体是什么？"
        
        # 尝试提取智能答案
        for line in lines:
            if '智能答案' in line or '智能选择' in line:
                answer_part = line.split(':', 1)[1].strip().strip('"')
                if answer_part:
                    result['selected_answer'] = answer_part
                    break
        
        # 尝试提取推理路径
        for line in lines:
            if '推理' in line or 'reasoning' in line.lower():
                if ':' in line:
                    reasoning_part = line.split(':', 1)[1].strip().strip('"').strip(',')
                    if len(reasoning_part) > 20:  # 推理路径应该足够长
                        result['reasoning_path'] = reasoning_part
                        break
        
        return result
    
    def _validate_qa_result(
        self, 
        result: Dict[str, Any], 
        target_answer: str, 
        nodes: List[Dict]
    ) -> Dict[str, Any]:
        """验证和完善QA结果"""
        # 确保基本字段存在
        validated = {
            'selected_answer': result.get('selected_answer', target_answer),
            'question': result.get('question', ''),
            'answer': result.get('answer', target_answer),
            'reasoning_path': result.get('reasoning_path', ''),
            'entity_mapping': result.get('entity_mapping', {}),
        }
        
        # # 验证答案
        # if not validated['answer'] or validated['answer'] != target_answer:
        #     validated['answer'] = target_answer
        #     validated['answer_validation'] = 'corrected_to_target'
        # else:
        #     validated['answer_validation'] = 'matches_target'
        
        # 验证问题质量
        question = validated['question']
        if not question or len(question) < 20:
            validated['question'] = self._generate_fallback_question(nodes, target_answer)
            validated['question_quality'] = 'generated_fallback'
        else:
            validated['question_quality'] = 'original'
        
        # 验证推理路径
        reasoning = validated['reasoning_path']
        if not reasoning or len(reasoning) < 30:
            validated['reasoning_path'] = self._generate_fallback_reasoning(nodes, target_answer)
            validated['reasoning_quality'] = 'generated_fallback'
        else:
            validated['reasoning_quality'] = 'original'
        
        # 添加元数据
        validated['generation_metadata'] = {
            'generation_method': 'unified_obfuscation_qa',
            'target_entity': target_answer,
            'nodes_used': len(nodes),
            'obfuscation_strategies': 0 # No obfuscation strategies in simplified output
        }
        
        return validated
    
    def _generate_fallback_question(self, nodes: List[Dict], target_answer: str) -> str:
        """生成备用问题"""
        if not nodes:
            return f"什么是 {target_answer}？"
        
        # 基于节点信息生成一个基本的复杂问题
        node_types = [node.get('type', 'unknown') for node in nodes]
        unique_types = list(set(node_types))
        
        if len(nodes) >= 3:
            return f"在一个包含{', '.join(unique_types)}等多种类型实体的复杂网络中，通过分析实体间的关系链和属性特征，同时验证关键信息，最终指向的核心实体是什么？"
        else:
            return f"基于给定的知识网络结构，请推理出与{unique_types[0] if unique_types else '相关实体'}密切相关并需要验证具体信息的目标实体是什么？"
    
    def _generate_fallback_reasoning(self, nodes: List[Dict], target_answer: str) -> str:
        """生成备用推理路径"""
        if not nodes:
            return f"基于题目描述，通过逻辑推理和必要的信息验证可以确定答案是{target_answer}。"
        
        # 构建基本的推理路径
        reasoning_steps = []
        
        # 第一步：识别实体类型和领域
        node_types = [node.get('type', 'unknown') for node in nodes]
        unique_types = list(set(node_types))
        reasoning_steps.append(f"第一步：分析题目中涉及的实体类型包括{', '.join(unique_types)}等，确定问题领域。")
        
        # 第二步：分析关系网络
        if len(nodes) >= 2:
            reasoning_steps.append("第二步：分析实体间的关系网络，识别关键的连接节点和路径。")
        
        # 第三步：综合线索和验证信息
        reasoning_steps.append("第三步：综合所有线索，通过排除法和逻辑推理，同时验证提供的关键信息，锁定目标实体。")
        
        # 第四步：确认答案
        reasoning_steps.append(f"第四步：验证推理结果并确认相关数据，确认答案为{target_answer}，该答案与所有线索和提供的信息都能完美匹配。")
        
        return " ".join(reasoning_steps)
    
    def _create_fallback_result(self, target_answer: str, nodes: List[Dict]) -> Dict[str, Any]:
        """创建备用结果"""
        return {
            'selected_answer': '无法确定',
            'question': self._generate_fallback_question(nodes, target_answer),
            'answer': target_answer,
            'reasoning_path': self._generate_fallback_reasoning(nodes, target_answer),
            'entity_mapping': {
                'Target_Entity': target_answer
            },
            'generation_metadata': {
                'generation_method': 'fallback',
                'target_entity': target_answer,
                'nodes_used': len(nodes),
                'is_fallback': True
            }
        }
    
    async def _generate_fallback_qa(self) -> Dict[str, Any]:
        """生成最基本的备用问答"""
        return {
            'selected_answer': '无法确定',
            'question': '基于复杂的知识图谱结构，通过多跳推理分析实体间的深层关联，同时验证关键信息，最终指向的核心概念是什么？',
            'answer': '无法确定',
            'reasoning_path': '由于子图信息不足，无法构建完整的推理链条。需要更多的实体关系信息才能进行有效的多跳推理分析和信息验证。',
            'entity_mapping': {},
            'generation_metadata': {
                'generation_method': 'emergency_fallback',
                'is_fallback': True
            }
        }
    
    async def generate_multiple_qa_variants(
        self, 
        sample_info: Dict[str, Any], 
        num_variants: int = 3
    ) -> List[Dict[str, Any]]:
        """生成多个QA变体"""
        variants = []
        
        for i in range(num_variants):
            try:
                # 每次选择不同的目标实体（如果有足够的节点）
                nodes = sample_info.get('nodes', [])
                if len(nodes) > i:
                    target_entity = nodes[i].get('original_name') or nodes[i].get('name', '')
                else:
                    target_entity = None
                
                variant = await self.generate_qa(
                    sample_info, target_entity
                )
                variant['variant_id'] = i + 1
                variants.append(variant)
                
            except Exception as e:
                logger.error(f"生成第{i+1}个QA变体失败: {e}")
                continue
        
        return variants if variants else [await self._generate_fallback_qa()] 