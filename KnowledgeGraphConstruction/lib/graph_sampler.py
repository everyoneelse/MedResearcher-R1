#!/usr/bin/env python3
"""
图采样器
用于从知识图谱中采样连通子图
"""

import logging
import random
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class GraphSampler:
    """图采样器"""
    
    def __init__(self):
        """初始化采样器"""
        pass
    
    async def sample_connected_subgraph(self, graph_info: Dict[str, Any], sample_size: int) -> Dict[str, Any]:
        """采样连通子图"""
        try:
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            if not entities or not relationships:
                logger.warning("图中没有实体或关系，无法采样")
                return {'nodes': [], 'relations': []}
            
            # 构建图结构
            graph = self._build_graph_structure(entities, relationships)
            
            # 选择起始节点
            start_node = self._select_start_node(graph, entities)
            
            # 使用 BFS 采样连通子图
            sampled_nodes = self._bfs_sample(graph, start_node, sample_size)
            
            # 获取采样节点之间的关系
            sampled_relations = self._get_sampled_relations(sampled_nodes, relationships)
            
            # 构建结果
            result = {
                'nodes': [entity for entity in entities if entity.get('name') in sampled_nodes],
                'relations': sampled_relations,
                'sample_method': 'connected_subgraph',
                'start_node': start_node,
                'sample_size': len(sampled_nodes)
            }
            
            logger.info(f"采样了 {len(sampled_nodes)} 个节点和 {len(sampled_relations)} 个关系")
            return result
            
        except Exception as e:
            logger.error(f"采样连通子图失败: {e}")
            return {'nodes': [], 'relations': []}
    
    def _build_graph_structure(self, entities: List[Dict], relationships: List[Dict]) -> Dict[str, Set[str]]:
        """构建图结构"""
        graph = defaultdict(set)
        
        # 添加所有实体作为节点
        for entity in entities:
            node_name = entity.get('name') or entity.get('title') or str(entity.get('id', ''))
            if node_name:
                graph[node_name] = set()
        
        # 添加关系作为边
        for relation in relationships:
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            
            if source and target:
                graph[source].add(target)
                graph[target].add(source)  # 无向图
        
        return dict(graph)
    
    def _select_start_node(self, graph: Dict[str, Set[str]], entities: List[Dict]) -> str:
        """选择起始节点"""
        if not graph:
            return ""
        
        # 计算节点的度
        node_degrees = [(node, len(neighbors)) for node, neighbors in graph.items()]
        
        # 选择度适中的节点作为起始点（不是度最高的，也不是度最低的）
        node_degrees.sort(key=lambda x: x[1], reverse=True)
        
        # 选择度在中等范围的节点
        mid_range_start = len(node_degrees) // 4
        mid_range_end = 3 * len(node_degrees) // 4
        
        if mid_range_start < mid_range_end:
            candidates = node_degrees[mid_range_start:mid_range_end]
        else:
            candidates = node_degrees
        
        # 从候选节点中随机选择
        selected_node = random.choice(candidates)[0]
        
        logger.info(f"选择起始节点: {selected_node}")
        return selected_node
    
    def _bfs_sample(self, graph: Dict[str, Set[str]], start_node: str, sample_size: int) -> Set[str]:
        """使用 BFS 采样连通子图"""
        if not start_node or start_node not in graph:
            # 如果起始节点不存在，随机选择一个
            if graph:
                start_node = random.choice(list(graph.keys()))
            else:
                return set()
        
        visited = set()
        queue = deque([start_node])
        visited.add(start_node)
        
        while queue and len(visited) < sample_size:
            current = queue.popleft()
            
            # 获取邻居节点
            neighbors = list(graph.get(current, set()))
            
            # 随机打乱邻居顺序
            random.shuffle(neighbors)
            
            # 添加未访问的邻居
            for neighbor in neighbors:
                if neighbor not in visited and len(visited) < sample_size:
                    visited.add(neighbor)
                    queue.append(neighbor)
        
        return visited
    
    def _get_sampled_relations(self, sampled_nodes: Set[str], relationships: List[Dict]) -> List[Dict]:
        """获取采样节点之间的关系"""
        sampled_relations = []
        
        for relation in relationships:
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            
            if source in sampled_nodes and target in sampled_nodes:
                sampled_relations.append(relation)
        
        return sampled_relations
    
    async def sample_random_nodes(self, graph_info: Dict[str, Any], sample_size: int) -> Dict[str, Any]:
        """随机采样节点"""
        try:
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            if not entities:
                return {'nodes': [], 'relations': []}
            
            # 随机选择节点
            sampled_entities = random.sample(entities, min(sample_size, len(entities)))
            sampled_node_names = {entity.get('name') or entity.get('title') or str(entity.get('id', '')) for entity in sampled_entities}
            
            # 获取采样节点之间的关系
            sampled_relations = self._get_sampled_relations(sampled_node_names, relationships)
            
            result = {
                'nodes': sampled_entities,
                'relations': sampled_relations,
                'sample_method': 'random_nodes',
                'sample_size': len(sampled_entities)
            }
            
            logger.info(f"随机采样了 {len(sampled_entities)} 个节点和 {len(sampled_relations)} 个关系")
            return result
            
        except Exception as e:
            logger.error(f"随机采样节点失败: {e}")
            return {'nodes': [], 'relations': []}
    
    async def sample_high_degree_nodes(self, graph_info: Dict[str, Any], sample_size: int) -> Dict[str, Any]:
        """采样高度节点"""
        try:
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            if not entities or not relationships:
                return {'nodes': [], 'relations': []}
            
            # 计算节点度
            node_degrees = defaultdict(int)
            for relation in relationships:
                source = relation.get('source') or relation.get('head') or relation.get('from')
                target = relation.get('target') or relation.get('tail') or relation.get('to')
                
                if source:
                    node_degrees[source] += 1
                if target:
                    node_degrees[target] += 1
            
            # 按度排序
            sorted_nodes = sorted(node_degrees.items(), key=lambda x: x[1], reverse=True)
            
            # 选择高度节点
            high_degree_node_names = [node for node, degree in sorted_nodes[:sample_size]]
            
            # 获取对应的实体
            sampled_entities = []
            for entity in entities:
                entity_name = entity.get('name') or entity.get('title') or str(entity.get('id', ''))
                if entity_name in high_degree_node_names:
                    sampled_entities.append(entity)
            
            # 获取采样节点之间的关系
            sampled_relations = self._get_sampled_relations(set(high_degree_node_names), relationships)
            
            result = {
                'nodes': sampled_entities,
                'relations': sampled_relations,
                'sample_method': 'high_degree_nodes',
                'sample_size': len(sampled_entities)
            }
            
            logger.info(f"采样了 {len(sampled_entities)} 个高度节点和 {len(sampled_relations)} 个关系")
            return result
            
        except Exception as e:
            logger.error(f"采样高度节点失败: {e}")
            return {'nodes': [], 'relations': []}
    
    def get_graph_statistics(self, graph_info: Dict[str, Any]) -> Dict[str, Any]:
        """获取图统计信息"""
        try:
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            # 基本统计
            stats = {
                'total_nodes': len(entities),
                'total_relations': len(relationships),
                'node_types': defaultdict(int),
                'relation_types': defaultdict(int)
            }
            
            # 节点类型统计
            for entity in entities:
                node_type = entity.get('type') or entity.get('category') or 'unknown'
                stats['node_types'][node_type] += 1
            
            # 关系类型统计
            for relation in relationships:
                relation_type = relation.get('type') or relation.get('relation') or relation.get('label') or 'unknown'
                stats['relation_types'][relation_type] += 1
            
            # 度统计
            node_degrees = defaultdict(int)
            for relation in relationships:
                source = relation.get('source') or relation.get('head') or relation.get('from')
                target = relation.get('target') or relation.get('tail') or relation.get('to')
                
                if source:
                    node_degrees[source] += 1
                if target:
                    node_degrees[target] += 1
            
            if node_degrees:
                degrees = list(node_degrees.values())
                stats['avg_degree'] = sum(degrees) / len(degrees)
                stats['max_degree'] = max(degrees)
                stats['min_degree'] = min(degrees)
            else:
                stats['avg_degree'] = 0
                stats['max_degree'] = 0
                stats['min_degree'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"获取图统计信息失败: {e}")
            return {'total_nodes': 0, 'total_relations': 0} 