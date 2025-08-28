#!/usr/bin/env python3
"""
实体链接器 - 负责将实体链接到Wikidata知识库
"""

import asyncio
import logging
import aiohttp
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class EntityLinker:
    """Wikidata实体链接器"""
    
    def __init__(self):
        """初始化实体链接器"""
        self.session = None
        self.cache = {}  # 简单的内存缓存
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def link_entity(self, entity_name: str, language: str = "zh", limit: int = 5) -> Dict[str, Any]:
        """
        将单个实体链接到Wikidata知识库
        
        Args:
            entity_name: 实体名称
            language: 语言代码，默认为中文("zh")，也可使用英文("en")
            limit: 返回结果数量限制
            
        Returns:
            Dict包含以下信息:
            - success: 是否成功链接
            - standard_name: 标准实体名称
            - wikidata_id: Wikidata实体ID (Q开头)
            - description: 实体描述
            - aliases: 别名列表
            - properties: 相关属性信息
            - url: Wikidata页面链接
            - confidence: 匹配置信度
        """
        logger.info(f"开始进行实体链接: {entity_name} (语言: {language})")
        
        # 检查缓存
        cache_key = f"{entity_name}_{language}"
        if cache_key in self.cache:
            logger.info(f"从缓存获取结果: {entity_name}")
            return self.cache[cache_key]
        
        result = {
            'success': False,
            'standard_name': entity_name,
            'wikidata_id': None,
            'description': None,
            'aliases': [],
            'properties': {},
            'url': None,
            'confidence': 0.0,
            'error': None
        }
        
        try:
            # 确保有session
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # 第一步：搜索实体
            search_results = await self._search_wikidata_entity(entity_name, language, limit)
            
            if not search_results:
                result['error'] = "未找到匹配的Wikidata实体"
                logger.warning(f"未找到实体 '{entity_name}' 的Wikidata匹配")
                self.cache[cache_key] = result
                return result
            
            # 选择最佳匹配（第一个结果通常是最相关的）
            best_match = search_results[0]
            wikidata_id = best_match.get('id')
            
            if not wikidata_id:
                result['error'] = "获取的Wikidata ID无效"
                self.cache[cache_key] = result
                return result
            
            # 第二步：获取详细信息
            entity_details = await self._get_wikidata_entity_details(wikidata_id, language)
            
            if entity_details:
                result.update({
                    'success': True,
                    'standard_name': entity_details.get('label', entity_name),
                    'wikidata_id': wikidata_id,
                    'description': entity_details.get('description', ''),
                    'aliases': entity_details.get('aliases', []),
                    'properties': entity_details.get('properties', {}),
                    'url': f"https://www.wikidata.org/wiki/{wikidata_id}",
                    'confidence': self._calculate_match_confidence(entity_name, entity_details)
                })
                
                logger.info(f"成功链接实体 '{entity_name}' -> {wikidata_id} ({result['standard_name']})")
            else:
                result['error'] = "获取Wikidata实体详细信息失败"
            
            # 缓存结果
            self.cache[cache_key] = result
                
        except Exception as e:
            error_msg = f"实体链接过程中发生错误: {str(e)}"
            result['error'] = error_msg
            logger.error(error_msg)
            # 也缓存失败的结果，避免重复请求
            self.cache[cache_key] = result
        
        return result
    
    async def link_entities_batch(self, entity_names: List[str], language: str = "zh") -> Dict[str, Dict[str, Any]]:
        """
        批量进行实体链接
        
        Args:
            entity_names: 实体名称列表
            language: 语言代码
            
        Returns:
            实体名称到链接结果的字典映射
        """
        logger.info(f"开始批量实体链接，共 {len(entity_names)} 个实体")
        
        results = {}
        
        # 使用asyncio.gather并发处理，但限制并发数量避免API限制
        semaphore = asyncio.Semaphore(5)  # 最多5个并发请求
        
        async def process_entity(entity_name: str) -> Tuple[str, Dict[str, Any]]:
            async with semaphore:
                result = await self.link_entity(entity_name, language)
                await asyncio.sleep(0.1)  # 添加小延迟避免API限制
                return entity_name, result
        
        try:
            tasks = [process_entity(name) for name in entity_names]
            completed_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for item in completed_results:
                if isinstance(item, Exception):
                    logger.error(f"批量处理中出现异常: {item}")
                    continue
                    
                entity_name, result = item
                results[entity_name] = result
                
        except Exception as e:
            logger.error(f"批量实体链接失败: {e}")
        
        successful_links = sum(1 for result in results.values() if result.get('success', False))
        logger.info(f"批量实体链接完成，成功链接 {successful_links}/{len(entity_names)} 个实体")
        
        return results
    
    async def _search_wikidata_entity(self, entity_name: str, language: str, limit: int) -> List[Dict[str, Any]]:
        """
        在Wikidata中搜索实体
        
        Args:
            entity_name: 实体名称
            language: 语言代码
            limit: 结果数量限制
            
        Returns:
            搜索结果列表
        """
        search_url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbsearchentities',
            'search': entity_name,
            'language': language,
            'format': 'json',
            'limit': limit,
            'type': 'item'
        }
        
        try:
            async with self.session.get(search_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('search', [])
                else:
                    logger.error(f"Wikidata搜索API返回状态码: {response.status}")
                    return []
                    
        except asyncio.TimeoutError:
            logger.error("Wikidata搜索请求超时")
            return []
        except Exception as e:
            logger.error(f"Wikidata搜索请求失败: {e}")
            return []
    
    async def _get_wikidata_entity_details(self, wikidata_id: str, language: str) -> Optional[Dict[str, Any]]:
        """
        获取Wikidata实体的详细信息
        
        Args:
            wikidata_id: Wikidata实体ID
            language: 语言代码
            
        Returns:
            实体详细信息字典
        """
        details_url = "https://www.wikidata.org/w/api.php"
        params = {
            'action': 'wbgetentities',
            'ids': wikidata_id,
            'format': 'json',
            'languages': f'{language}|en',  # 同时获取指定语言和英文
            'props': 'labels|descriptions|aliases|claims'
        }
        
        try:
            async with self.session.get(details_url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    data = await response.json()
                    entities = data.get('entities', {})
                    entity_data = entities.get(wikidata_id, {})
                    
                    if not entity_data:
                        return None
                    
                    # 提取标签（优先指定语言，其次英文）
                    labels = entity_data.get('labels', {})
                    label = None
                    if language in labels:
                        label = labels[language]['value']
                    elif 'en' in labels:
                        label = labels['en']['value']
                    
                    # 提取描述（优先指定语言，其次英文）
                    descriptions = entity_data.get('descriptions', {})
                    description = None
                    if language in descriptions:
                        description = descriptions[language]['value']
                    elif 'en' in descriptions:
                        description = descriptions['en']['value']
                    
                    # 提取别名
                    aliases_data = entity_data.get('aliases', {})
                    aliases = []
                    if language in aliases_data:
                        aliases.extend([alias['value'] for alias in aliases_data[language]])
                    if 'en' in aliases_data and language != 'en':
                        aliases.extend([alias['value'] for alias in aliases_data['en']])
                    
                    # 提取重要属性
                    claims = entity_data.get('claims', {})
                    properties = self._extract_important_properties(claims)
                    
                    return {
                        'label': label,
                        'description': description,
                        'aliases': list(set(aliases)),  # 去重
                        'properties': properties
                    }
                else:
                    logger.error(f"Wikidata详情API返回状态码: {response.status}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("Wikidata详情请求超时")
            return None
        except Exception as e:
            logger.error(f"Wikidata详情请求失败: {e}")
            return None
    
    def _extract_important_properties(self, claims: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        从Wikidata声明中提取重要属性
        
        Args:
            claims: Wikidata声明数据
            
        Returns:
            重要属性字典
        """
        important_props = {
            'P31': 'instance_of',        # 是...的实例
            'P279': 'subclass_of',       # 是...的子类
            'P361': 'part_of',           # 是...的一部分
            'P17': 'country',            # 国家
            'P131': 'located_in',        # 位于
            'P106': 'occupation',        # 职业
            'P39': 'position_held',      # 担任职位
            'P101': 'field_of_work',     # 工作领域
            'P127': 'owned_by',          # 拥有者
            'P112': 'founded_by',        # 创立者
            'P571': 'inception',         # 成立时间
            'P576': 'dissolved',         # 解散时间
        }
        
        extracted = {}
        
        for prop_id, prop_name in important_props.items():
            if prop_id in claims:
                values = []
                for claim in claims[prop_id]:
                    try:
                        mainsnak = claim.get('mainsnak', {})
                        if mainsnak.get('snaktype') == 'value':
                            datavalue = mainsnak.get('datavalue', {})
                            value_type = datavalue.get('type')
                            
                            if value_type == 'wikibase-entityid':
                                # 实体引用，提取ID
                                entity_id = datavalue.get('value', {}).get('id')
                                if entity_id:
                                    values.append(entity_id)
                            elif value_type == 'string':
                                # 字符串值
                                string_value = datavalue.get('value')
                                if string_value:
                                    values.append(string_value)
                            elif value_type == 'time':
                                # 时间值
                                time_value = datavalue.get('value', {}).get('time')
                                if time_value:
                                    values.append(time_value)
                    except Exception as e:
                        logger.debug(f"处理属性 {prop_id} 时出错: {e}")
                        continue
                
                if values:
                    extracted[prop_name] = values
        
        return extracted
    
    def _calculate_match_confidence(self, input_name: str, entity_details: Dict[str, Any]) -> float:
        """
        计算实体匹配的置信度
        
        Args:
            input_name: 输入的实体名称
            entity_details: Wikidata实体详情
            
        Returns:
            置信度分数 (0.0 - 1.0)
        """
        try:
            input_name_lower = input_name.lower().strip()
            
            # 检查标签匹配
            label = entity_details.get('label', '').lower().strip()
            if input_name_lower == label:
                return 1.0
            
            # 检查别名匹配
            aliases = [alias.lower().strip() for alias in entity_details.get('aliases', [])]
            if input_name_lower in aliases:
                return 0.9
            
            # 计算字符串相似度（简单的Jaccard相似度）
            def jaccard_similarity(s1: str, s2: str) -> float:
                set1 = set(s1.split())
                set2 = set(s2.split())
                intersection = len(set1.intersection(set2))
                union = len(set1.union(set2))
                return intersection / union if union > 0 else 0.0
            
            # 与标签的相似度
            label_similarity = jaccard_similarity(input_name_lower, label)
            
            # 与别名的最高相似度
            alias_similarity = 0.0
            for alias in aliases:
                similarity = jaccard_similarity(input_name_lower, alias)
                alias_similarity = max(alias_similarity, similarity)
            
            # 返回最高相似度，但最少为0.1
            max_similarity = max(label_similarity, alias_similarity)
            return max(max_similarity, 0.1)
            
        except Exception as e:
            logger.error(f"计算匹配置信度时出错: {e}")
            return 0.1
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        logger.info("实体链接缓存已清空")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_entries = len(self.cache)
        successful_entries = sum(1 for result in self.cache.values() if result.get('success', False))
        
        return {
            'total_entries': total_entries,
            'successful_entries': successful_entries,
            'failed_entries': total_entries - successful_entries,
            'success_rate': successful_entries / total_entries if total_entries > 0 else 0.0
        }

# 便捷函数，用于不需要上下文管理器的简单用法
async def link_entity_simple(entity_name: str, language: str = "zh") -> Dict[str, Any]:
    """
    简单的实体链接函数，自动管理连接
    
    Args:
        entity_name: 实体名称
        language: 语言代码
        
    Returns:
        链接结果
    """
    async with EntityLinker() as linker:
        return await linker.link_entity(entity_name, language)

async def link_entities_batch_simple(entity_names: List[str], language: str = "zh") -> Dict[str, Dict[str, Any]]:
    """
    简单的批量实体链接函数，自动管理连接
    
    Args:
        entity_names: 实体名称列表
        language: 语言代码
        
    Returns:
        实体名称到链接结果的字典映射
    """
    async with EntityLinker() as linker:
        return await linker.link_entities_batch(entity_names, language) 