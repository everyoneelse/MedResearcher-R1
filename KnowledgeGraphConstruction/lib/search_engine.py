import logging
import time
import random
from typing import List, Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

class SearchEngine:
    """基于Tavily API的搜索引擎"""
    
    def __init__(self):
        """初始化搜索引擎"""
        self.api_key = settings.TAVILY_API_KEY
        self.max_results = settings.SEARCH_RESULTS_LIMIT
        
        # 检查API密钥配置
        if not self.api_key:
            logger.warning("Tavily API Key 未配置，将使用模拟结果")
        
        # 初始化Tavily客户端
        self.client = None
        if self.api_key:
            try:
                from tavily import TavilyClient
                self.client = TavilyClient(self.api_key)
                logger.info("Tavily 搜索引擎初始化成功")
            except ImportError:
                logger.error("未安装tavily-python包，请运行: pip install tavily-python")
            except Exception as e:
                logger.error(f"初始化Tavily客户端失败: {e}")
    
    async def search(self, query: str, start: int = 1, limit: int = None) -> List[Dict[str, Any]]:
        """搜索指定查询词并返回结果"""
        try:
            logger.info(f"搜索查询: {query}")
            
            # 确定结果数量
            num_results = limit if limit is not None else self.max_results
            
            if self.client:
                return await self._search_with_tavily(query, num_results)
            else:
                logger.warning("Tavily客户端未初始化，使用模拟结果")
                return await self._generate_mock_results(query, num_results)
                
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return await self._generate_mock_results(query, num_results)
    
    async def _search_with_tavily(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """使用Tavily API搜索"""
        try:
            logger.info(f"使用Tavily搜索: {query}")
            
            # 使用asyncio.to_thread将同步调用转为异步
            import asyncio
            response = await asyncio.to_thread(
                self.client.search,
                query=query,
                max_results=num_results,
                include_answer=False,
                include_images=False,
                include_raw_content=True  # 新增：获取原始内容
            )
            
            # 解析结果
            results = []
            tavily_results = response.get('results', [])
            
            for item in tavily_results:
                # 优先使用 raw_content，如果没有则使用 content
                raw_content = item.get('raw_content', '')
                content = item.get('content', '')
                preferred_content = raw_content if raw_content else content
                
                result = {
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'snippet': preferred_content[:200] + '...' if len(preferred_content) > 200 else preferred_content,
                    'content': preferred_content,  # 使用优选的内容
                    'raw_content': raw_content,    # 保留原始内容字段
                    'source': 'tavily',
                    'score': item.get('score', 0.0),
                    'displayLink': self._extract_domain(item.get('url', '')),
                    'formattedUrl': item.get('url', '')
                }
                results.append(result)
            
            logger.info(f"Tavily搜索完成，获得 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"Tavily搜索失败: {e}")
            return await self._generate_mock_results(query, num_results)
    
    def extract_content(self, urls: List[str]) -> List[Dict[str, Any]]:
        """使用Tavily API提取网页内容"""
        try:
            if not self.client:
                logger.warning("Tavily客户端未初始化，无法提取内容")
                return []
            
            logger.info(f"提取网页内容: {len(urls)} 个URL")
            
            # 调用Tavily提取API
            response = self.client.extract(urls=urls)
            
            # 解析结果
            results = []
            extract_results = response.get('results', [])
            
            for item in extract_results:
                result = {
                    'url': item.get('url', ''),
                    'content': item.get('raw_content', ''),
                    'images': item.get('images', [])
                }
                results.append(result)
            
            logger.info(f"内容提取完成，获得 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"内容提取失败: {e}")
            return []
    
    def _extract_domain(self, url: str) -> str:
        """从URL中提取域名"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ""
    
    async def _generate_mock_results(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """生成模拟搜索结果（当API不可用时使用）"""
        logger.info(f"使用模拟搜索结果: {query}")
        
        # 生成更真实的模拟内容
        mock_content_templates = [
            f"{query}是一个重要的概念，在现代科学技术发展中发挥着关键作用。研究表明，{query}的应用领域非常广泛，包括医疗、工程、信息技术等多个方面。通过深入分析{query}的特点和机制，我们可以更好地理解其在各个领域的应用价值。",
            f"关于{query}的最新研究显示，这一技术正在快速发展。专家指出，{query}具有巨大的发展潜力，未来可能在多个行业产生重大影响。目前，{query}的主要应用包括数据处理、自动化控制、智能分析等方面。",
            f"{query}的发展历程可以追溯到数十年前。随着技术的不断进步，{query}已经成为现代科技的重要组成部分。最新的研究成果表明，{query}在提高效率、降低成本、增强安全性等方面具有显著优势。"
        ]
        
        mock_results = []
        for i in range(min(num_results, len(mock_content_templates))):
            content = mock_content_templates[i]
            mock_results.append({
                'title': f'{query} - 权威资料 {i+1}',
                'url': f'https://example-{i+1}.com/{query}',
                'snippet': content[:150] + '...',
                'content': content,
                'displayLink': f'example-{i+1}.com',
                'formattedUrl': f'https://example-{i+1}.com/{query}',
                'source': 'mock',
                'score': 0.9 - i * 0.1
            })
        
        # 如果需要更多结果，重复使用模板
        while len(mock_results) < num_results:
            idx = len(mock_results)
            template_idx = idx % len(mock_content_templates)
            content = mock_content_templates[template_idx]
            
            mock_results.append({
                'title': f'{query} - 相关资料 {idx+1}',
                'url': f'https://source-{idx+1}.com/{query}',
                'snippet': content[:150] + '...',
                'content': content,
                'displayLink': f'source-{idx+1}.com',
                'formattedUrl': f'https://source-{idx+1}.com/{query}',
                'source': 'mock',
                'score': max(0.1, 0.9 - idx * 0.1)
            })
        
        return mock_results[:num_results]
    
    async def get_search_contents(self, query: str, limit: int = 3) -> List[str]:
        """获取搜索结果的内容文本（按照用户要求的逻辑）"""
        try:
            # 调用搜索
            search_results = await self.search(query, limit=limit)
            
            # 提取前三个结果的content字段（现在优先使用raw_content）
            contents = []
            for result in search_results[:limit]:
                content = result.get('content', '').strip()
                if content:
                    contents.append(content)
            
            logger.info(f"搜索查询 '{query}' 获得 {len(contents)} 个内容")
            return contents
            
        except Exception as e:
            logger.error(f"获取搜索内容失败: {e}")
            return []
    
    def batch_search(self, queries: List[str]) -> Dict[str, List[str]]:
        """批量搜索多个查询词，返回内容文本"""
        results = {}
        
        for query in queries:
            # 添加随机延迟以避免被限制
            time.sleep(random.uniform(0.5, 1.5))
            
            contents = self.get_search_contents(query, limit=3)  # 改回默认值3
            results[query] = contents
            
            logger.info(f"查询 '{query}' 完成，获得 {len(contents)} 个内容")
        
        return results 