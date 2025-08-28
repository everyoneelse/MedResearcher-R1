import sys
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Union
import requests
from functools import lru_cache
from time import sleep


class ToolServiceError(Exception):
    """Custom exception for tool service errors"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


def detect_language(text: str) -> str:
    """Simple language detection"""
    # Count Chinese characters
    chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    total_chars = len(text)
    
    if total_chars == 0:
        return "en"
    
    # If more than 30% are Chinese characters, consider it Chinese
    if chinese_chars / total_chars > 0.3:
        return "zh"
    else:
        return "en"


# Domain filtering configuration
FILTERED_DOMAINS = {
    "huggingface.co/datasets",
    # Add more domains to filter as needed
}




class SearchTool:
    """
    Search tool for performing web searches.
    Adapted for langgraph from the original search tool.
    """
    
    def __init__(self, description, parameters, domain_filter=None, **kwargs):
        self.name = "search"
        # Set default max_queries to 3 if not provided
        self.max_queries = 10
        # Handle domain_filter - can be None, list, or set
        if domain_filter is None:
            self.domain_filter = set()
        elif isinstance(domain_filter, list):
            self.domain_filter = set(domain_filter)
        else:
            self.domain_filter = domain_filter
        
        # Format description with current config values
        self.description = description
        
        # Store parameters configuration
        self.parameters = parameters
    
    def __call__(self, query: Union[str, List[str]]) -> str:
        """
        Call method for langgraph compatibility

        Args:
            query: Search query string or list of query strings

        Returns:
            str: Search results formatted as text
        """

        def search_by_language(q):
            # Convert domain_filter to tuple for caching compatibility
            domain_filter_tuple = tuple(sorted(self.domain_filter)) if self.domain_filter else ()
            if detect_language(q) == "zh":
                return self.serper_search(q, "cn", domain_filter_tuple)
            else:
                return self.serper_search(q, "en", domain_filter_tuple)

        if isinstance(query, str):
            response = search_by_language(query)
        else:
            # 为每个query根据语言选择对应的搜索引擎，根据max_queries参数处理查询
            with ThreadPoolExecutor(max_workers=self.max_queries) as executor:
                response = list(executor.map(search_by_language, query[:self.max_queries]))
            response = "\n=======\n".join(response)
        return response

    @staticmethod
    @lru_cache(maxsize=100)  # Cache recent 100 different query results
    def serper_search(query: str, default_country="en", domain_filter=None):
        url = 'https://google.serper.dev/search'
        headers = {
            'X-API-KEY': os.getenv("GOOGLE_SEARCH_KEY"),
            'Content-Type': 'application/json',
        }
        data = {
            "q": query,
            "num": 10,
        }
        # if default_country != "en":
        #     data["gl"] = default_country
        max_tries = 5
        for i in range(max_tries):
            try:
                response = requests.post(url, headers=headers, data=json.dumps(data))
                if response.status_code != 200:
                    raise ToolServiceError(message=f"Error: {response.status_code} - {response.text}")
                results = response.json()
                break
            except ToolServiceError as e:
                raise e
            except Exception as e:
                # print(e)
                if i == max_tries-1:
                    raise ToolServiceError(message="Google search Timeout, return None, Please try again later.")

        try:
            if "organic" not in results:
                raise Exception(f"No results found for query: '{query}'. Use a less specific query.")

            web_snippets = list()
            idx = 0
            filtered_count = 0
            total_results = len(results.get("organic", []))

            # Handle domain_filter parameter
            if domain_filter is None:
                domain_filter = set()
            elif isinstance(domain_filter, (list, tuple)):
                domain_filter = set(domain_filter)
            
            # print(f"🔍 [搜索] 查询: '{query}' - 原始结果: {total_results}个")
            # if domain_filter:
                # print(f"🚫 [过滤] 启用域名过滤，过滤列表: {list(domain_filter)}")

            if "organic" in results:
                for page in results["organic"]:
                    # 检查链接是否包含被过滤的域名
                    page_link = page.get('link', '')
                    is_filtered = any(domain in page_link for domain in domain_filter)

                    if is_filtered:
                        # 跳过被过滤的域名
                        filtered_count += 1
                        filtered_domain = next(domain for domain in domain_filter if domain in page_link)
                        # print(f"🚫 [过滤] 跳过域名 '{filtered_domain}': {page.get('title', 'Unknown')} - {page_link}")
                        continue

                    idx += 1
                    date_published = ""
                    if "date" in page:
                        date_published = "\nDate published: " + page["date"]

                    source = ""
                    if "source" in page:
                        source = "\nSource: " + page["source"]

                    snippet = ""
                    if "snippet" in page:
                        snippet = "\n" + page["snippet"]

                    redacted_version = f"{idx}. [{page['title']}]({page['link']}){date_published}{source}\n{snippet}"

                    redacted_version = redacted_version.replace("Your browser can't play this video.", "")
                    web_snippets.append(redacted_version)

            # print(f"✅ [结果] 过滤完成 - 原始: {total_results}个, 过滤: {filtered_count}个, 返回: {len(web_snippets)}个")

            content = f"A Google search for '{query}' found {len(web_snippets)} results:\n\n## Web Results\n" + "\n\n".join(web_snippets)
            return content
        except:
            return f"No results found for '{query}'. Try with a more general query, or remove the year filter."

    @classmethod
    def clear_cache(cls):
        """Clear search cache"""
        cls.serper_search.cache_clear()

    @classmethod
    def get_cache_info(cls):
        """Get cache information"""
        return cls.serper_search.cache_info()


if __name__ == "__main__":
    search_tool = SearchTool("", "", domain_filter=FILTERED_DOMAINS)
    params = {"query": ["王紫萱 直播平台 花火 原创歌曲", "花火 专辑名 乐队", "汪峰 花火 专辑", "王紫萱 中文昵称", "紫萱 直播艺人"]}
    params = {"query": ["test1", "test2", "test3"]}
    params = {"query": ["动画电影获多项短片拓展到长片 中国 顶级团队 亲情 传统文化 现代思想 少数民族 音乐节目 上映时间 调整"]}
    start_time = time.time()
    result = search_tool(params["query"])

    # 验证结果
    print(result)
    print("Run Duration: ", time.time()-start_time)