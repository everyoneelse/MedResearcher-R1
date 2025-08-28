import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any
from tqdm import tqdm
import threading
from datetime import datetime
import re

# Add parent directory to path for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Add project root to path for global tools import
project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, project_root)

from langgraph_agent import LangGraphReasoningAgent
from prompts import build_system_message, build_training_user_prompt, build_training_system_prompt


def clean_cheat_sheet_from_messages(messages, original_question):
    if not messages or len(messages) == 0:
        return messages
    
    cleaned_messages = []
    for i, message in enumerate(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            
            has_cheat_sheet = False
            cleaned_content = content
            
            if "我有一些关键提示可以帮助解决这个问题：" in content and "现在请回答：" in content:
                parts = content.split("我有一些关键提示可以帮助解决这个问题：")
                if len(parts) >= 2:
                    prefix = parts[0]
                    cleaned_content = prefix + original_question
                    has_cheat_sheet = True
            
            elif "I have some key guidance to help solve this question:" in content and "Now please answer:" in content:
                parts = content.split("I have some key guidance to help solve this question:")
                if len(parts) >= 2:
                    prefix = parts[0]
                    cleaned_content = prefix + original_question
                    has_cheat_sheet = True
            
            elif ("## Keypoints:" in content or "## 关键点：" in content):
                if "## Keypoints:" in content:
                    parts = content.split("User Question:")
                    if len(parts) >= 2:
                        cleaned_content = "Do research on the question and answer it when you finish the research. When you finish your research, you should explain first and then answer, your answer should be place inside <answer></answer>, and your answer should be direct answer without any explanation. User Question: " + original_question
                        has_cheat_sheet = True
                elif "## 关键点：" in content:
                    parts = content.split("用户问题：")
                    if len(parts) >= 2:
                        cleaned_content = "对这个问题进行研究，完成研究后回答问题。当你完成研究时，你应该先解释然后回答，你的答案应该放在<answer></answer>内，你的答案应该是直接答案，不需要任何解释。用户问题：" + original_question
                        has_cheat_sheet = True
            
            if has_cheat_sheet:
                print(f"[DEBUG] Detected and cleaned cheat_sheet from user message")
                cleaned_messages.append({"role": message["role"], "content": cleaned_content})
            else:
                cleaned_messages.append(message)
        else:
            cleaned_messages.append(message)
    
    return cleaned_messages


def process_single_task(agent, task, model, standard_user_prompt, training_system_message, use_cheat_sheet=False, max_iterations=30):
    item = task["item"]
    rollout_id = task["rollout_id"]
    
    question = item.get("question", "")
    answer = item.get("answer", "")
    
    reasoning_path = ""
    if use_cheat_sheet:
        reasoning_path = item.get("reasoning_path", "")
    
    try:
        result = agent.process_question(
            question=question,
            reasoning_path=reasoning_path,
            max_iterations=max_iterations
        )
        
        trajectory_messages = result.get("trajectory_messages", [])
        training_messages = agent.get_trajectory_in_training_format(
            trajectory_messages, 
            standard_user_prompt=standard_user_prompt,
            training_system_prompt=training_system_message
        )
        
        return {
            "rollout": rollout_id,
            "question": question,
            "answer": answer,
            "prediction": result.get("prediction", "No answer found."),
            "messages": training_messages,
            "termination": result.get("termination", "unknown"),
            "step_count": result.get("step_count", 0),
            "token_count": agent.count_tokens_from_dict(training_messages)
        }
        
    except Exception as e:
        return {
            "rollout": rollout_id,
            "question": question,
            "answer": answer,
            "prediction": f"[Error] {str(e)}",
            "messages": [],
            "termination": f"error: {str(e)}",
            "step_count": 0,
            "token_count": 0
        }


def load_config(config_path: str = None) -> Dict[str, Any]:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")


def main():
    config = load_config()
    
    gen_config = config["generation"]
    llm_config = config["llm_config"]
    runtime_config = config["runtime"]
    
    model = gen_config["model"]
    output_base = gen_config["output"]
    rollouts = gen_config["rollouts"]

    model_name = os.path.basename(model.rstrip('/'))

    project_root = os.path.join(os.path.dirname(__file__), '..', '..')
    output_base_path = os.path.join(project_root, output_base)
    model_dir = os.path.join(output_base_path, model_name)
    dataset_dir = os.path.join(model_dir, gen_config["dataset"])

    os.makedirs(dataset_dir, exist_ok=True)

    meta_info = {
        "input_parameters": {
            "model": model,
            "dataset": gen_config["dataset"],
            "temperature": llm_config["temperature"],
            "top_p": llm_config.get("top_p", 0.95),
            "max_workers": gen_config["max_workers"],
            "sys_prompt": "default",
            "rollouts": rollouts,
            "use_cheat_sheet": gen_config["use_cheat_sheet"],
            "enabled_tools": gen_config["enabled_tools"],
            "output": output_base
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "model_name": model_name,
            "dataset_dir": dataset_dir,
            "data_filepath": os.path.join(project_root, "qa_data", f"{gen_config['dataset']}"),
            "langgraph_version": "enabled",
            "framework": "create_react_agent"
        }
    }

    print(f"Model name: {model_name}")
    print(f"Dataset name: {gen_config['dataset']}")
    print(f"Output directory: {dataset_dir}")
    print(f"Rollout count: {rollouts}")
    print(f"Use cheat sheet: {gen_config['use_cheat_sheet']}")
    print(f"Enabled tools: {gen_config['enabled_tools']}")
    print("Tool configuration: Using default ToolManager configuration")

    data_filepath = os.path.join(project_root, "qa_data", f"{gen_config['dataset']}")
    
    try:
        if data_filepath.endswith(".json"):
            with open(data_filepath, "r", encoding="utf-8") as f:
                items = json.load(f)
            if not isinstance(items, list):
                raise ValueError("Input JSON must be a list of objects.")
            if items and not isinstance(items[0], dict):
                raise ValueError("Input JSON list items must be objects.")
        elif data_filepath.endswith(".jsonl"):
            with open(data_filepath, "r", encoding="utf-8") as f:
                items = [json.loads(line) for line in f]
        else:
            raise ValueError("Unsupported file extension. Please use .json or .jsonl files.")
    except FileNotFoundError:
        print(f"Error: Input file not found at {data_filepath}")
        exit(1)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Error reading or parsing input file {data_filepath}: {e}")
        exit(1)

    if gen_config["use_cheat_sheet"]:
        missing_reasoning_path_count = 0
        for item in items:
            if not ("reasoning_path" in item and item["reasoning_path"]):
                missing_reasoning_path_count += 1
        
        if missing_reasoning_path_count > 0:
            print(f"Error: --use_cheat_sheet is enabled but {missing_reasoning_path_count}/{len(items)} items in the dataset are missing 'reasoning_path'")
            print("Please ensure all items in the dataset contain a valid 'reasoning_path' field when using cheat sheet mode")
            print("Note: 'mapped_reasoning_path' is not used as it contains too much specific information")
            exit(1)
        else:
            print(f"✓ All {len(items)} items contain valid 'reasoning_path' for cheat sheet")

    reasoning_stats = {"total_items": len(items)}
    
    if gen_config["use_cheat_sheet"]:
        reasoning_path_count = sum(1 for item in items if "reasoning_path" in item and item["reasoning_path"])
        reasoning_stats.update({
            "has_reasoning_path_items": reasoning_path_count,
            "missing_reasoning_path_items": len(items) - reasoning_path_count
        })
    else:
        reasoning_stats.update({
            "has_reasoning_path_items": None,
            "missing_reasoning_path_items": None
        })
    
    meta_info["dataset_statistics"] = reasoning_stats
    
    sample_item = items[0] if items else {}
    dataset_format_info = {
        "has_unique_id": "unique_id" in sample_item,
        "has_entity_mapping": "entity_mapping" in sample_item,
        "has_domain_tags": "domain_tags" in sample_item,
        "has_generation_metadata": "generation_metadata" in sample_item,
        "question_language": sample_item.get("question_language", "unknown"),
        "answer_language": sample_item.get("answer_language", "unknown"),
        "format_version": "v3_with_tags" if "domain_tags" in sample_item else "legacy"
    }
    meta_info["dataset_format"] = dataset_format_info

    output_file = os.path.join(dataset_dir, "trajectories.jsonl")

    print(f"\nOutput file: {output_file}")

    processed_pairs = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if "question" in data and "rollout" in data and "error" not in data:
                            processed_pairs.add((data["question"].strip(), data["rollout"]))
                    except json.JSONDecodeError:
                        print(f"Warning: Skipping invalid line in output file: {line.strip()}")
        except FileNotFoundError:
            pass

    tasks_to_run = []
    for rollout_idx in range(1, rollouts + 1):
        for item in items:
            question = item.get("question", "").strip()
            if question == "":
                try:
                    user_msg = item["messages"][1]["content"]
                    question = user_msg.split("User:")[1].strip() if "User:" in user_msg else user_msg
                    item["question"] = question
                except Exception as e:
                    print(f"Extract question from user message failed: {e}")
            if not question:
                print(f"Warning: Skipping item with empty question: {item}")
                continue

            if (question, rollout_idx) not in processed_pairs:
                tasks_to_run.append({"item": item.copy(), "rollout_id": rollout_idx})
            else:
                print(f"Skipping already processed: question='{question[:50]}...', rollout={rollout_idx}")

    print(f"Total questions: {len(items)}")
    print(f"Total rollouts: {rollouts}")
    print(f"Already processed pairs: {len(processed_pairs)}")
    print(f"Total tasks to run: {len(tasks_to_run)}")

    if not tasks_to_run:
        print("All tasks completed, nothing to process")
        return

    llm_cfg = {
        'model': model,
        'generate_cfg': {
            'max_input_tokens': 320000,
            'max_retries': 10,
            'temperature': llm_config["temperature"],
            'top_p': llm_config.get("top_p", 0.95)
        }
    }

    system_message = build_system_message()
    
    training_system_message = build_training_system_prompt()

    agent = LangGraphReasoningAgent(
        model=model,
        generate_cfg=llm_cfg['generate_cfg'],
        system_message=system_message,
        use_cheat_sheet=gen_config["use_cheat_sheet"],
        enabled_tools=gen_config["enabled_tools"],
        max_llm_calls=runtime_config["max_llm_calls"],
        max_token_length=runtime_config["max_token_length"],
        llm_config=llm_config,
        tokenizer_path=runtime_config["tokenizer_path"]
    )

    standard_user_prompt = build_training_user_prompt(
        tool_manager=agent.tool_manager,
        enabled_tools=gen_config["enabled_tools"]
    )

    meta_info["metadata"]["system_message"] = training_system_message
    meta_info["metadata"]["user_prompt"] = standard_user_prompt
    meta_info["metadata"]["enabled_tools"] = gen_config["enabled_tools"]
        
    meta_file = os.path.join(dataset_dir, "meta.json")
    if not os.path.exists(meta_file):
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False, indent=2)
        print(f"Meta information saved to: {meta_file}")

    write_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=gen_config["max_workers"]) as executor:
            future_to_task = {
                executor.submit(
                    process_single_task,
                    agent,
                    task,
                    model,
                    standard_user_prompt, # Use standard_user_prompt here
                    training_system_message, # Pass training system message
                    gen_config["use_cheat_sheet"],
                    runtime_config["max_llm_calls"]
                ): task
                for task in tasks_to_run
            }

            for future in tqdm(as_completed(future_to_task), total=len(tasks_to_run),
                           desc="Processing All Rollouts"):
                task_info = future_to_task[future]
                try:
                    result = future.result()
                    
                    if gen_config["use_cheat_sheet"] and "messages" in result:
                        original_question = task_info["item"].get("question", "")
                        result["messages"] = clean_cheat_sheet_from_messages(result["messages"], original_question)
                        print(f"[DEBUG] Cleaned cheat_sheet content from messages for question: {original_question[:50]}...")
                    
                    result["trajectory_id"] = str(uuid.uuid4())
                    result["source_model"] = model
                    result["source_dataset"] = gen_config["dataset"]
                    result["created_at"] = datetime.now().isoformat()
                    result["rollout"] = task_info["rollout_id"]
                    result["langgraph_version"] = "enabled"
                    result["framework"] = "create_react_agent"
                    result["enabled_tools"] = gen_config["enabled_tools"]
                    
                    # Extract qaid from item
                    item = task_info["item"]
                    if "unique_id" in item:
                        result["qaid"] = item["unique_id"]
                    elif "qaid" in item:
                        result["qaid"] = item["qaid"]
                    elif "id" in item:
                        result["qaid"] = item["id"]
                    else:
                        import hashlib
                        question = item.get("question", "")
                        result["qaid"] = hashlib.md5(question.encode()).hexdigest()[:12]
                    
                    with write_lock:
                        with open(output_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps(result, ensure_ascii=False) + "\n")
                            
                except Exception as exc:
                    print(f'Task for question "{task_info["item"]["question"]}" (Rollout {task_info["rollout_id"]}) generated an exception: {exc}')
                    
                    item = task_info["item"]
                    error_result = {
                        "question": item["question"],
                        "answer": item.get("answer", ""),
                        "rollout": task_info["rollout_id"],
                        "error": f"Future resolution failed: {exc}",
                        "messages": [],
                        "prediction": "[Failed]",
                        "trajectory_id": str(uuid.uuid4()),
                        "source_model": model,
                        "source_dataset": gen_config["dataset"],
                        "created_at": datetime.now().isoformat(),
                        "langgraph_version": "enabled",
                        "framework": "create_react_agent"
                    }
                    
                    # Extract qaid from item
                    if "unique_id" in item:
                        error_result["qaid"] = item["unique_id"]
                    elif "qaid" in item:
                        error_result["qaid"] = item["qaid"]
                    elif "id" in item:
                        error_result["qaid"] = item["id"]
                    else:
                        import hashlib
                        question = item.get("question", "")
                        error_result["qaid"] = hashlib.md5(question.encode()).hexdigest()[:12]
                    
                    print("===============================")
                    print(error_result)
                    print("===============================")

                    with write_lock:
                        with open(output_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps(error_result, ensure_ascii=False) + "\n")

    print(f"\nAll {rollouts} rollouts completed!")


if __name__ == "__main__":
    main() 