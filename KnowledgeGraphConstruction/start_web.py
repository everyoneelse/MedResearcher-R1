#!/usr/bin/env python3
"""
Web应用启动脚本
"""
import os
import sys
from web_app import app, socketio

if __name__ == '__main__':
    print("🚀 启动知识图谱构建Web应用...")
    print("📍 访问地址: http://localhost:5000")
    print("🔧 调试模式: 开启")
    print("="*50)
    
    # 启动Flask-SocketIO应用
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=True,
        allow_unsafe_werkzeug=True
    ) 