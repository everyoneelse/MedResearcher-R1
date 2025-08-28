import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union, Dict, Any
import requests
from time import sleep
import os
import random
from openai import OpenAI


WEBCONTENT_MAXLENGTH = int(os.getenv("WEBCONTENT_MAXLENGTH", 150000))
# Extractor prompt for visit tool
EXTRACTOR_PROMPT = """Please process the following webpage content and user goal to extract relevant information:

## **Webpage Content** 
{webpage_content}

## **User Goal**
{goal}

## **Task Guidelines**
1. **Content Scanning for Rational**: Locate the **specific sections/data** directly related to the user's goal within the webpage content
2. **Key Extraction for Evidence**: Identify and extract the **most relevant information** from the content, you never miss any important information, output the **full original context** of the content as far as possible, it can be more than three paragraphs.
3. **Summary Output for Summary**: Organize into a concise paragraph with logical flow, prioritizing clarity and judge the contribution of the information to the goal.

**Final Output Format using JSON format has "rational", "evidence", "summary" feilds**
"""


class ToolServiceError(Exception):
    """Custom exception for tool service errors"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class VisitTool:
    """
    visit tool for extracting content from webpages.
    """
    
    def __init__(self, description, parameters, **kwargs):
        # Set default max_urls to 5 if not provided
        self.max_urls = 5
        self.name = 'visit'
        
        # Format description with current config values
        self.description = description
        
        # Store parameters configuration
        self.parameters = parameters
    
    def __call__(self, url: Union[str, List[str]], goal: str) -> str:
        if isinstance(url, str):
            response = self._read(url, goal)
        else:
            response = []
            assert isinstance(url, List)
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(self._read, u, goal): u for u in url}
                for future in as_completed(futures):
                    try:
                        response.append(future.result())
                    except ToolServiceError as e:
                        raise
                    except Exception as e:
                        response.append(f"Error fetching {futures[future]}: {str(e)}")
            response = "\n=======\n".join(response)

        # print(f'Summary Length {len(response)}; Summary Content {response}')
        return response.strip()

    def _call_llm_summary(self, msgs, max_tries=10):
        openai_api_base = "https://openrouter.ai/api/v1"
        openai_api_key = os.getenv("OPENROUTER_API_KEY")

        for attempt in range(max_tries):
            try:
                client = OpenAI(
                    api_key=openai_api_key,
                    base_url=openai_api_base,
                )
                chat_response = client.chat.completions.create(
                    model='moonshotai/kimi-k2',
                    messages=msgs,
                    temperature=0.7
                )
                content = chat_response.choices[0].message.content
                if content:
                    try:
                        left = content.find('{')
                        right = content.rfind('}') 
                        return content[left:right+1]
                    except:
                        return content
            except:
                sleep(attempt)
                if attempt == (max_tries - 1):
                    raise ToolServiceError(message=f"visit tool summary encounter unexpected error")
                continue

    def _extract_jina(self, url: str) -> str:
        headers = {
            "Authorization": "Bearer " + str(os.getenv('JINA_API_KEY')),
        }
        max_retries = 3
        timeout = 20

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"https://r.jina.ai/{url}",
                    headers=headers,
                    timeout=timeout
                )
                if response.status_code == 200:
                    webpage_content = response.text
                    return webpage_content
                else:
                    # print(response.text)
                    raise ToolServiceError(message="jina readpage error")
            except ToolServiceError as e:
                if attempt == max_retries - 1:
                    raise ToolServiceError(message=f"{str(e.message)}")
            except Exception as e:
                if attempt == max_retries - 1:
                    # print(f"jina encounter error: {e}")
                    return "[visit] Failed to visit page."

            return "[visit] Failed to read page."
    def _read(self, url: str, goal: str) -> str:
        """
              Attempt to read webpage content by alternating between jina and aidata services.

              Args:
                  url: The URL to read
                  goal: The goal/purpose of reading the page

              Returns:
                  str: The webpage content or error message
              """
        max_attempts = 5
        content = ""
        for attempt in range(max_attempts):
            if not (content and not content.startswith(
                    "[visit] Failed to read page.") and content != "[visit] Empty content." and not content.startswith(
                "[document_parser]")):
                # print(f"[visit] tavily read failed with error {str(e)}, use jina")
                content = self._extract_jina(url)
                sevice = "jina"
                # Check if we got valid content
                # print(f"{sevice} finish extraction of url: {url}, the content is {content[:100]}... ")
            # print(content)
            if content and not content.startswith(
                    "[visit] Failed to read page.") and content != "[visit] Empty content." and not content.startswith(
                    "[document_parser]"):
                content = content[:WEBCONTENT_MAXLENGTH]
                messages = [{"role": "user", "content": EXTRACTOR_PROMPT.format(webpage_content=content, goal=goal)}]
                parse_retry_times = 0
                raw = self._call_llm_summary(messages)

                # 如果网页超长，返回结果是 {\n 这种形式
                summary_retries = 3
                while len(raw) < 10 and summary_retries >= 0:
                    truncate_length = int(0.7 * len(content)) if summary_retries > 0 else 25000
                    status_msg = (
                        f"[visit] Summary url[{url}] "
                        f"attempt {3 - summary_retries + 1}/3, "
                        f"content length: {len(content)}, "
                        f"truncating to {truncate_length} chars"
                    ) if summary_retries > 0 else (
                        f"[visit] Summary url[{url}] failed after 3 attempts, "
                        f"final truncation to 25000 chars"
                    )
                    # print(status_msg)
                    content = content[:truncate_length]
                    extraction_prompt = EXTRACTOR_PROMPT.format(
                        webpage_content=content,
                        goal=goal
                    )
                    messages = [{"role": "user", "content": extraction_prompt}]
                    raw = self._call_llm_summary(messages)
                    summary_retries -= 1
                # 说明 raw 的长度大于10或者已经retry 超出了
                parse_retry_times = 0
                while parse_retry_times < 3:
                    try:
                        # 尝试 parse json
                        raw = json.loads(raw)
                        break
                    except:
                        raw = self._call_llm_summary(messages)
                        parse_retry_times += 1
                # parse 失败
                if parse_retry_times >= 3:
                    useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(
                        url=url, goal=goal)
                    useful_information += "Evidence in page: \n" + "The provided webpage content could not be accessed. Please check the URL or file format." + "\n\n"
                    useful_information += "Summary: \n" + "The webpage content could not be processed, and therefore, no information is available." + "\n\n"
                # parse 成功
                else:
                    useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(
                        url=url, goal=goal)
                    useful_information += "Evidence in page: \n" + str(raw["evidence"]) + "\n\n"
                    useful_information += "Summary: \n" + str(raw["summary"]) + "\n\n"

                    summary_retries -= 1

                if len(useful_information) < 10 and summary_retries < 0:
                    # print("[visit] Could not generate valid summary after maximum retries")
                    useful_information = "[visit] Failed to read page"
                return useful_information

            # If we're on the last attempt, return the last result
            if attempt == max_attempts - 1:
                useful_information = "The useful information in {url} for user goal {goal} as follows: \n\n".format(
                    url=url, goal=goal)
                useful_information += "Evidence in page: \n" + "The provided webpage content could not be accessed. Please check the URL or file format." + "\n\n"
                useful_information += "Summary: \n" + "The webpage content could not be processed, and therefore, no information is available." + "\n\n"
                return useful_information


if __name__ == "__main__":
    visit_tool = VisitTool("", "")
    print(visit_tool(["https://baike.baidu.com/item/1995%E5%B9%B4%E4%B8%AD%E5%A4%AE%E7%94%B5%E8%A7%86%E5%8F%B0%E6%98%A5%E8%8A%82%E8%81%94%E6%AC%A2%E6%99%9A%E4%BC%9A/6130478"], "谁是主持者？"))