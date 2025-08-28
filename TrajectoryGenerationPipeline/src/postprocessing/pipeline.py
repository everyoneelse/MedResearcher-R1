#!/usr/bin/env python3
"""
Post-processing pipeline: evaluation -> filtering -> rewriting
"""

import argparse
import json
import os
import glob
from pathlib import Path
from typing import Dict, List, Any, Optional

from evaluation.evaluator import AnswerEvaluator
from filtering.filter import TrajectoryFilter
from rewriting.rewriter import ThinkRewriter


class PostProcessingPipeline:
    """
    Integrated pipeline for trajectory post-processing.
    
    Stages:
    1. Evaluation: Judge answer quality using configurable prompts
    2. Filtering: Remove low-quality trajectories based on criteria  
    3. Rewriting: Optimize think content for training
    """
    
    def __init__(self, config_path: str = None):
        """
        Initialize the pipeline.
        
        Args:
            config_path: Path to configuration file
        """
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.json")
        
        # Initialize components
        self.evaluator = AnswerEvaluator(self.config_path)
        self.filter = TrajectoryFilter(self.config_path)
        self.rewriter = ThinkRewriter(self.config_path)
        
        # Load config for pipeline settings
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
    
    def _find_input_file_for_mode(self, input_dir: str, mode: str) -> str:
        """
        Find the appropriate input file based on mode and directory structure.
        
        Args:
            input_dir: Input directory path
            mode: Pipeline mode (eval, filter, rewrite)
            
        Returns:
            Path to the appropriate input file
            
        Raises:
            FileNotFoundError: If required file is not found
        """
        input_dir = Path(input_dir)
        
        if mode == "eval":
            # Look for trajectory files
            possible_files = [
                input_dir / "trajectories.jsonl",
                input_dir / "trajectory.jsonl"
            ]
            for file_path in possible_files:
                if file_path.exists():
                    return str(file_path)
            
            raise FileNotFoundError(
                f"No trajectory file found in {input_dir}. "
                f"Expected: trajectories.jsonl or trajectory.jsonl"
            )
        
        elif mode == "filter":
            # Look for evaluation results
            evaluation_file = input_dir / "evaluation_results" / "question_rollouts.jsonl"
            if evaluation_file.exists():
                return str(evaluation_file)
            
            raise FileNotFoundError(
                f"No evaluation results found in {input_dir}/evaluation_results/question_rollouts.jsonl. "
                f"Please run evaluation first."
            )
        
        elif mode == "rewrite":
            # Look for filtered accepted results
            accepted_file = input_dir / "filtered_results" / "accepted_results.jsonl"
            if accepted_file.exists():
                return str(accepted_file)
            
            raise FileNotFoundError(
                f"No accepted results found in {input_dir}/filtered_results/accepted_results.jsonl. "
                f"Please run filtering first."
            )
        
        else:
            raise ValueError(f"Unknown mode: {mode}")

    def _get_jsonl_files(self, input_path: str) -> List[str]:
        """
        Get list of jsonl files from input path.
        
        Args:
            input_path: Either a single file or directory containing jsonl files
            
        Returns:
            List of jsonl file paths
        """
        input_path = Path(input_path)
        
        if input_path.is_file():
            if input_path.suffix == '.jsonl':
                return [str(input_path)]
            else:
                raise ValueError(f"Input file must be .jsonl format: {input_path}")
        
        elif input_path.is_dir():
            jsonl_files = list(input_path.glob("*.jsonl"))
            if not jsonl_files:
                raise ValueError(f"No .jsonl files found in directory: {input_path}")
            
            # Sort files to ensure consistent processing order
            return sorted([str(f) for f in jsonl_files])
        
        else:
            raise ValueError(f"Input path does not exist: {input_path}")
    
    def run_evaluation(self, input_file: str, output_file: str, dataset_type: str = None) -> Dict[str, Any]:
        """Run evaluation stage."""
        print(f"\n🔍 Stage 1: Evaluation")
        print(f"Input: {input_file}")
        print(f"Output: {output_file}")
        
        stats = self.evaluator.evaluate_file(input_file, output_file, dataset_type)
        print(f"✅ Evaluation completed: {stats}")
        return stats
    
    def run_filtering(self, input_file: str, output_file: str) -> Dict[str, Any]:
        """Run filtering stage."""
        print(f"\n🔄 Stage 2: Filtering")
        print(f"Input: {input_file}")
        print(f"Output: {output_file}")
        
        stats = self.filter.filter_file(input_file, output_file)
        print(f"✅ Filtering completed: {stats}")
        return stats
    
    def run_rewriting(self, input_file: str, output_file: str) -> Dict[str, Any]:
        """Run rewriting stage."""
        print(f"\n✍️  Stage 3: Rewriting")
        print(f"Input: {input_file}")
        print(f"Output: {output_file}")
        
        stats = self.rewriter.rewrite_file(input_file, output_file)
        print(f"✅ Rewriting completed: {stats}")
        return stats
    


    def run_evaluation_directory(self, input_dir: str, dataset_type: str = None) -> Dict[str, Any]:
        """
        Run evaluation stage on a directory.
        
        Args:
            input_dir: Input directory containing trajectory files
            dataset_type: Type of dataset for evaluation
            
        Returns:
            Evaluation statistics
        """
        input_dir = Path(input_dir)
        
        # Find trajectory file
        input_file = self._find_input_file_for_mode(str(input_dir), "eval")
        
        # Output to input_dir/evaluation_results
        output_dir = input_dir / "evaluation_results"
        
        print(f"🔍 Starting evaluation pipeline")
        print(f"Input directory: {input_dir}")
        print(f"Input file: {input_file}")
        print(f"Output directory: {output_dir}")
        
        # Run evaluation
        eval_stats = self.evaluator.evaluate_file(input_file, str(output_dir), dataset_type)
        
        # Clean up intermediate files
        intermediate_file = output_dir / "intermediate_results.jsonl"
        if intermediate_file.exists():
            intermediate_file.unlink()
            print(f"🗑️ Cleaned up intermediate file: {intermediate_file}")
        
        print(f"\n🎉 Evaluation completed!")
        print(f"📁 Results available in: {output_dir}")
        print(f"   📊 evaluation_results.json")
        print(f"   📋 question_rollouts.jsonl") 
        print(f"   📈 evaluation_summary.json")
        
        return eval_stats

    def run_filtering_directory(self, input_dir: str) -> Dict[str, Any]:
        """
        Run filtering stage on a directory with evaluation results.
        
        Args:
            input_dir: Input directory containing evaluation_results
            
        Returns:
            Filtering statistics
        """
        input_dir = Path(input_dir)
        
        # Find evaluation results
        input_file = self._find_input_file_for_mode(str(input_dir), "filter")
        
        # Output to input_dir/filtered_results
        output_dir = input_dir / "filtered_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"🔄 Starting filtering pipeline")
        print(f"Input directory: {input_dir}")
        print(f"Input file: {input_file}")
        print(f"Output directory: {output_dir}")
        
        # Load evaluation results
        with open(input_file, 'r', encoding='utf-8') as f:
            evaluation_data = []
            for line in f:
                if line.strip():
                    evaluation_data.append(json.loads(line))
        
        # Convert question_rollouts to individual items
        all_items = []
        for record in evaluation_data:
            question = record["question"]
            answer = record["answer"]
            for rollout in record["rollouts"]:
                item = {
                    "question": question,
                    "answer": answer,
                    "prediction": rollout["prediction"],
                    "messages": rollout["messages"],
                    "rollout": rollout["rollout_id"],
                    "termination": rollout.get("termination", ""),
                    "evaluation": rollout.get("evaluation", {})
                }
                all_items.append(item)
        
        print(f"Loaded {len(all_items)} items from evaluation results")
        
        # Filter items
        valid_items, filter_stats = self.filter.filter_batch(all_items)
        
        # Get valid item indices to determine rejected items properly
        valid_indices = set()
        for valid_item in valid_items:
            for i, original_item in enumerate(all_items):
                if (valid_item.get("question") == original_item.get("question") and 
                    valid_item.get("rollout") == original_item.get("rollout")):
                    valid_indices.add(i)
                    break
        
        rejected_items = [all_items[i] for i in range(len(all_items)) if i not in valid_indices]
        
        # Save accepted results
        accepted_file = output_dir / "accepted_results.jsonl"
        with open(accepted_file, 'w', encoding='utf-8') as f:
            for item in valid_items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # Save rejected results  
        rejected_file = output_dir / "rejected_results.jsonl"
        with open(rejected_file, 'w', encoding='utf-8') as f:
            for item in rejected_items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # Save filter statistics
        stats_file = output_dir / "filtering_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(filter_stats, f, indent=2, ensure_ascii=False)
        
        print(f"\n🎉 Filtering completed!")
        print(f"📊 Results:")
        print(f"  Accepted: {len(valid_items)} items → {accepted_file}")
        print(f"  Rejected: {len(rejected_items)} items → {rejected_file}")
        print(f"  Pass rate: {filter_stats.get('pass_rate', 0)*100:.1f}%")
        print(f"  Statistics saved to: {stats_file}")
        
        return filter_stats

    def run_rewriting_directory(self, input_dir: str) -> Dict[str, Any]:
        """
        Run rewriting stage on a directory with filtered results.
        
        Args:
            input_dir: Input directory containing filtered_results
            
        Returns:
            Rewriting statistics
        """
        input_dir = Path(input_dir)
        
        # Find accepted results
        input_file = self._find_input_file_for_mode(str(input_dir), "rewrite")
        
        # Output to input_dir/rewritten_results.jsonl
        output_file = input_dir / "rewritten_results.jsonl"
        
        print(f"✍️  Starting rewriting pipeline")
        print(f"Input directory: {input_dir}")
        print(f"Input file: {input_file}")
        print(f"Output file: {output_file}")
        
        # Run rewriting
        rewrite_stats = self.rewriter.rewrite_file(input_file, str(output_file))
        
        print(f"\n🎉 Rewriting completed!")
        print(f"📄 Results saved to: {output_file}")
        print(f"📊 Statistics: {rewrite_stats}")
        
        return rewrite_stats

    def run_evaluation_and_filtering(self, input_dir: str, dataset_type: str = None) -> Dict[str, Any]:
        """
        Run evaluation and filtering stages sequentially on a directory.
        
        This method:
        1. First runs evaluation on the input directory
        2. Then runs filtering on the evaluation results
        
        Args:
            input_dir: Input directory containing trajectory files
            dataset_type: Type of dataset for evaluation
            
        Returns:
            Combined statistics from both stages
        """
        input_dir = Path(input_dir)
        
        print(f"🚀 Starting evaluation + filtering pipeline")
        print(f"Input directory: {input_dir}")
        
        # Stage 1: Run evaluation
        print(f"\n{'='*60}")
        print(f"🔍 STAGE 1: EVALUATION")
        print(f"{'='*60}")
        
        eval_stats = self.run_evaluation_directory(str(input_dir), dataset_type)
        
        # Stage 2: Run filtering on the evaluation results
        print(f"\n{'='*60}")
        print(f"🔄 STAGE 2: FILTERING")
        print(f"{'='*60}")
        
        filter_stats = self.run_filtering_directory(str(input_dir))
        
        # Combine statistics
        combined_stats = {
            "evaluation": eval_stats,
            "filtering": filter_stats,
            "pipeline_type": "evaluation_and_filtering_directory"
        }
        
        # Save combined statistics
        stats_file = input_dir / "eval_filter_pipeline_stats.json"
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(combined_stats, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*60}")
        print(f"🎉 EVALUATION + FILTERING PIPELINE COMPLETED!")
        print(f"{'='*60}")
        print(f"📊 Final Results:")
        print(f"  📁 Evaluation results: {input_dir}/evaluation_results/")
        print(f"  📁 Filtering results: {input_dir}/filtered_results/")
        print(f"  📈 Combined statistics: {stats_file}")
        
        if filter_stats.get("total_items", 0) > 0:
            pass_rate = filter_stats.get("pass_rate", 0) * 100
            print(f"  ✅ Overall pass rate: {pass_rate:.1f}%")
        
        return combined_stats


def main():
    """Main entry point for post-processing pipeline."""
    parser = argparse.ArgumentParser(description="Post-processing pipeline for trajectory data")
    
    parser.add_argument("--input_dir", type=str, required=True, 
                       help="Input directory containing the appropriate files for the selected mode")
    parser.add_argument("--mode", choices=["eval_filter", "rewrite", "eval", "filter"], required=True,
                       help="Pipeline mode: 'eval' for evaluation only, 'filter' for filtering only, 'rewrite' for rewriting only, 'eval_filter' for evaluation+filtering")
    parser.add_argument("--dataset_type", type=str, 
                       help="Dataset type for evaluation prompt selection (only for eval modes)")
    parser.add_argument("--config", type=str, help="Configuration file path")
    
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        return
    
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input path must be a directory: {args.input_dir}")
        return
    
    # Initialize pipeline
    try:
        pipeline = PostProcessingPipeline(args.config)
        
        if args.mode == "eval":
            # Run evaluation on directory
            stats = pipeline.run_evaluation_directory(
                input_dir=args.input_dir,
                dataset_type=args.dataset_type
            )
            
        elif args.mode == "filter":
            # Run filtering on directory
            stats = pipeline.run_filtering_directory(
                input_dir=args.input_dir
            )
            
        elif args.mode == "rewrite":
            # Run rewriting on directory
            stats = pipeline.run_rewriting_directory(
                input_dir=args.input_dir
            )
            
        elif args.mode == "eval_filter":
            # Run evaluation + filtering sequentially
            stats = pipeline.run_evaluation_and_filtering(
                input_dir=args.input_dir,
                dataset_type=args.dataset_type
            )
            
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        return
    except Exception as e:
        print(f"Error running pipeline: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 