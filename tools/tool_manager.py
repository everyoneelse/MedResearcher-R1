#!/usr/bin/env python3
"""
Tool manager for the reasoning module.
Provides dynamic tool configuration and management based on config file.
"""

import json
import os
from typing import Dict, List, Any, Optional
from langchain_core.tools import tool
from .tool_visit import VisitTool
from .tool_search import SearchTool


class ToolManager:
    """Manages tools for the reasoning agent with dynamic configuration"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "tool_config.json")
        self.config = self._load_config()
        self.tool_classes = {
            "SearchTool": SearchTool,
            "VisitTool": VisitTool,
        }
        self.tool_instances = {}
        self._initialize_tools()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load tool configuration from JSON file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                raise FileNotFoundError(f"Tool configuration file not found: {self.config_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to load tool config from {self.config_path}: {e}")
    
    def _initialize_tools(self):
        """Initialize tool instances based on configuration"""
        for tool_name, tool_config in self.config["tools"].items():
            if tool_config.get("enabled", True):
                tool_class_name = tool_config["class"]
                if tool_class_name in self.tool_classes:
                    tool_class = self.tool_classes[tool_class_name]
                    # Pass extra_config to tool constructor if available
                    extra_config = tool_config.get("extra_config", {})
                    
                    # Pass description and parameters from config
                    description = tool_config.get("description", "")
                    parameters = tool_config.get("parameters", {})
                    
                    # Combine all config parameters
                    init_params = {
                        **extra_config,
                        "description": description,
                        "parameters": parameters
                    }
                    
                    self.tool_instances[tool_name] = tool_class(**init_params)
    
    def _create_langchain_tool(self, tool_name: str):
        """Create a LangChain tool wrapper for the specified tool"""
        if tool_name not in self.tool_instances:
            return None
            
        tool_config = self.config["tools"][tool_name]
        tool_instance = self.tool_instances[tool_name]
        
        # Use the tool instance's formatted description
        description = getattr(tool_instance, 'description', tool_config.get("description", ""))
        parameters = getattr(tool_instance, 'parameters', tool_config.get("parameters", {}))
        
        if tool_name == "search":
            query_desc = parameters.get("query", {}).get("description", "Array of query strings")
            
            # Create the docstring dynamically
            search_docstring = f"""{description}
                
Args:
    query: {query_desc}
    
Returns:
    Search results for all queries"""
            
            @tool
            def search(query: List[str]) -> str:
                """Temporary docstring"""
                return tool_instance(query)
            
            # Set both docstring and description after creation
            search.__doc__ = search_docstring
            search.description = description
            return search
            
        elif tool_name == "visit":
            url_desc = parameters.get("url", {}).get("description", "The URL(s) of the webpage(s) to visit")
            goal_desc = parameters.get("goal", {}).get("description", "The goal for visiting the webpage(s)")
            
            # Create the docstring dynamically
            visit_docstring = f"""{description}
                
Args:
    url: {url_desc}
    goal: {goal_desc}
    
Returns:
    Summary of the webpage content based on the specified goal"""
            
            @tool 
            def visit(url: List[str], goal: str) -> str:
                """Temporary docstring"""
                return tool_instance(url, goal)
            
            # Set both docstring and description after creation
            visit.__doc__ = visit_docstring
            visit.description = description
            return visit
        
        return None
    
    def get_enabled_tools(self, tool_names: List[str] = None) -> List:
        """
        Get LangChain tools for the specified tool names.
        
        Args:
            tool_names: List of tool names to get. If None, returns all enabled tools.
            
        Returns:
            List of LangChain tool objects
        """
        if tool_names is None:
            tool_names = list(self.config["tools"].keys())
        
        tools = []
        for tool_name in tool_names:
            if tool_name in self.config["tools"] and self.config["tools"][tool_name].get("enabled", True):
                langchain_tool = self._create_langchain_tool(tool_name)
                if langchain_tool:
                    tools.append(langchain_tool)
        
        return tools
    
    def get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Get configuration for a specific tool"""
        return self.config["tools"].get(tool_name, {})
    
    def update_tool_config(self, tool_name: str, config_updates: Dict[str, Any]):
        """Update configuration for a specific tool"""
        if tool_name in self.config["tools"]:
            self.config["tools"][tool_name].update(config_updates)
            # Re-initialize the tool with new config
            if config_updates.get("enabled", True):
                tool_class_name = self.config["tools"][tool_name]["class"]
                if tool_class_name in self.tool_classes:
                    tool_class = self.tool_classes[tool_class_name]
                    extra_config = self.config["tools"][tool_name].get("extra_config", {})
                    
                    # Pass description and parameters from config
                    description = self.config["tools"][tool_name].get("description", "")
                    parameters = self.config["tools"][tool_name].get("parameters", {})
                    
                    # Combine all config parameters
                    init_params = {
                        **extra_config,
                        "description": description,
                        "parameters": parameters
                    }
                    
                    self.tool_instances[tool_name] = tool_class(**init_params)
    
    def save_config(self, config_path: Optional[str] = None):
        """Save current configuration to file"""
        save_path = config_path or self.config_path
        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save tool config to {save_path}: {e}")
    
    def get_available_tools(self) -> List[str]:
        """Get list of all available tool names"""
        return list(self.config["tools"].keys())
    
    def get_enabled_tool_names(self) -> List[str]:
        """Get list of enabled tool names"""
        return [name for name, config in self.config["tools"].items() 
                if config.get("enabled", True)]


def create_tool_manager(config_path: Optional[str] = None) -> ToolManager:
    """
    Factory function to create a ToolManager instance.
    
    Args:
        config_path: Path to tool configuration file
        
    Returns:
        ToolManager instance
    """
    return ToolManager(config_path)


def get_default_tools() -> List[str]:
    """Get list of default tool names"""
    return ["search", "visit"]


if __name__ == "__main__":
    # Test the tool manager
    tm = create_tool_manager()
    
    print("Available tools:", tm.get_available_tools())
    print("Enabled tools:", tm.get_enabled_tool_names())
    
    # Test tool creation
    tools = tm.get_enabled_tools(['search', 'visit'])
    for tool in tools:
        print(f"✅ Tool: {tool.name} - {tool.description[:100]}...")
    
    print("🎉 Tool manager test completed!") 