#!/usr/bin/env python3
"""
文本处理器 - 简化版本
用于基本的文本清理和处理，不依赖 NLTK
"""

import re
import logging
import requests
from typing import List, Optional
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)

class TextProcessor:
    """文本处理器 - 简化版本"""
    
    def __init__(self):
        """初始化处理器"""
        # 基本的英文停用词
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your',
            'his', 'her', 'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours', 'theirs'
        }
    
    async def extract_and_clean_text(self, url: str) -> Optional[str]:
        """从 URL 提取和清理文本"""
        try:
            # 发送请求
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # 解析 HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 转换为文本
            text = soup.get_text(separator=' ', strip=True)
            
            # 清理文本
            cleaned_text = self._clean_text(text)
            
            # 检查文本长度
            if len(cleaned_text) < settings.MIN_TEXT_LENGTH:
                return None
            
            # 截断过长的文本
            if len(cleaned_text) > settings.MAX_CHUNK_SIZE:
                cleaned_text = cleaned_text[:settings.MAX_CHUNK_SIZE]
            
            return cleaned_text
            
        except Exception as e:
            logger.error(f"提取文本失败 {url}: {e}")
            return None
    
    async def clean_text(self, text: str) -> str:
        """清理文本（公共方法）"""
        return self._clean_text(text)
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除 HTML 标签残留
        text = re.sub(r'<[^>]+>', '', text)
        
        # 移除 URL
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # 移除电子邮件
        text = re.sub(r'\S+@\S+', '', text)
        
        # 移除特殊字符（保留中文字符）
        text = re.sub(r'[^\w\s\u4e00-\u9fff\u3400-\u4dbf\u20000-\u2a6df\u2a700-\u2b73f\u2b740-\u2b81f\u2b820-\u2ceaf\uf900-\ufaff\u3300-\u33ff\ufe30-\ufe4f\uf900-\ufaff\u2f800-\u2fa1f.,!?;:()\[\]{}"\'-]', ' ', text)
        
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    async def extract_entities(self, text: str) -> List[str]:
        """简单的实体提取（关键词提取）"""
        try:
            # 简单的词语分割
            words = re.findall(r'\b[A-Za-z]{3,}\b', text)
            
            # 过滤停用词和短词
            entities = []
            for word in words:
                if word.lower() not in self.stop_words and len(word) > 2:
                    entities.append(word)
            
            # 去重并返回
            return list(set(entities))
            
        except Exception as e:
            logger.error(f"提取实体失败: {e}")
            return []
    
    def extract_sentences(self, text: str, max_sentences: int = 10) -> List[str]:
        """简单的句子分割"""
        try:
            # 使用正则表达式分割句子
            sentences = re.split(r'[.!?]+', text)
            
            # 过滤短句子
            filtered_sentences = [s.strip() for s in sentences if len(s.split()) > 5]
            
            # 返回指定数量的句子
            return filtered_sentences[:max_sentences]
            
        except Exception as e:
            logger.error(f"提取句子失败: {e}")
            return []
    
    def extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        """简单的关键词提取"""
        try:
            # 简单的词语分割
            words = re.findall(r'\b[A-Za-z]{3,}\b', text.lower())
            
            # 移除停用词
            keywords = [word for word in words if word not in self.stop_words and len(word) > 2]
            
            # 计算词频
            word_freq = {}
            for word in keywords:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # 按频率排序
            sorted_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            
            # 返回前 N 个关键词
            return [word for word, freq in sorted_keywords[:max_keywords]]
            
        except Exception as e:
            logger.error(f"提取关键词失败: {e}")
            return []
    
    def summarize_text(self, text: str, max_length: int = 500) -> str:
        """简单的文本摘要（截取前几句）"""
        try:
            sentences = self.extract_sentences(text)
            
            if not sentences:
                return text[:max_length]
            
            # 逐句添加直到达到长度限制
            summary = ""
            for sentence in sentences:
                if len(summary) + len(sentence) <= max_length:
                    summary += sentence + ". "
                else:
                    break
            
            return summary.strip()
            
        except Exception as e:
            logger.error(f"文本摘要失败: {e}")
            return text[:max_length] 