#!/usr/bin/env python3
"""
信息模糊化器
用于对采样的信息进行模糊化处理
"""

import logging
import random
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from config import settings

logger = logging.getLogger(__name__)

class InformationAnonymizer:
    """信息模糊化器"""
    
    def __init__(self):
        """初始化模糊化器"""
        # 时间模糊化模板
        self.time_templates = {
            'year': [
                '21世纪初期', '21世纪10年代', '21世纪20年代初',
                '近十年', '过去几年', '最近几年',
                '本世纪初', '本世纪中期', '当代'
            ],
            'month': [
                '春季', '夏季', '秋季', '冬季',
                '上半年', '下半年', '年中', '年末',
                '春夏之交', '秋冬之际', '某个季度'
            ],
            'day': [
                '月初', '月中', '月末', '某一天',
                '周初', '周中', '周末', '某个时期'
            ]
        }
        
        # 数字模糊化模板
        self.number_templates = [
            '约{}', '大约{}', '接近{}', '超过{}',
            '不到{}', '几{}', '多个{}', '少数{}'
        ]
        
        # 地点模糊化模板
        self.location_templates = [
            '某个{}', '一个{}', '位于{}的', '来自{}的',
            '{}地区', '{}附近', '{}周边'
        ]
        
        # 人名模糊化模板
        self.person_templates = [
            '某位{}', '一位{}', '著名的{}', '知名{}',
            '相关{}', '业内{}', '专业{}'
        ]
        
        # 组织模糊化模板
        self.organization_templates = [
            '某{}', '一家{}', '知名{}', '大型{}',
            '国际{}', '领先{}', '专业{}'
        ]
    
    async def anonymize_sample(self, sample_info: Dict[str, Any]) -> Dict[str, Any]:
        """模糊化采样信息"""
        try:
            nodes = sample_info.get('nodes', [])
            relations = sample_info.get('relations', [])
            
            # 创建映射表
            name_mapping = {}
            
            # 模糊化节点
            anonymized_nodes = []
            for node in nodes:
                anonymized_node = await self._anonymize_node(node, name_mapping)
                anonymized_nodes.append(anonymized_node)
            
            # 模糊化关系
            anonymized_relations = []
            for relation in relations:
                anonymized_relation = await self._anonymize_relation(relation, name_mapping)
                anonymized_relations.append(anonymized_relation)
            
            # 构建结果
            result = {
                'nodes': anonymized_nodes,
                'relations': anonymized_relations,
                'anonymization_stats': {
                    'total_nodes': len(anonymized_nodes),
                    'total_relations': len(anonymized_relations),
                    'anonymized_nodes': sum(1 for node in anonymized_nodes if node.get('is_anonymized', False)),
                    'anonymized_relations': sum(1 for rel in anonymized_relations if rel.get('is_anonymized', False))
                }
            }
            
            logger.info(f"模糊化了 {len(anonymized_nodes)} 个节点和 {len(anonymized_relations)} 个关系")
            return result
            
        except Exception as e:
            logger.error(f"模糊化采样信息失败: {e}")
            return sample_info
    
    async def _anonymize_node(self, node: Dict[str, Any], name_mapping: Dict[str, str]) -> Dict[str, Any]:
        """模糊化节点"""
        try:
            # 复制节点
            anonymized_node = node.copy()
            
            # 决定是否模糊化 (确保不是所有实体都被模糊化)
            anonymize_threshold = settings.ANONYMIZE_PROBABILITY
            # 至少保留一个实体不被模糊化
            if len(name_mapping) == 0 and random.random() > 0.5:
                # 第一个实体有50%概率不被模糊化，确保至少有一个原始名称
                should_anonymize = False
            else:
                should_anonymize = random.random() < anonymize_threshold
            
            if should_anonymize:
                anonymized_node['is_anonymized'] = True
                
                # 获取原始名称
                original_name = node.get('name') or node.get('title') or str(node.get('id', ''))
                
                # 模糊化名称
                anonymized_name = await self._anonymize_name(original_name, node.get('type', 'unknown'))
                
                # 更新映射
                name_mapping[original_name] = anonymized_name
                
                # 更新节点信息
                anonymized_node['original_name'] = original_name
                anonymized_node['name'] = anonymized_name
                
                # 模糊化描述
                if 'description' in anonymized_node:
                    anonymized_node['description'] = await self._anonymize_text(anonymized_node['description'])
            else:
                anonymized_node['is_anonymized'] = False
            
            return anonymized_node
            
        except Exception as e:
            logger.error(f"模糊化节点失败: {e}")
            return node
    
    async def _anonymize_relation(self, relation: Dict[str, Any], name_mapping: Dict[str, str]) -> Dict[str, Any]:
        """模糊化关系"""
        try:
            # 复制关系
            anonymized_relation = relation.copy()
            
            # 更新节点名称
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            
            if source in name_mapping:
                anonymized_relation['source'] = name_mapping[source]
                anonymized_relation['head'] = name_mapping[source]
                anonymized_relation['from'] = name_mapping[source]
                anonymized_relation['is_anonymized'] = True
            
            if target in name_mapping:
                anonymized_relation['target'] = name_mapping[target]
                anonymized_relation['tail'] = name_mapping[target]
                anonymized_relation['to'] = name_mapping[target]
                anonymized_relation['is_anonymized'] = True
            
            # 模糊化关系描述
            if 'description' in anonymized_relation:
                anonymized_relation['description'] = await self._anonymize_text(anonymized_relation['description'])
            
            return anonymized_relation
            
        except Exception as e:
            logger.error(f"模糊化关系失败: {e}")
            return relation
    
    async def _anonymize_name(self, name: str, entity_type: str) -> str:
        """模糊化名称"""
        try:
            # 根据实体类型选择模糊化策略
            if entity_type in ['person', 'researcher', 'scientist', 'author']:
                templates = self.person_templates
                category = '研究者'
            elif entity_type in ['organization', 'company', 'institution']:
                templates = self.organization_templates
                category = '机构'
            elif entity_type in ['location', 'place', 'city', 'country']:
                templates = self.location_templates
                category = '地区'
            else:
                # 通用模糊化
                return f"某个{entity_type}"
            
            # 随机选择模板
            template = random.choice(templates)
            
            # 生成模糊化名称
            anonymized_name = template.format(category)
            
            return anonymized_name
            
        except Exception as e:
            logger.error(f"模糊化名称失败: {e}")
            return f"某个{entity_type}"
    
    async def _anonymize_text(self, text: str) -> str:
        """模糊化文本"""
        try:
            # 模糊化时间
            text = self._anonymize_time(text)
            
            # 模糊化数字
            text = self._anonymize_numbers(text)
            
            # 模糊化具体地点
            text = self._anonymize_locations(text)
            
            return text
            
        except Exception as e:
            logger.error(f"模糊化文本失败: {e}")
            return text
    
    def _anonymize_time(self, text: str) -> str:
        """模糊化时间表达"""
        try:
            # 模糊化年份
            text = re.sub(r'20\d{2}年', lambda m: random.choice(self.time_templates['year']), text)
            text = re.sub(r'20\d{2}', lambda m: random.choice(self.time_templates['year']), text)
            
            # 模糊化月份
            months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
            for month in months:
                text = text.replace(month, random.choice(self.time_templates['month']))
            
            # 模糊化具体日期
            text = re.sub(r'\d{1,2}日', lambda m: random.choice(self.time_templates['day']), text)
            text = re.sub(r'\d{4}-\d{2}-\d{2}', lambda m: random.choice(self.time_templates['year']), text)
            
            return text
            
        except Exception as e:
            logger.error(f"模糊化时间失败: {e}")
            return text
    
    def _anonymize_numbers(self, text: str) -> str:
        """模糊化数字"""
        try:
            # 模糊化大数字
            def replace_number(match):
                num = int(match.group())
                if num > 100:
                    template = random.choice(self.number_templates)
                    if num > 10000:
                        return template.format('万')
                    elif num > 1000:
                        return template.format('千')
                    else:
                        return template.format('百')
                return match.group()
            
            text = re.sub(r'\d{3,}', replace_number, text)
            
            return text
            
        except Exception as e:
            logger.error(f"模糊化数字失败: {e}")
            return text
    
    def _anonymize_locations(self, text: str) -> str:
        """模糊化地点"""
        try:
            # 常见地点模式
            location_patterns = [
                r'北京', r'上海', r'广州', r'深圳', r'杭州', r'成都',
                r'美国', r'欧洲', r'日本', r'韩国', r'新加坡',
                r'MIT', r'斯坦福', r'哈佛', r'清华', r'北大'
            ]
            
            for pattern in location_patterns:
                text = re.sub(pattern, '某地', text)
            
            return text
            
        except Exception as e:
            logger.error(f"模糊化地点失败: {e}")
            return text
    
    def _generate_generic_name(self, entity_type: str) -> str:
        """生成通用名称"""
        generic_names = {
            'person': ['研究者A', '科学家B', '专家C', '学者D'],
            'organization': ['机构X', '公司Y', '组织Z', '团队W'],
            'location': ['地区A', '区域B', '地点C', '位置D'],
            'concept': ['概念A', '理论B', '方法C', '技术D'],
            'technology': ['技术A', '方案B', '系统C', '平台D'],
            'event': ['事件A', '会议B', '项目C', '研究D']
        }
        
        names = generic_names.get(entity_type, ['实体A', '实体B', '实体C'])
        return random.choice(names)
    
    def get_anonymization_stats(self, anonymized_sample: Dict[str, Any]) -> Dict[str, Any]:
        """获取模糊化统计信息"""
        try:
            stats = anonymized_sample.get('anonymization_stats', {})
            
            # 计算模糊化比例
            total_nodes = stats.get('total_nodes', 0)
            total_relations = stats.get('total_relations', 0)
            anonymized_nodes = stats.get('anonymized_nodes', 0)
            anonymized_relations = stats.get('anonymized_relations', 0)
            
            if total_nodes > 0:
                node_anonymization_rate = anonymized_nodes / total_nodes
            else:
                node_anonymization_rate = 0
            
            if total_relations > 0:
                relation_anonymization_rate = anonymized_relations / total_relations
            else:
                relation_anonymization_rate = 0
            
            return {
                'total_nodes': total_nodes,
                'total_relations': total_relations,
                'anonymized_nodes': anonymized_nodes,
                'anonymized_relations': anonymized_relations,
                'node_anonymization_rate': node_anonymization_rate,
                'relation_anonymization_rate': relation_anonymization_rate
            }
            
        except Exception as e:
            logger.error(f"获取模糊化统计信息失败: {e}")
            return {} 