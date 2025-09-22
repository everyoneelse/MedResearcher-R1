#!/usr/bin/env python3
"""
将处理完的数据从generated_datasets提升到final_datasets的脚本
"""

import os
import shutil
from pathlib import Path
import json

def promote_to_final_datasets():
    """将generated_datasets中的文件提升到final_datasets"""
    
    generated_dir = Path("evaluation_data/generated_datasets")
    final_dir = Path("evaluation_data/final_datasets")
    
    # 确保目录存在
    final_dir.mkdir(parents=True, exist_ok=True)
    
    if not generated_dir.exists():
        print("❌ generated_datasets目录不存在")
        return
    
    # 列出generated_datasets中的文件
    jsonl_files = list(generated_dir.glob("*.jsonl"))
    
    if not jsonl_files:
        print("⚠️  generated_datasets目录中没有JSONL文件")
        return
    
    print(f"📂 在generated_datasets中找到 {len(jsonl_files)} 个文件:")
    for i, file in enumerate(jsonl_files, 1):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                count = sum(1 for line in f if line.strip())
            print(f"  {i}. {file.name} ({count} 条记录)")
        except:
            print(f"  {i}. {file.name} (读取失败)")
    
    print("\n请选择要提升到最终数据集的文件:")
    print("0. 全部文件")
    
    try:
        choice = input("请输入选择 (0 或文件编号): ").strip()
        
        if choice == "0":
            # 提升所有文件
            selected_files = jsonl_files
        else:
            # 提升指定文件
            file_index = int(choice) - 1
            if 0 <= file_index < len(jsonl_files):
                selected_files = [jsonl_files[file_index]]
            else:
                print("❌ 无效选择")
                return
        
        # 执行提升操作
        promoted_count = 0
        for file in selected_files:
            target_path = final_dir / file.name
            
            # 检查目标文件是否已存在
            if target_path.exists():
                overwrite = input(f"文件 {file.name} 已存在，是否覆盖? (y/N): ").lower()
                if overwrite != 'y':
                    print(f"  跳过: {file.name}")
                    continue
            
            # 复制文件
            shutil.copy2(file, target_path)
            print(f"  ✅ 提升: {file.name} -> final_datasets/")
            promoted_count += 1
        
        if promoted_count > 0:
            print(f"\n🎉 成功提升 {promoted_count} 个文件到最终数据集!")
            print(f"📁 最终数据集目录: {final_dir.absolute()}")
            print("💡 现在可以访问 http://localhost:5000/final-datasets 查看数据")
        else:
            print("\n⚠️  没有文件被提升")
            
    except KeyboardInterrupt:
        print("\n\n用户取消操作")
    except ValueError:
        print("❌ 请输入有效的数字")
    except Exception as e:
        print(f"❌ 操作失败: {e}")

if __name__ == "__main__":
    promote_to_final_datasets()