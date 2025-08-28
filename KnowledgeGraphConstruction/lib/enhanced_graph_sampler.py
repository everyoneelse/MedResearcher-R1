#!/usr/bin/env python3
"""
增强图采样器
实现复杂混合拓扑的采样算法，生成具有内在非线性复杂性的子图
支持三种高级采样策略：主干增强、社群核心路径、双核桥接
"""

import logging
import random
import networkx as nx
from typing import Dict, List, Any, Set, Tuple, Optional
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)

class SamplingAlgorithm(Enum):
    """采样算法枚举"""
    AUGMENTED_CHAIN = "augmented_chain"  # 主干增强采样
    COMMUNITY_CORE_PATH = "community_core_path"  # 社群核心路径采样
    DUAL_CORE_BRIDGE = "dual_core_bridge"  # 双核桥接采样
    MAX_CHAIN = "max_chain"  # 最长链采样
    MIXED = "mixed"  # 混合采样（随机选择）

class EnhancedGraphSampler:
    """增强图采样器"""
    
    def __init__(self):
        """初始化采样器"""
        # 采样参数配置
        self.config = {
            'min_path_length': 3,  # 最小路径长度
            'max_path_length': 6,  # 最大路径长度
            'augmentation_ratio': 0.5,  # 增强节点比例
            'community_depth': 2,  # 社群搜索深度
            'min_degree_for_core': 2,  # 核心节点最小度数
        }
    
    async def sample_complex_subgraph(
        self, 
        graph_info: Dict[str, Any], 
        sample_size: int,
        algorithm: SamplingAlgorithm = SamplingAlgorithm.MIXED
    ) -> Dict[str, Any]:
        """
        采样复杂混合拓扑子图
        
        Args:
            graph_info: 完整图信息
            sample_size: 目标采样大小
            algorithm: 采样算法选择
            
        Returns:
            采样结果字典
        """
        # 继承trace context（如果有的话）
        from .trace_manager import TraceManager, start_trace
        parent_trace = TraceManager.get_trace_id()
        if parent_trace:
            logger.info(f"图采样器继承trace: {parent_trace}")
        else:
            start_trace(prefix="sampling")
            logger.info(f"图采样器创建新trace")
        
        try:
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            if not entities or not relationships:
                logger.warning("图中没有足够的实体或关系，无法采样")
                return {'nodes': [], 'relations': [], 'algorithm': algorithm.value}
            
            # 构建NetworkX图
            G = self._build_networkx_graph(entities, relationships)
            
            if len(G.nodes()) < sample_size:
                logger.warning(f"图节点数({len(G.nodes())})小于采样大小({sample_size})")
                return self._fallback_sampling(entities, relationships, sample_size)
            
            # 根据算法选择执行采样
            if algorithm == SamplingAlgorithm.MIXED:
                # 随机选择一种算法
                algorithms = [SamplingAlgorithm.AUGMENTED_CHAIN, 
                            SamplingAlgorithm.COMMUNITY_CORE_PATH, 
                            SamplingAlgorithm.DUAL_CORE_BRIDGE,
                            SamplingAlgorithm.MAX_CHAIN]
                algorithm = random.choice(algorithms)
                logger.info(f"混合模式选择算法: {algorithm.value}")
            
            # 执行对应的采样算法
            if algorithm == SamplingAlgorithm.AUGMENTED_CHAIN:
                result = await self._augmented_chain_sampling(G, entities, relationships, sample_size)
            elif algorithm == SamplingAlgorithm.COMMUNITY_CORE_PATH:
                result = await self._community_core_path_sampling(G, entities, relationships, sample_size)
            elif algorithm == SamplingAlgorithm.DUAL_CORE_BRIDGE:
                result = await self._dual_core_bridge_sampling(G, entities, relationships, sample_size)
            elif algorithm == SamplingAlgorithm.MAX_CHAIN:
                result = await self._max_chain_sampling(G, entities, relationships, sample_size)
            else:
                # 默认回退到增强链采样
                result = await self._augmented_chain_sampling(G, entities, relationships, sample_size)
            
            result['algorithm'] = algorithm.value
            logger.info(f"采样完成，算法: {algorithm.value}, 节点: {len(result.get('nodes', []))}, 关系: {len(result.get('relations', []))}")
            
            return result
            
        except Exception as e:
            logger.error(f"复杂子图采样失败: {e}")
            return self._fallback_sampling(entities, relationships, sample_size)
    
    def _build_networkx_graph(self, entities: List[Dict], relationships: List[Dict]) -> nx.Graph:
        """构建NetworkX图"""
        G = nx.Graph()
        
        # 添加节点
        for entity in entities:
            node_id = entity.get('name') or entity.get('title') or str(entity.get('id', ''))
            G.add_node(node_id, **entity)
        
        # 添加边
        for rel in relationships:
            source = rel.get('source') or rel.get('head') or rel.get('from')
            target = rel.get('target') or rel.get('tail') or rel.get('to')
            
            if source and target and source in G.nodes() and target in G.nodes():
                G.add_edge(source, target, **rel)
        
        return G
    
    async def _augmented_chain_sampling(
        self, 
        G: nx.Graph, 
        entities: List[Dict], 
        relationships: List[Dict], 
        sample_size: int
    ) -> Dict[str, Any]:
        """
        算法一：主干增强采样 (Augmented Chain Sampling)
        先找到核心逻辑链，然后用相关节点来丰满它
        """
        try:
            # 1. 随机选择起始和结束节点（确保不直接连接）
            nodes = list(G.nodes())
            attempts = 0
            start_node, end_node = None, None
            
            while attempts < 10:  # 最多尝试10次
                start_node = random.choice(nodes)
                potential_ends = [n for n in nodes if n != start_node and not G.has_edge(start_node, n)]
                
                if potential_ends:
                    end_node = random.choice(potential_ends)
                    break
                attempts += 1
            
            if not end_node:
                # 如果找不到合适的起终点，随机选择
                start_node, end_node = random.sample(nodes, 2)
            
            # 2. 寻找主干路径
            try:
                backbone_path = nx.shortest_path(G, start_node, end_node)
            except nx.NetworkXNoPath:
                # 如果没有路径，选择连通的节点
                connected_nodes = list(nx.node_connected_component(G, start_node))
                if len(connected_nodes) >= 2:
                    end_node = random.choice([n for n in connected_nodes if n != start_node])
                    backbone_path = nx.shortest_path(G, start_node, end_node)
                else:
                    # 回退到简单路径
                    backbone_path = [start_node]
                    if len(connected_nodes) > 1:
                        backbone_path.append(random.choice([n for n in connected_nodes if n != start_node]))
            
            sampled_nodes = set(backbone_path)
            
            # 3. 增强节点：为主干上的每个节点添加邻居
            for backbone_node in backbone_path:
                neighbors = list(G.neighbors(backbone_node))
                # 排除已在主干中的节点
                available_neighbors = [n for n in neighbors if n not in sampled_nodes]
                
                # 为每个主干节点添加1-2个邻居
                num_to_add = min(
                    random.randint(1, 2), 
                    len(available_neighbors),
                    sample_size - len(sampled_nodes)
                )
                
                if num_to_add > 0:
                    selected_neighbors = random.sample(available_neighbors, num_to_add)
                    sampled_nodes.update(selected_neighbors)
                
                if len(sampled_nodes) >= sample_size:
                    break
            
            # 4. 构建结果
            result_nodes = [e for e in entities if e.get('name') in sampled_nodes]
            result_relations = self._get_relations_for_nodes(sampled_nodes, relationships)
            
            return {
                'nodes': result_nodes,
                'relations': result_relations,
                'sample_method': 'augmented_chain',
                'backbone_path': backbone_path,
                'sample_size': len(result_nodes),
                'topology_info': {
                    'has_main_path': True,
                    'path_length': len(backbone_path),
                    'augmented_nodes': len(sampled_nodes) - len(backbone_path)
                }
            }
            
        except Exception as e:
            logger.error(f"主干增强采样失败: {e}")
            return self._fallback_sampling(entities, relationships, sample_size)
    
    async def _community_core_path_sampling(
        self, 
        G: nx.Graph, 
        entities: List[Dict], 
        relationships: List[Dict], 
        sample_size: int
    ) -> Dict[str, Any]:
        """
        算法二：社群核心路径采样 (Community Core Path Sampling)
        先圈定复杂的局部网络，再寻找最长曲折路径
        """
        try:
            # 1. 选择高度连接的中心节点
            degrees = dict(G.degree())
            high_degree_nodes = [n for n, d in degrees.items() if d >= self.config['min_degree_for_core']]
            
            if not high_degree_nodes:
                high_degree_nodes = list(degrees.keys())
            
            center_node = max(high_degree_nodes, key=lambda n: degrees[n])
            
            # 2. 构建局部社群（多跳邻居）
            community_nodes = set([center_node])
            for depth in range(self.config['community_depth']):
                current_layer = set()
                for node in list(community_nodes):
                    neighbors = set(G.neighbors(node))
                    current_layer.update(neighbors)
                community_nodes.update(current_layer)
                
                if len(community_nodes) >= sample_size * 1.5:  # 控制社群大小
                    break
            
            # 限制社群大小
            if len(community_nodes) > sample_size * 2:
                community_nodes = set(random.sample(list(community_nodes), int(sample_size * 1.5)))
            
            # 3. 在社群内寻找最长简单路径
            community_subgraph = G.subgraph(community_nodes)
            longest_path = []
            max_length = 0
            
            # 尝试多个起点寻找最长路径
            sample_nodes = random.sample(list(community_nodes), min(5, len(community_nodes)))
            
            for start in sample_nodes:
                for end in community_nodes:
                    if start != end:
                        try:
                            path = nx.shortest_path(community_subgraph, start, end)
                            if len(path) > max_length:
                                max_length = len(path)
                                longest_path = path
                        except nx.NetworkXNoPath:
                            continue
            
            # 4. 如果路径太短，尝试增加节点
            if len(longest_path) < self.config['min_path_length']:
                # 添加更多社群节点
                additional_nodes = community_nodes - set(longest_path)
                num_to_add = min(len(additional_nodes), sample_size - len(longest_path))
                if num_to_add > 0:
                    longest_path.extend(random.sample(list(additional_nodes), num_to_add))
            
            # 5. 最终采样节点
            sampled_nodes = set(longest_path[:sample_size])
            
            # 确保包含足够的节点
            if len(sampled_nodes) < sample_size:
                remaining_community = community_nodes - sampled_nodes
                if remaining_community:
                    need_more = sample_size - len(sampled_nodes)
                    additional = random.sample(list(remaining_community), min(need_more, len(remaining_community)))
                    sampled_nodes.update(additional)
            
            # 6. 构建结果
            result_nodes = [e for e in entities if e.get('name') in sampled_nodes]
            result_relations = self._get_relations_for_nodes(sampled_nodes, relationships)
            
            return {
                'nodes': result_nodes,
                'relations': result_relations,
                'sample_method': 'community_core_path',
                'core_path': longest_path,
                'community_center': center_node,
                'sample_size': len(result_nodes),
                'topology_info': {
                    'has_main_path': True,
                    'core_path_length': len(longest_path),
                    'community_size': len(community_nodes),
                    'is_dense_subgraph': True
                }
            }
            
        except Exception as e:
            logger.error(f"社群核心路径采样失败: {e}")
            return self._fallback_sampling(entities, relationships, sample_size)
    
    async def _dual_core_bridge_sampling(
        self, 
        G: nx.Graph, 
        entities: List[Dict], 
        relationships: List[Dict], 
        sample_size: int
    ) -> Dict[str, Any]:
        """
        算法三：双核桥接采样 (Dual-Core Bridge Sampling)
        创造包含多个中心和复杂连接的子图
        """
        try:
            # 1. 找到两个高度连接但不直接相连的核心节点
            degrees = dict(G.degree())
            high_degree_nodes = sorted(degrees.items(), key=lambda x: x[1], reverse=True)
            
            core1, core2 = None, None
            
            # 选择度数高且不直接连接的两个节点
            for i, (node1, _) in enumerate(high_degree_nodes):
                for node2, _ in high_degree_nodes[i+1:]:
                    if not G.has_edge(node1, node2):
                        core1, core2 = node1, node2
                        break
                if core1 and core2:
                    break
            
            # 如果找不到合适的双核，随机选择两个节点
            if not core1 or not core2:
                nodes = list(G.nodes())
                core1, core2 = random.sample(nodes, 2)
            
            # 2. 寻找桥接路径
            try:
                bridge_path = nx.shortest_path(G, core1, core2)
            except nx.NetworkXNoPath:
                # 如果没有路径，在各自的连通分量中工作
                comp1 = nx.node_connected_component(G, core1)
                comp2 = nx.node_connected_component(G, core2)
                bridge_path = [core1, core2]  # 简化处理
            
            # 3. 收集双核的邻居
            core1_neighbors = set(G.neighbors(core1))
            core2_neighbors = set(G.neighbors(core2))
            
            # 4. 构建最终的采样节点集
            sampled_nodes = set(bridge_path)  # 包含桥接路径
            
            # 添加核心1的邻居
            remaining_quota = sample_size - len(sampled_nodes)
            if remaining_quota > 0:
                available_neighbors1 = core1_neighbors - sampled_nodes
                num_from_core1 = min(len(available_neighbors1), remaining_quota // 2)
                if num_from_core1 > 0:
                    selected1 = random.sample(list(available_neighbors1), num_from_core1)
                    sampled_nodes.update(selected1)
            
            # 添加核心2的邻居
            remaining_quota = sample_size - len(sampled_nodes)
            if remaining_quota > 0:
                available_neighbors2 = core2_neighbors - sampled_nodes
                num_from_core2 = min(len(available_neighbors2), remaining_quota)
                if num_from_core2 > 0:
                    selected2 = random.sample(list(available_neighbors2), num_from_core2)
                    sampled_nodes.update(selected2)
            
            # 5. 如果还需要更多节点，从整个图中添加
            if len(sampled_nodes) < sample_size:
                all_neighbors = (core1_neighbors | core2_neighbors) - sampled_nodes
                remaining_quota = sample_size - len(sampled_nodes)
                if all_neighbors and remaining_quota > 0:
                    additional = random.sample(list(all_neighbors), min(remaining_quota, len(all_neighbors)))
                    sampled_nodes.update(additional)
            
            # 6. 构建结果
            result_nodes = [e for e in entities if e.get('name') in sampled_nodes]
            result_relations = self._get_relations_for_nodes(sampled_nodes, relationships)
            
            return {
                'nodes': result_nodes,
                'relations': result_relations,
                'sample_method': 'dual_core_bridge',
                'core1': core1,
                'core2': core2,
                'bridge_path': bridge_path,
                'sample_size': len(result_nodes),
                'topology_info': {
                    'has_dual_cores': True,
                    'bridge_path_length': len(bridge_path),
                    'core1_degree': degrees.get(core1, 0),
                    'core2_degree': degrees.get(core2, 0),
                    'is_complex_network': True
                }
            }
            
        except Exception as e:
            logger.error(f"双核桥接采样失败: {e}")
            return self._fallback_sampling(entities, relationships, sample_size)
    
    async def _max_chain_sampling(
        self, 
        G: nx.Graph, 
        entities: List[Dict], 
        relationships: List[Dict], 
        sample_size: int
    ) -> Dict[str, Any]:
        """
        算法四：最长链采样 (Max Chain Sampling)
        以尽可能长的逻辑链为核心，在此基础上对链条的邻居进行随机拓展
        """
        try:
            nodes = list(G.nodes())
            if len(nodes) < 2:
                return self._fallback_sampling(entities, relationships, sample_size)
            
            # 1. 寻找图中的最长路径
            max_chain = []
            max_length = 0
            
            logger.info("开始寻找最长链...")
            
            # 由于寻找最长路径是NP-hard问题，我们使用启发式方法
            # 从多个节点开始，找到最长的简单路径
            for start_node in random.sample(nodes, min(10, len(nodes))):  # 限制搜索起点数量
                current_chain = self._find_longest_path_from_node(G, start_node, sample_size // 2)
                if len(current_chain) > max_length:
                    max_length = len(current_chain)
                    max_chain = current_chain
            
            logger.info(f"找到最长链，长度: {max_length}, 路径: {' -> '.join(max_chain)}")
            
            # 2. 以最长链为核心，添加邻居节点
            sampled_nodes = set(max_chain)
            chain_nodes = set(max_chain)
            
            # 3. 为链条上的每个节点添加邻居（随机拓展）
            remaining_quota = sample_size - len(sampled_nodes)
            
            if remaining_quota > 0:
                # 收集所有链条节点的邻居
                chain_neighbors = set()
                for chain_node in chain_nodes:
                    neighbors = set(G.neighbors(chain_node)) - sampled_nodes
                    chain_neighbors.update(neighbors)
                
                # 随机选择邻居节点进行拓展
                if chain_neighbors:
                    num_neighbors_to_add = min(remaining_quota, len(chain_neighbors))
                    selected_neighbors = random.sample(list(chain_neighbors), num_neighbors_to_add)
                    sampled_nodes.update(selected_neighbors)
                    logger.info(f"为链条添加了 {len(selected_neighbors)} 个邻居节点")
            
            # 4. 如果还需要更多节点，进行二阶邻居拓展
            remaining_quota = sample_size - len(sampled_nodes)
            if remaining_quota > 0:
                second_order_neighbors = set()
                for node in sampled_nodes:
                    for neighbor in G.neighbors(node):
                        if neighbor not in sampled_nodes:
                            second_order_neighbors.update(set(G.neighbors(neighbor)) - sampled_nodes)
                
                if second_order_neighbors:
                    num_second_order = min(remaining_quota, len(second_order_neighbors))
                    selected_second_order = random.sample(list(second_order_neighbors), num_second_order)
                    sampled_nodes.update(selected_second_order)
                    logger.info(f"添加了 {len(selected_second_order)} 个二阶邻居节点")
            
            # 5. 构建结果
            result_nodes = [e for e in entities if e.get('name') in sampled_nodes]
            result_relations = self._get_relations_for_nodes(sampled_nodes, relationships)
            
            return {
                'nodes': result_nodes,
                'relations': result_relations,
                'sample_method': 'max_chain',
                'max_chain': max_chain,
                'chain_length': len(max_chain),
                'sample_size': len(result_nodes),
                'topology_info': {
                    'has_long_chain': True,
                    'chain_length': len(max_chain),
                    'chain_coverage': len(max_chain) / len(sampled_nodes),
                    'neighbor_expansion_ratio': (len(sampled_nodes) - len(max_chain)) / len(sampled_nodes) if len(sampled_nodes) > 0 else 0,
                    'is_chain_centered': True
                }
            }
            
        except Exception as e:
            logger.error(f"最长链采样失败: {e}")
            return self._fallback_sampling(entities, relationships, sample_size)
    
    def _find_longest_path_from_node(self, G: nx.Graph, start_node: str, max_length: int) -> List[str]:
        """
        从指定节点开始，使用深度优先搜索找到最长简单路径
        限制搜索深度以避免过长的计算时间
        """
        def dfs(current_node: str, visited: Set[str], path: List[str]) -> List[str]:
            if len(path) >= max_length:  # 限制路径长度
                return path[:]
            
            longest_path = path[:]
            
            for neighbor in G.neighbors(current_node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = path + [neighbor]
                    candidate_path = dfs(neighbor, visited, new_path)
                    
                    if len(candidate_path) > len(longest_path):
                        longest_path = candidate_path
                    
                    visited.remove(neighbor)
            
            return longest_path
        
        visited = {start_node}
        return dfs(start_node, visited, [start_node])
    
    def _get_relations_for_nodes(self, sampled_nodes: Set[str], relationships: List[Dict]) -> List[Dict]:
        """获取采样节点之间的所有关系"""
        sampled_relations = []
        
        for relation in relationships:
            source = relation.get('source') or relation.get('head') or relation.get('from')
            target = relation.get('target') or relation.get('tail') or relation.get('to')
            
            if source in sampled_nodes and target in sampled_nodes:
                sampled_relations.append(relation)
        
        return sampled_relations
    
    def _fallback_sampling(self, entities: List[Dict], relationships: List[Dict], sample_size: int) -> Dict[str, Any]:
        """回退采样方法"""
        try:
            # 简单随机采样
            sampled_entities = random.sample(entities, min(sample_size, len(entities)))
            sampled_node_names = {entity.get('name') for entity in sampled_entities}
            sampled_relations = self._get_relations_for_nodes(sampled_node_names, relationships)
            
            return {
                'nodes': sampled_entities,
                'relations': sampled_relations,
                'sample_method': 'fallback_random',
                'sample_size': len(sampled_entities),
                'topology_info': {
                    'is_fallback': True
                }
            }
        except Exception as e:
            logger.error(f"回退采样也失败: {e}")
            return {'nodes': [], 'relations': [], 'sample_method': 'failed'}
    
    def analyze_topology(self, sample_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析采样结果的拓扑结构"""
        try:
            nodes = sample_result.get('nodes', [])
            relations = sample_result.get('relations', [])
            
            if not nodes or not relations:
                return {'analysis': 'empty_graph'}
            
            # 基本统计
            analysis = {
                'total_nodes': len(nodes),
                'total_edges': len(relations),
                'algorithm_used': sample_result.get('sample_method', 'unknown'),
                'topology_complexity': 'low'
            }
            
            # 构建简单图进行分析
            node_names = {n.get('name') for n in nodes}
            edges = []
            for rel in relations:
                source = rel.get('source') or rel.get('head') or rel.get('from')
                target = rel.get('target') or rel.get('tail') or rel.get('to')
                if source in node_names and target in node_names:
                    edges.append((source, target))
            
            # 计算度分布
            degree_dist = defaultdict(int)
            for source, target in edges:
                degree_dist[source] += 1
                degree_dist[target] += 1
            
            if degree_dist:
                degrees = list(degree_dist.values())
                analysis.update({
                    'avg_degree': sum(degrees) / len(degrees),
                    'max_degree': max(degrees),
                    'degree_variance': self._calculate_variance(degrees)
                })
                
                # 判断复杂度
                if analysis['max_degree'] >= 3 and analysis['degree_variance'] > 1:
                    analysis['topology_complexity'] = 'high'
                elif analysis['max_degree'] >= 2:
                    analysis['topology_complexity'] = 'medium'
            
            # 添加算法特定信息
            analysis.update(sample_result.get('topology_info', {}))
            
            return analysis
            
        except Exception as e:
            logger.error(f"拓扑分析失败: {e}")
            return {'analysis': 'failed', 'error': str(e)}
    
    def _calculate_variance(self, values: List[int]) -> float:
        """计算方差"""
        if not values:
            return 0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values) 