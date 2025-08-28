#!/usr/bin/env python3
"""
知识图谱构建Web应用
提供前端界面来运行知识图谱构建系统
"""

import json
import logging
import asyncio
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from flask_socketio import SocketIO, emit
import threading
import sys
import os
import concurrent.futures
from threading import Lock
import time

# 预定义的领域标签列表
PREDEFINED_DOMAIN_TAGS = {'体育', '学术', '政治', '娱乐', '文学', '文化', '经济', '科技', '历史', '医疗', '其他'}

# 添加lib目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from lib.graphrag_builder import GraphRagBuilder
from lib.run_manager import RunManager
from lib.runs_qa_generator import RunsQAGenerator

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局变量存储构建状态
building_status = {
    'is_running': False,
    'current_step': '',
    'progress': 0,
    'graph_data': {'nodes': [], 'links': []},
    'logs': [],
    'run_id': None,
    'qa_result': None
}

class WebSocketHandler(logging.Handler):
    """自定义日志处理器，将日志发送到WebSocket - 支持trace"""
    
    def emit(self, record):
        # 获取trace ID（如果有的话）
        trace_id = getattr(record, 'trace_id', 'NO_TRACE')
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': record.levelname,
            'message': self.format(record),
            'trace_id': trace_id
        }
        building_status['logs'].append(log_entry)
        socketio.emit('log_message', log_entry)

def setup_logging():
    """设置日志系统 - 带有trace支持"""
    from lib.trace_manager import TraceFormatter
    from config import setup_global_logging
    
    # 首先设置全局日志（包含文件日志和trace支持）
    log_filename = setup_global_logging()
    
    # 获取根logger
    root_logger = logging.getLogger()
    
    # 检查是否已经有WebSocket处理器，避免重复添加
    has_websocket_handler = any(isinstance(handler, WebSocketHandler) for handler in root_logger.handlers)
    
    if not has_websocket_handler:
        # 创建WebSocket处理器（带trace支持）
        ws_handler = WebSocketHandler()
        trace_formatter = TraceFormatter('%(asctime)s [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s')
        ws_handler.setFormatter(trace_formatter)
        
        # 添加WebSocket处理器
        root_logger.addHandler(ws_handler)
    
    # 检查控制台处理器
    has_console_handler = any(isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout 
                             for handler in root_logger.handlers)
    
    if not has_console_handler:
        # 添加控制台处理器（带trace支持）
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = TraceFormatter('%(asctime)s [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # 获取logger并记录初始化信息
    setup_logger = logging.getLogger(__name__)
    setup_logger.info(f"Web应用日志系统初始化完成，日志文件: {log_filename}")

setup_logging()
logger = logging.getLogger(__name__)

@app.route('/')
def index():
    """主页导航"""
    return render_template('navigation.html')

@app.route('/single-qa')
def single_qa():
    """单条QA测试页面"""
    return render_template('single_qa.html')

@app.route('/batch-generation')
def batch_generation():
    """批量生成页面"""
    return render_template('batch_generation.html')

@app.route('/data-evaluation')
def data_evaluation():
    """数据评测页面"""
    return render_template('data_evaluation.html')

@app.route('/comparison-evaluation')
def comparison_evaluation():
    """对比评测页面"""
    return render_template('comparison_evaluation.html')

@app.route('/runs-qa-generation')
def runs_qa_generation():
    """Runs记录QA生成页面"""
    return render_template('runs_qa_generation.html')

@app.route('/data-management')
def data_management():
    """数据管理页面"""
    return render_template('data_management.html')

@app.route('/modern')
def modern_app():
    """现代化版本主页"""
    return render_template('modern_app.html')

@app.route('/domain-tags')
def domain_tags():
    return render_template('domain_tags.html')

@app.route('/api/start_building', methods=['POST'])
def start_building():
    """开始构建知识图谱"""
    from lib.trace_manager import start_trace
    
    # 启动trace
    trace_id = start_trace(prefix="web")
    logger.info(f"开始构建知识图谱请求")
    
    if building_status['is_running']:
        return jsonify({'error': '系统正在运行中'}), 400
    
    data = request.json
    entity = data.get('entity', '蚂蚁集团')
    max_nodes = data.get('max_nodes', 200)
    max_iterations = data.get('max_iterations', 10)
    sample_size = data.get('sample_size', 12)
    sampling_algorithm = data.get('sampling_algorithm', 'mixed')
    
    # 创建运行管理器
    run_manager = RunManager()
    run_id = run_manager.create_new_run(f"kg_build_{entity}")
    
    # 重置状态
    building_status['is_running'] = True
    building_status['current_step'] = '初始化'
    building_status['progress'] = 0
    building_status['graph_data'] = {'nodes': [], 'links': []}
    building_status['logs'] = []
    building_status['run_id'] = run_id
    building_status['qa_result'] = None
    
    # 在新线程中运行构建过程
    thread = threading.Thread(target=run_building_process, args=(entity, max_nodes, sample_size, run_manager, max_iterations, sampling_algorithm))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': '开始构建知识图谱', 'entity': entity, 'run_id': run_id})

@app.route('/api/status')
def get_status():
    """获取构建状态"""
    return jsonify(building_status)

@app.route('/api/stop_building', methods=['POST'])
def stop_building():
    """停止构建"""
    building_status['is_running'] = False
    building_status['current_step'] = '已停止'
    return jsonify({'message': '已停止构建'})

@app.route('/api/generate/single', methods=['POST'])
def generate_single():
    """单点查询接口 - 按研发计划设计"""
    from lib.trace_manager import start_trace
    
    # 启动trace
    trace_id = start_trace(prefix="single")
    logger.info(f"接收单条QA生成请求")
    
    if building_status['is_running']:
        return jsonify({'error': '系统正在运行中'}), 400
    
    data = request.json
    entity = data.get('entity', '量子计算机')
    sampling_algorithm = data.get('sampling_algorithm', 'mixed')
    
    logger.info(f"单条QA生成参数: 实体={entity}, 采样算法={sampling_algorithm}")
    
    # 创建运行管理器
    run_manager = RunManager()
    run_id = run_manager.create_new_run(f"single_{entity}")
    
    # 重置状态
    building_status['is_running'] = True
    building_status['current_step'] = '初始化'
    building_status['progress'] = 0
    building_status['graph_data'] = {'nodes': [], 'links': []}
    building_status['logs'] = []
    building_status['run_id'] = run_id
    building_status['qa_result'] = None
    
    # 在新线程中运行构建过程
    thread = threading.Thread(target=run_building_process, args=(entity, 30, 8, run_manager, 3, sampling_algorithm))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': run_id})

@app.route('/api/generate/batch', methods=['POST'])
def generate_batch():
    """批量生成接口 - 按研发计划设计"""
    if building_status['is_running']:
        return jsonify({'error': '系统正在运行中'}), 400
    
    data = request.json
    entities = data.get('entities', ['量子计算机', '人工智能', '基因编辑'])
    
    # 创建运行管理器
    run_manager = RunManager()
    run_id = run_manager.create_new_run(f"batch_{len(entities)}_entities")
    
    # 重置状态
    building_status['is_running'] = True
    building_status['current_step'] = '批量初始化'
    building_status['progress'] = 0
    building_status['graph_data'] = {'nodes': [], 'links': []}
    building_status['logs'] = []
    building_status['run_id'] = run_id
    building_status['qa_result'] = None
    
    # 在新线程中运行批量构建过程
    thread = threading.Thread(target=run_batch_building_process, args=(entities, run_manager))
    thread.daemon = True
    thread.start()
    
    return jsonify({'batch_job_id': run_id})

@app.route('/api/qa/<job_id>')
def get_qa_result(job_id):
    """获取QA生成结果"""
    if building_status['run_id'] == job_id and building_status['qa_result']:
        return jsonify(building_status['qa_result'])
    
    # 如果没有找到结果，返回默认消息
    return jsonify({
        'question': '暂无可用的QA结果',
        'answer': '请先完成知识图谱构建'
    })

# 批量生成相关API
# 实体集管理API
@app.route('/api/entity_sets/save', methods=['POST'])
def save_entity_set():
    """保存实体集"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        entities = data.get('entities', [])
        import_method = data.get('import_method', 'manual_newline')
        
        if not name:
            return jsonify({'error': '请提供实体集名称'}), 400
        
        if not entities:
            return jsonify({'error': '请提供实体数据'}), 400
        
        # 创建实体集目录
        entity_sets_dir = "evaluation_data/entity_sets"
        os.makedirs(entity_sets_dir, exist_ok=True)
        
        # 保存为CSV文件
        csv_path = os.path.join(entity_sets_dir, f"{name}.csv")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['entity'])  # 头部
            for entity in entities:
                writer.writerow([entity])
        
        # 保存元数据
        metadata = {
            'name': name,
            'count': len(entities),
            'created_at': datetime.now().isoformat(),
            'import_method': import_method,
            'file_path': csv_path
        }
        
        metadata_path = os.path.join(entity_sets_dir, f"{name}.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"实体集 '{name}' 保存成功，共{len(entities)}个实体")
        
        return jsonify({
            'success': True,
            'message': '实体集保存成功',
            'count': len(entities)
        })
        
    except Exception as e:
        logger.error(f"保存实体集失败: {e}")
        return jsonify({'error': f'保存失败: {str(e)}'}), 500

@app.route('/api/entity_sets/upload', methods=['POST'])
def upload_entity_set():
    """上传CSV文件保存实体集"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有文件'}), 400
        
        file = request.files['file']
        name = request.form.get('name', '').strip()
        
        if not name:
            return jsonify({'error': '请提供实体集名称'}), 400
        
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 创建实体集目录
        entity_sets_dir = "evaluation_data/entity_sets"
        os.makedirs(entity_sets_dir, exist_ok=True)
        
        # 读取CSV文件
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.reader(stream)
        
        entities = []
        for row in reader:
            if row and row[0].strip():  # 只取第一列，且非空
                entities.append(row[0].strip())
        
        if not entities:
            return jsonify({'error': 'CSV文件中没有有效的实体数据'}), 400
        
        # 保存为CSV文件
        csv_path = os.path.join(entity_sets_dir, f"{name}.csv")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['entity'])  # 头部
            for entity in entities:
                writer.writerow([entity])
        
        # 保存元数据
        metadata = {
            'name': name,
            'count': len(entities),
            'created_at': datetime.now().isoformat(),
            'import_method': 'csv_file',
            'file_path': csv_path
        }
        
        metadata_path = os.path.join(entity_sets_dir, f"{name}.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        logger.info(f"实体集 '{name}' 上传保存成功，共{len(entities)}个实体")
        
        return jsonify({
            'success': True,
            'message': '实体集上传成功',
            'count': len(entities)
        })
        
    except Exception as e:
        logger.error(f"上传实体集失败: {e}")
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@app.route('/api/entity_sets/list', methods=['GET'])
def list_entity_sets():
    """获取实体集列表"""
    try:
        entity_sets_dir = "evaluation_data/entity_sets"
        
        if not os.path.exists(entity_sets_dir):
            return jsonify({'success': True, 'entity_sets': []})
        
        entity_sets = []
        for file in os.listdir(entity_sets_dir):
            if file.endswith('.json'):
                try:
                    metadata_path = os.path.join(entity_sets_dir, file)
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    entity_sets.append(metadata)
                except Exception as e:
                    logger.warning(f"读取元数据文件失败: {file}, 错误: {e}")
        
        # 按创建时间排序
        entity_sets.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'entity_sets': entity_sets
        })
        
    except Exception as e:
        logger.error(f"获取实体集列表失败: {e}")
        return jsonify({'error': f'获取列表失败: {str(e)}'}), 500

@app.route('/api/entity_sets/info/<name>', methods=['GET'])
def get_entity_set_info(name):
    """获取实体集详情"""
    try:
        entity_sets_dir = "evaluation_data/entity_sets"
        metadata_path = os.path.join(entity_sets_dir, f"{name}.json")
        
        if not os.path.exists(metadata_path):
            return jsonify({'error': '实体集不存在'}), 404
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        return jsonify({
            'success': True,
            'entity_set': metadata
        })
        
    except Exception as e:
        logger.error(f"获取实体集详情失败: {e}")
        return jsonify({'error': f'获取详情失败: {str(e)}'}), 500

@app.route('/api/entity_sets/delete/<name>', methods=['DELETE'])
def delete_entity_set(name):
    """删除实体集"""
    try:
        entity_sets_dir = "evaluation_data/entity_sets"
        
        # 删除CSV文件
        csv_path = os.path.join(entity_sets_dir, f"{name}.csv")
        if os.path.exists(csv_path):
            os.remove(csv_path)
        
        # 删除元数据文件
        metadata_path = os.path.join(entity_sets_dir, f"{name}.json")
        if os.path.exists(metadata_path):
            os.remove(metadata_path)
        
        logger.info(f"实体集 '{name}' 删除成功")
        
        return jsonify({
            'success': True,
            'message': '实体集删除成功'
        })
        
    except Exception as e:
        logger.error(f"删除实体集失败: {e}")
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

@app.route('/api/data_management/directories')
def list_data_directories():
    """获取可用的数据目录列表"""
    try:
        directories = [
            {
                'path': 'evaluation_data/generated_datasets',
                'name': '生成数据集',
                'description': '批量生成的QA数据集'
            },
            {
                'path': 'evaluation_data/final_datasets',
                'name': '最终数据集', 
                'description': '最终版本的数据集'
            },
            {
                'path': 'evaluation_data/final_datasets/label_datasets',
                'name': '标签数据集',
                'description': '带领域标签的数据集'
            }
        ]
        
        # 检查目录是否存在并添加文件统计
        available_dirs = []
        for dir_info in directories:
            if os.path.exists(dir_info['path']):
                # 统计JSONL文件数量
                file_count = sum(1 for f in os.listdir(dir_info['path']) 
                               if f.endswith('.jsonl'))
                dir_info['file_count'] = file_count
                available_dirs.append(dir_info)
        
        return jsonify({
            'success': True,
            'directories': available_dirs
        })
        
    except Exception as e:
        logger.error(f"获取目录列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/data_management/files')
def list_directory_files():
    """获取指定目录下的文件列表"""
    try:
        directory = request.args.get('directory', '')
        if not directory:
            return jsonify({'success': False, 'error': '请指定目录'}), 400
        
        if not os.path.exists(directory):
            return jsonify({'success': False, 'error': '目录不存在'}), 404
        
        files = []
        for filename in os.listdir(directory):
            if filename.endswith('.jsonl'):
                filepath = os.path.join(directory, filename)
                try:
                    # 获取文件信息
                    stat = os.stat(filepath)
                    modified_time = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 计算记录数
                    count = 0
                    with open(filepath, 'r', encoding='utf-8') as f:
                        count = sum(1 for line in f if line.strip())
                    
                    files.append({
                        'filename': filename,
                        'count': count,
                        'modified_time': modified_time,
                        'size': stat.st_size,
                        'directory': directory
                    })
                except Exception as e:
                    logger.error(f"读取文件信息失败 {filename}: {e}")
                    continue
        
        # 按修改时间倒序排列
        files.sort(key=lambda x: x['modified_time'], reverse=True)
        
        return jsonify({
            'success': True,
            'files': files,
            'directory': directory
        })
        
    except Exception as e:
        logger.error(f"获取文件列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/batch_generation/start', methods=['POST'])
def start_batch_generation():
    """开始批量生成"""
    from lib.trace_manager import start_trace
    
    # 启动trace
    trace_id = start_trace(prefix="batch")
    logger.info(f"接收批量生成请求")
    
    if building_status['is_running']:
        return jsonify({'error': '系统正在运行中'}), 400
    
    data = request.json
    entity_set_name = data.get('entity_set', '')
    
    if not entity_set_name:
        return jsonify({'error': '请选择实体集'}), 400
    
    # 读取实体集
    try:
        entity_sets_dir = "evaluation_data/entity_sets"
        csv_path = os.path.join(entity_sets_dir, f"{entity_set_name}.csv")
        
        if not os.path.exists(csv_path):
            return jsonify({'error': '实体集不存在'}), 404
        
        entities = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('entity', '').strip():
                    entities.append(row['entity'].strip())
        
        if not entities:
            return jsonify({'error': '实体集为空'}), 400
        
        # 处理断点续传
        resume_config = data.get('resume', {})
        if resume_config.get('enabled') and resume_config.get('filename'):
            resume_filename = resume_config['filename']
            resume_filepath = f"evaluation_data/generated_datasets/{resume_filename}"
            
            if os.path.exists(resume_filepath):
                # 读取已完成的实体
                completed_entities = set()
                try:
                    with open(resume_filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                line_data = json.loads(line.strip())
                                entity = line_data.get('entity', '')
                                if entity:
                                    completed_entities.add(entity)
                    
                    # 过滤掉已完成的实体
                    original_count = len(entities)
                    entities = [e for e in entities if e not in completed_entities]
                    skipped_count = original_count - len(entities)
                    
                    logger.info(f"断点续传: 跳过 {skipped_count} 个已完成的实体，剩余 {len(entities)} 个")
                    
                    # 如果启用了即时保存，使用续传文件作为输出文件
                    instant_save_config = data.get('instant_save', {})
                    if instant_save_config.get('enabled'):
                        instant_save_config['filename'] = resume_filename
                        data['instant_save'] = instant_save_config
                    
                except Exception as e:
                    logger.error(f"读取断点续传文件失败: {e}")
                    return jsonify({'error': f'读取断点续传文件失败: {str(e)}'}), 500
        
        if not entities:
            return jsonify({'error': '所有实体都已完成，无需继续生成'}), 400
        
        # 将实体列表添加到配置中
        data['entities'] = entities
        data['count'] = len(entities)
        
        count = len(entities)
        logger.info(f"接收到批量生成请求，实体集: {entity_set_name}，实体数量: {count}")
        
        # 创建运行管理器
        run_manager = RunManager()
        batch_id = run_manager.create_new_run(f"batch_generation_{entity_set_name}_{count}")
        
        # 重置状态
        building_status['is_running'] = True
        building_status['current_step'] = '批量生成初始化'
        building_status['progress'] = 0
        building_status['run_id'] = batch_id
        
        # 在新线程中运行批量生成
        thread = threading.Thread(target=run_batch_generation_process, args=(data, run_manager))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'batch_id': batch_id, 
            'message': '批量生成已开始',
            'count': count
        })
        
    except Exception as e:
        logger.error(f"读取实体集失败: {e}")
        return jsonify({'error': f'读取实体集失败: {str(e)}'}), 500

@app.route('/api/batch_generation/stop', methods=['POST'])
def stop_batch_generation():
    """停止批量生成"""
    building_status['is_running'] = False
    building_status['current_step'] = '已停止'
    return jsonify({'message': '批量生成已停止'})

@app.route('/api/preview_entities', methods=['POST'])
def preview_entities():
    """预览实体"""
    data = request.json
    source = data.get('source', 'wikidata')
    count = data.get('count', 10)
    category = data.get('category', '')
    
    # 这里可以实现不同数据源的预览逻辑
    if source == 'wikidata':
        # 模拟WikiData实体
        sample_entities = [
            '量子计算机', '人工智能', '基因编辑', '脑机接口', '纳米材料',
            '区块链', '虚拟现实', '增强现实', '物联网', '5G通信',
            '太阳能电池', '电动汽车', '自动驾驶', '机器学习', '深度学习'
        ]
        import random
        entities = random.sample(sample_entities, min(count, len(sample_entities)))
        return jsonify({'entities': entities})
    
    return jsonify({'entities': []})

# 评测数据管理API
@app.route('/api/evaluation_data/list')
def list_evaluation_data():
    """列出所有评测数据集"""
    import os
    import json
    from datetime import datetime
    
    def scan_dataset_directory(directory):
        """扫描数据集目录，返回jsonl文件列表"""
        datasets = []
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.endswith('.jsonl') and not filename.startswith('.'):
                    filepath = os.path.join(directory, filename)
                    try:
                        # 计算文件中的行数（QA对数量）
                        with open(filepath, 'r', encoding='utf-8') as f:
                            count = sum(1 for line in f if line.strip())
                        
                        # 获取文件创建时间
                        created_at = datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d')
                        
                        # 去掉.jsonl后缀作为展示名称
                        display_name = filename.replace('.jsonl', '')
                        
                        datasets.append({
                            'id': filename,  # 使用完整文件名作为ID
                            'name': display_name,  # 展示名称去掉后缀
                            'count': count,
                            'created_at': created_at
                        })
                    except Exception as e:
                        logger.error(f"读取数据集文件 {filename} 失败: {e}")
                        continue
        return datasets
    
    # 扫描标准数据集和生成数据集目录
    standard_datasets = scan_dataset_directory('evaluation_data/standard_datasets')
    generated_datasets = scan_dataset_directory('evaluation_data/generated_datasets')
    
    return jsonify({
        'standard': standard_datasets,
        'generated': generated_datasets
    })

@app.route('/api/evaluation_data/details/<dataset_id>')
def get_evaluation_data_details(dataset_id):
    """获取数据集详情"""
    import os
    import json
    from datetime import datetime
    
    # 确定数据集文件路径
    standard_path = f'evaluation_data/standard_datasets/{dataset_id}'
    generated_path = f'evaluation_data/generated_datasets/{dataset_id}'
    
    filepath = None
    dataset_type = None
    
    if os.path.exists(standard_path):
        filepath = standard_path
        dataset_type = 'standard'
    elif os.path.exists(generated_path):
        filepath = generated_path
        dataset_type = 'generated'
    else:
        return jsonify({'error': 'Dataset not found'}), 404
    
    try:
        # 读取jsonl文件
        qa_pairs = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        qa_pair = json.loads(line)
                        qa_pairs.append({
                            'line_num': line_num,
                            'question': qa_pair.get('question', ''),
                            'answer': qa_pair.get('answer', ''),
                            'metadata': {k: v for k, v in qa_pair.items() if k not in ['question', 'answer']}
                        })
                    except json.JSONDecodeError as e:
                        logger.error(f"解析第 {line_num} 行JSON失败: {e}")
                        continue
        
        # 获取文件信息
        file_stats = os.stat(filepath)
        created_at = datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
        modified_at = datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        return jsonify({
            'id': dataset_id,
            'name': dataset_id.replace('.jsonl', ''),
            'type': dataset_type,
            'count': len(qa_pairs),
            'created_at': created_at,
            'modified_at': modified_at,
            'data': qa_pairs,
            'evaluation_history': []  # TODO: 实现评测历史记录
        })
        
    except Exception as e:
        logger.error(f"读取数据集详情失败: {e}")
        return jsonify({'error': 'Failed to read dataset'}), 500

@app.route('/api/evaluation_data/save', methods=['POST'])
def save_evaluation_data():
    """保存评测数据"""
    data = request.json
    name = data.get('name')
    data_type = data.get('type', 'generated')
    qa_data = data.get('data', [])
    metadata = data.get('metadata', {})
    
    # 这里应该保存到evaluation_data目录
    import os
    import json
    
    # 创建目录
    dataset_dir = f"evaluation_data/{data_type}_datasets"
    os.makedirs(dataset_dir, exist_ok=True)
    
    # 保存数据为jsonl格式
    filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    filepath = os.path.join(dataset_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            # 以jsonl格式保存，每行一个QA对
            for qa_item in qa_data:
                # 处理两种数据结构：
                # 1. 直接的QA对：{"question": "...", "answer": "..."}
                # 2. 生成结果对象：{"qa_pair": {"question": "...", "answer": "..."}, "initial_entity": "..."}
                
                if 'qa_pair' in qa_item and qa_item['qa_pair']:
                    # 来自批量生成的结果对象
                    qa_pair = qa_item['qa_pair']
                    line_data = {
                        'question': qa_pair.get('question', ''),
                        'answer': qa_pair.get('answer', ''),
                        'entity': qa_item.get('initial_entity', ''),
                        'question_type': qa_pair.get('question_type', ''),
                        'complexity': qa_pair.get('complexity', ''),
                        'reasoning': qa_pair.get('reasoning', ''),  # 保持兼容性
                        'reasoning_path': qa_pair.get('reasoning_path', ''),  # 新增推理路径字段
                        **qa_item.get('metadata', {})
                    }
                else:
                    # 直接的QA对格式
                    line_data = {
                        'question': qa_item.get('question', ''),
                        'answer': qa_item.get('answer', ''),
                        **qa_item.get('metadata', {})
                    }
                
                f.write(json.dumps(line_data, ensure_ascii=False) + '\n')
        
        return jsonify({'success': True, 'filepath': filepath, 'filename': filename})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/evaluation_data/upload', methods=['POST'])
def upload_evaluation_data():
    """上传评测数据文件"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '文件名为空'})
    
    try:
        # 读取文件内容
        content = file.read().decode('utf-8')
        
        # 解析JSON
        data = json.loads(content)
        
        # 保存文件
        import os
        upload_dir = "evaluation_data/uploaded_datasets"
        os.makedirs(upload_dir, exist_ok=True)
        
        filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        filepath = os.path.join(upload_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'filepath': filepath})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# 评测执行API
@app.route('/api/evaluation/start', methods=['POST'])
def start_evaluation():
    """开始评测"""
    from lib.trace_manager import start_trace
    
    # 启动trace
    trace_id = start_trace(prefix="eval")
    
    data = request.json
    dataset_id = data.get('dataset_id')
    evaluator_type = data.get('evaluator_type', 'reasoning_model')
    model_name = data.get('model_name', 'gpt-4')
    
    logger.info(f"开始评测，数据集: {dataset_id}, 评测器: {evaluator_type}")
    
    # 创建评测任务
    evaluation_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # 计算总任务数
    total_tasks = 0
    try:
        # 确定数据集文件路径
        standard_path = f'evaluation_data/standard_datasets/{dataset_id}'
        generated_path = f'evaluation_data/generated_datasets/{dataset_id}'
        
        dataset_path = None
        if os.path.exists(standard_path):
            dataset_path = standard_path
        elif os.path.exists(generated_path):
            dataset_path = generated_path
        
        if dataset_path:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                total_tasks = sum(1 for line in f if line.strip())
    except Exception as e:
        logger.error(f"计算任务总数失败: {e}")
        total_tasks = 0
    
    # 在新线程中运行评测
    thread = threading.Thread(target=run_evaluation_process, args=(evaluation_id, data))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'evaluation_id': evaluation_id, 
        'message': '评测已开始',
        'total_tasks': total_tasks
    })

@app.route('/api/evaluation/stop', methods=['POST'])
def stop_evaluation():
    """停止评测"""
    # 这里应该停止正在运行的评测
    return jsonify({'message': '评测已停止'})

# 对比评测相关API
@app.route('/api/comparison/start', methods=['POST'])
def start_comparison():
    """开始对比评测"""
    from lib.trace_manager import start_trace
    
    # 启动trace
    trace_id = start_trace(prefix="comp")
    logger.info(f"接收对比评测请求")
    
    if building_status['is_running']:
        return jsonify({'error': '系统正在运行中'}), 400
    
    data = request.json
    
    # 验证必要参数
    if not data.get('datasetA') or not data.get('datasetB'):
        return jsonify({'error': '请选择两个数据文件'}), 400
    
    if data.get('datasetA', {}).get('id') == data.get('datasetB', {}).get('id'):
        return jsonify({'error': '不能选择相同的数据文件'}), 400
    
    try:
        # 创建对比评测ID
        comparison_id = f"comp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 重置状态
        building_status['is_running'] = True
        building_status['current_step'] = '对比评测初始化'
        building_status['progress'] = 0
        building_status['run_id'] = comparison_id
        
        logger.info(f"开始对比评测: {data.get('datasetA', {}).get('name')} vs {data.get('datasetB', {}).get('name')}")
        
        # 在新线程中运行对比评测
        thread = threading.Thread(target=run_comparison_process, args=(comparison_id, data))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'comparison_id': comparison_id,
            'message': '对比评测已开始'
        })
        
    except Exception as e:
        logger.error(f"启动对比评测失败: {e}")
        building_status['is_running'] = False
        return jsonify({'error': f'启动失败: {str(e)}'}), 500

@app.route('/api/comparison/stop', methods=['POST'])
def stop_comparison():
    """停止对比评测"""
    building_status['is_running'] = False
    building_status['current_step'] = '已停止'
    return jsonify({'message': '对比评测已停止'})

@app.route('/api/comparison/history')
def get_comparison_history():
    """获取对比评测历史记录"""
    try:
        from lib.comparison_evaluator import ComparisonEvaluator
        evaluator = ComparisonEvaluator()
        history = evaluator.get_comparison_history()
        
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        logger.error(f"获取对比历史失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/comparison/history/<comparison_id>')
def get_comparison_details(comparison_id):
    """获取对比评测详细结果"""
    try:
        from lib.comparison_evaluator import ComparisonEvaluator
        evaluator = ComparisonEvaluator()
        details = evaluator.get_comparison_details(comparison_id)
        
        if details is None:
            return jsonify({'error': '未找到对比记录'}), 404
        
        return jsonify(details)
        
    except Exception as e:
        logger.error(f"获取对比详情失败: {e}")
        return jsonify({'error': str(e)}), 500

def run_building_process(entity, max_nodes, sample_size, run_manager, max_iterations=3, sampling_algorithm='mixed'):
    """运行构建过程"""
    from lib.trace_manager import TraceManager, start_trace
    
    # 在新线程中需要重新设置trace（使用building_status中的run_id）
    if building_status.get('run_id'):
        # 创建基于run_id的trace
        trace_id = f"build_{building_status['run_id']}"
        start_trace(trace_id)
        logger.info(f"构建线程启动，trace_id: {trace_id}")
    else:
        start_trace(prefix="build")
        logger.info(f"构建线程启动，创建新trace")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger.info(f"开始异步构建过程: 实体={entity}, 最大节点={max_nodes}, 采样大小={sample_size}")
        result = loop.run_until_complete(async_building_process(entity, max_nodes, sample_size, run_manager, max_iterations, sampling_algorithm))
        logger.info(f"异步构建过程完成")
        
        # 保存结果
        run_manager.save_result(result, "knowledge_graph_result.json")
        
        # 提取QA结果
        qa_pair = result.get('qa_pair', {})
        building_status['qa_result'] = qa_pair
        
        # 发送完成事件，包含QA结果
        socketio.emit('building_complete', {
            'success': True,
            'result': result,
            'qa_result': qa_pair,
            'run_id': building_status['run_id'],
            'message': '知识图谱构建完成'
        })
        
        # 标记运行完成
        run_manager.complete_run(success=True)
        
    except Exception as e:
        logger.error(f"构建过程出错: {e}")
        
        # 标记运行失败
        run_manager.complete_run(success=False, error_message=str(e))
        
        socketio.emit('building_complete', {
            'success': False,
            'error': str(e),
            'run_id': building_status['run_id'],
            'message': '构建过程出错'
        })
    finally:
        building_status['is_running'] = False
        building_status['current_step'] = '完成'
        # 清理trace
        from lib.trace_manager import end_trace
        end_trace()

async def async_building_process(entity, max_nodes, sample_size, run_manager, max_iterations=3, sampling_algorithm='mixed', progress_callback=None):
    """异步构建过程"""
    try:
        # 获取运行路径
        run_paths = run_manager.get_run_paths()
        
        # 创建自定义设置实例，使用运行特定的路径
        from config import Settings
        custom_settings = Settings()
        custom_settings.GRAPHRAG_ROOT_DIR = run_paths['graphrag_root']
        custom_settings.GRAPHRAG_INPUT_DIR = run_paths['graphrag_input']
        custom_settings.GRAPHRAG_OUTPUT_DIR = run_paths['graphrag_output']
        custom_settings.GRAPHRAG_CACHE_DIR = run_paths['graphrag_cache']
        
        # 更新自定义参数
        custom_settings.MAX_NODES = max_nodes
        custom_settings.SAMPLE_SIZE = sample_size
        
        # 创建图更新回调函数
        def graph_update_callback(graph_data):
            """实时图更新回调"""
            try:
                socketio.emit('graph_update', graph_data)
                logger.info(f"发送实时图更新: {len(graph_data.get('nodes', []))} 个节点, {len(graph_data.get('links', []))} 个关系")
            except Exception as e:
                logger.error(f"发送实时图更新失败: {e}")
        
        # 创建GraphRagBuilder，传入自定义设置和图更新回调
        builder = GraphRagBuilder(custom_settings, graph_update_callback)
        
        def pipeline_progress_callback(step, progress):
            """流水线进度回调"""
            if progress_callback:
                progress_callback(step, progress)
            else:
                # 如果没有流水线回调，使用默认的进度更新
                update_progress(step, progress)
        
        result = await builder.build_knowledge_graph(
            entity, 
            pipeline_progress_callback, 
            max_iterations,
            sampling_algorithm=sampling_algorithm
        )
        
        # 只发送星座图采样信息，避免重复发送基础图数据
        if 'sample_info' in result:
            try:
                sample_info = result['sample_info']
                sampled_nodes = sample_info.get('nodes', [])
                sampled_relations = sample_info.get('relations', [])
                
                # 创建采样节点数据
                sampled_graph_nodes = []
                for node in sampled_nodes:
                    sampled_graph_nodes.append({
                        'id': node.get('name', f'Node_{len(sampled_graph_nodes)}'),
                        'name': node.get('name', f'Node_{len(sampled_graph_nodes)}'),
                        'type': node.get('type', 'unknown'),
                        'description': node.get('description', ''),
                        'group': hash(node.get('type', 'unknown')) % 10,
                        'sampled': True
                    })
                
                # 创建采样连线数据
                sampled_graph_links = []
                for relation in sampled_relations:
                    source = relation.get('source') or relation.get('head') or relation.get('from')
                    target = relation.get('target') or relation.get('tail') or relation.get('to')
                    if source and target:
                        relation_type = (relation.get('relationship') or 
                                       relation.get('relation') or 
                                       relation.get('type') or 
                                       'related_to')
                        sampled_graph_links.append({
                            'source': source,
                            'target': target,
                            'relation': relation_type,
                            'description': relation.get('description', ''),
                            'weight': relation.get('weight', 1.0),
                            'sampled': True
                        })
                
                # 发送星座图高亮事件
                socketio.emit('sampled_graph_update', {
                    'nodes': sampled_graph_nodes,
                    'links': sampled_graph_links
                })
                logger.info(f"发送星座图更新: {len(sampled_graph_nodes)} 个采样节点, {len(sampled_graph_links)} 个采样关系")
                
            except Exception as e:
                logger.error(f"发送星座图更新失败: {e}")
        
        # 发送QA结果
        if 'qa_pair' in result:
            socketio.emit('qa_generated', result['qa_pair'])
        
        # 输出QA对到控制台和日志
        qa_pair = result.get('qa_pair', {})
        if qa_pair:
            logger.info("\n" + "="*60)
            logger.info("🎯 生成的QA对:")
            logger.info("="*60)
            logger.info(f"问题类型: {qa_pair.get('question_type', 'N/A')}")
            logger.info(f"复杂度: {qa_pair.get('complexity', 'N/A')}")
            logger.info(f"\n❓ 问题:")
            logger.info(qa_pair.get('question', 'N/A'))
            logger.info(f"\n✅ 答案:")
            logger.info(qa_pair.get('answer', 'N/A'))
            if qa_pair.get('reasoning_path'):
                logger.info(f"\n🧠 推理路径:")
                logger.info(qa_pair.get('reasoning_path'))
            elif qa_pair.get('reasoning'):
                logger.info(f"\n🧠 推理过程:")
                logger.info(qa_pair.get('reasoning'))
            logger.info("="*60)
        
        return result
        
    except Exception as e:
        logger.error(f"异步构建过程出错: {e}")
        raise

def update_progress(step, progress):
    """更新进度"""
    building_status['current_step'] = step
    building_status['progress'] = progress
    
    socketio.emit('progress_update', {
        'step': step,
        'progress': progress
    })
    logger.info(f"进度更新: {step} ({progress}%)")

def update_graph_data(result):
    """更新图数据"""
    try:
        # 检查是否有完整的图信息（迭代过程中的增量更新）
        if 'graph_info' in result:
            graph_info = result['graph_info']
            entities = graph_info.get('entities', [])
            relationships = graph_info.get('relationships', [])
            
            graph_nodes = []
            for entity in entities:
                graph_nodes.append({
                    'id': entity.get('name', entity.get('id', f'Entity_{len(graph_nodes)}')),
                    'name': entity.get('name', entity.get('id', f'Entity_{len(graph_nodes)}')),
                    'type': entity.get('type', 'concept'),
                    'description': entity.get('description', ''),
                    'group': hash(entity.get('type', 'concept')) % 10
                })
            
            graph_links = []
            for relation in relationships:
                source = relation.get('source') or relation.get('head') or relation.get('from')
                target = relation.get('target') or relation.get('tail') or relation.get('to')
                if source and target:
                    # 正确获取关系类型，优先使用 relationship 字段
                    relation_type = (relation.get('relationship') or 
                                   relation.get('relation') or 
                                   relation.get('type') or 
                                   'related_to')
                    graph_links.append({
                        'source': source,
                        'target': target,
                        'relation': relation_type,
                        'description': relation.get('description', ''),
                        'weight': relation.get('weight', 1.0)
                    })
            
            building_status['graph_data'] = {
                'nodes': graph_nodes,
                'links': graph_links
            }
            
            socketio.emit('graph_update', building_status['graph_data'])
            
        # 检查是否有采样信息（星座图高亮）
        if 'sample_info' in result:
            sample_info = result['sample_info']
            sampled_nodes = sample_info.get('nodes', [])
            sampled_relations = sample_info.get('relations', [])
            
            # 创建采样节点数据
            sampled_graph_nodes = []
            for node in sampled_nodes:
                sampled_graph_nodes.append({
                    'id': node.get('name', f'Node_{len(sampled_graph_nodes)}'),
                    'name': node.get('name', f'Node_{len(sampled_graph_nodes)}'),
                    'type': node.get('type', 'unknown'),
                    'description': node.get('description', ''),
                    'group': hash(node.get('type', 'unknown')) % 10,
                    'sampled': True
                })
            
            # 创建采样连线数据
            sampled_graph_links = []
            for relation in sampled_relations:
                source = relation.get('source') or relation.get('head') or relation.get('from')
                target = relation.get('target') or relation.get('tail') or relation.get('to')
                if source and target:
                    relation_type = (relation.get('relationship') or 
                                   relation.get('relation') or 
                                   relation.get('type') or 
                                   'related_to')
                    sampled_graph_links.append({
                        'source': source,
                        'target': target,
                        'relation': relation_type,
                        'description': relation.get('description', ''),
                        'weight': relation.get('weight', 1.0),
                        'sampled': True
                    })
            
            # 发送星座图高亮事件
            socketio.emit('sampled_graph_update', {
                'nodes': sampled_graph_nodes,
                'links': sampled_graph_links
            })
        
    except Exception as e:
        logger.error(f"更新图数据失败: {e}")

@socketio.on('connect')
def handle_connect():
    """处理客户端连接"""
    logger.info("客户端已连接")
    emit('connected', {'message': '连接成功'})

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    logger.info("客户端已断开连接")

def run_batch_building_process(entities, run_manager):
    """运行批量构建过程"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        results = []
        total_entities = len(entities)
        
        for i, entity in enumerate(entities):
            logger.info(f"批量构建 ({i+1}/{total_entities}): {entity}")
            
            # 更新进度
            progress = int((i / total_entities) * 100)
            update_progress(f"处理实体: {entity}", progress)
            
            # 运行单个实体的构建
            result = loop.run_until_complete(async_building_process(entity, 30, 8, run_manager, 3))
            results.append({
                'entity': entity,
                'result': result
            })
            
            # 更新图数据
            update_graph_data(result)
            
            # 保存单个实体的结果
            run_manager.save_result(result, f"entity_{entity}_result.json")
        
        # 批量构建完成后，保存所有结果
        run_manager.save_result(results, "batch_knowledge_graph_results.json")
        
        socketio.emit('batch_building_complete', {
            'success': True,
            'results': results,
            'message': f'批量构建完成，共处理 {total_entities} 个实体'
        })
        
        # 标记运行完成
        run_manager.complete_run(success=True)
        
    except Exception as e:
        logger.error(f"批量构建过程出错: {e}")
        
        # 标记运行失败
        run_manager.complete_run(success=False, error_message=str(e))
        
        socketio.emit('batch_building_complete', {
            'success': False,
            'error': str(e),
            'message': '批量构建过程出错'
        })
    finally:
        building_status['is_running'] = False
        building_status['current_step'] = '批量完成'

def instant_save_result(result, config):
    """即时保存单个结果到文件"""
    try:
        instant_save_config = config.get('instant_save', {})
        if not instant_save_config.get('enabled'):
            return
        
        filename = instant_save_config.get('filename')
        if not filename:
            # 自动生成文件名
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"batch_generated_{timestamp}.jsonl"
        
        # 确保文件名以.jsonl结尾
        if not filename.endswith('.jsonl'):
            filename += '.jsonl'
        
        # 创建生成数据集目录
        dataset_dir = "evaluation_data/generated_datasets"
        os.makedirs(dataset_dir, exist_ok=True)
        
        filepath = os.path.join(dataset_dir, filename)
        
        # 只保存成功生成的QA对
        qa_pair = result.get('qa_pair', {})
        if qa_pair and qa_pair.get('question') and qa_pair.get('answer'):
            # 构建jsonl格式的数据
            line_data = {
                'question': qa_pair.get('question', ''),
                'answer': qa_pair.get('answer', ''),
                'question_type': qa_pair.get('question_type', ''),
                'complexity': qa_pair.get('complexity', ''),
                'reasoning': qa_pair.get('reasoning', ''),  # 保持兼容性
                'reasoning_path': qa_pair.get('reasoning_path', ''),  # 新增推理路径字段
                'entity': result.get('initial_entity', ''),
                'generated_at': datetime.now().isoformat()
            }
            
            # 追加写入文件
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(line_data, ensure_ascii=False) + '\n')
                f.flush()  # 立即刷新到磁盘
            
            logger.info(f"即时保存结果到: {filepath}")
        
    except Exception as e:
        logger.error(f"即时保存结果失败: {e}")

def run_batch_generation_process(config, run_manager):
    """批量生成过程 - 使用并行处理"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        entities = config.get('entities', [])
        parallel_workers = config.get('parallel_workers', 2)
        
        total_count = len(entities)
        results = []
        
        logger.info(f"开始批量生成，共 {total_count} 个实体，并行worker数: {parallel_workers}")
        
        # 检查是否启用即时保存
        instant_save_enabled = config.get('instant_save', {}).get('enabled', False)
        if instant_save_enabled:
            logger.info("启用即时保存模式")
        
        # 在新的事件循环中运行异步批量生成
        result = loop.run_until_complete(async_batch_generation_process(
            entities, config, run_manager, parallel_workers
        ))
        
        results = result
        
        # 如果没有启用即时保存，则在最后统一保存
        if not instant_save_enabled and results:
            import os
            import json
            from datetime import datetime
            
            # 创建生成数据集目录
            dataset_dir = "evaluation_data/generated_datasets"
            os.makedirs(dataset_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"batch_generated_{timestamp}.jsonl"
            filepath = os.path.join(dataset_dir, filename)
            
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    for result in results:
                        qa_pair = result.get('qa_pair', {})
                        if qa_pair.get('question') and qa_pair.get('answer'):
                            # 构建jsonl格式的数据
                            line_data = {
                                'question': qa_pair.get('question', ''),
                                'answer': qa_pair.get('answer', ''),
                                'question_type': qa_pair.get('question_type', ''),
                                'complexity': qa_pair.get('complexity', ''),
                                'reasoning': qa_pair.get('reasoning', ''),  # 保持兼容性
                                'reasoning_path': qa_pair.get('reasoning_path', ''),  # 新增推理路径字段
                                'entity': result.get('initial_entity', ''),
                                'generated_at': datetime.now().isoformat()
                            }
                            f.write(json.dumps(line_data, ensure_ascii=False) + '\n')
                
                logger.info(f"批量生成结果已保存到: {filepath}")
                
                # 发送完成信号（包含保存的文件信息）
                socketio.emit('batch_complete', {
                    'total': len(results),
                    'message': f'批量生成完成，共生成 {len(results)} 个QA对',
                    'saved_file': filename,
                    'saved_path': filepath
                })
                
            except Exception as e:
                logger.error(f"保存批量生成结果失败: {e}")
                # 即使保存失败，也发送完成信号
                socketio.emit('batch_complete', {
                    'total': len(results),
                    'message': f'批量生成完成，共生成 {len(results)} 个QA对（保存失败）'
                })
        else:
            # 即时保存模式下的完成信号
            instant_save_config = config.get('instant_save', {})
            filename = instant_save_config.get('filename', 'unknown')
            socketio.emit('batch_complete', {
                'total': len(results),
                'message': f'批量生成完成，共生成 {len(results)} 个QA对（即时保存）',
                'saved_file': filename,
                'instant_save': True
            })
        
        building_status['is_running'] = False
        building_status['current_step'] = '批量生成完成'
        building_status['progress'] = 100
        
    except Exception as e:
        logger.error(f"批量生成过程出错: {e}")
        socketio.emit('batch_error', {'message': f'批量生成失败: {str(e)}'})
        building_status['is_running'] = False

@app.route('/api/evaluation_data/results')
def get_evaluation_results():
    """获取评测结果汇总"""
    mode = request.args.get('mode', 'R1-0528')
    
    # 扫描evaluation_results目录
    results_dir = 'evaluation_data/evaluation_results'
    dataset_results = {}  # 用于存储每个数据集的最新结果
    
    if os.path.exists(results_dir):
        for filename in os.listdir(results_dir):
            if filename.endswith('.json'):
                try:
                    filepath = os.path.join(results_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    
                    if result_data.get('mode') == mode:
                        dataset_name = result_data.get('dataset_name', '')
                        submitted_at = result_data.get('submitted_at', '')
                        
                        # 保留最新的评测结果
                        if dataset_name not in dataset_results or submitted_at > dataset_results[dataset_name]['submitted_at']:
                            dataset_results[dataset_name] = {
                                'name': dataset_name,
                                'count': result_data.get('total_questions', 0),
                                'accuracy': result_data.get('accuracy', 0) * 100,  # 转换为百分比
                                'last_evaluation': result_data.get('timestamp', '').split('_')[0] if result_data.get('timestamp') else '',
                                'submitted_at': submitted_at,
                                'evaluation_id': result_data.get('evaluation_id', ''),
                                'status': 'completed',
                                'correct_count': result_data.get('correct_answers', 0)  # 修复字段名不匹配问题
                            }
                except Exception as e:
                    logger.error(f"读取评测结果文件 {filename} 失败: {e}")
                    continue
    
    # 转换为列表并按提交时间排序
    results = list(dataset_results.values())
    results.sort(key=lambda x: x['submitted_at'], reverse=True)
    
    return jsonify({'results': results})

@app.route('/api/evaluation_data/history/<dataset_id>')
def get_evaluation_history(dataset_id):
    """获取数据集的评测历史"""
    results_dir = 'evaluation_data/evaluation_results'
    history = []
    
    if os.path.exists(results_dir):
        for filename in os.listdir(results_dir):
            if filename.endswith('.json') and dataset_id.replace('.jsonl', '') in filename:
                try:
                    filepath = os.path.join(results_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    
                    history.append({
                        'mode': result_data.get('mode', 'R1-0528'),
                        'completed_at': result_data.get('submitted_at', '').replace('T', ' ').split('.')[0] if result_data.get('submitted_at') else '',
                        'total_questions': result_data.get('total_questions', 0),
                        'correct_count': result_data.get('correct_answers', 0),  # 修复字段名不匹配问题
                        'accuracy': round(result_data.get('accuracy', 0) * 100, 1)  # 转换为百分比并保留1位小数
                    })
                except Exception as e:
                    logger.error(f"读取历史记录文件 {filename} 失败: {e}")
                    continue
    
    # 按完成时间倒序排列
    history.sort(key=lambda x: x['completed_at'], reverse=True)
    
    return jsonify({'history': history})

def run_evaluation_process(evaluation_id, config):
    """评测过程"""
    from lib.trace_manager import start_trace
    
    # 在新线程中重新设置trace
    trace_id = f"eval_{evaluation_id}"
    start_trace(trace_id)
    logger.info(f"评测线程启动，evaluation_id: {evaluation_id}")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        logger.info(f"开始异步评测过程")
        result = loop.run_until_complete(async_evaluation_process(evaluation_id, config))
        logger.info(f"异步评测过程完成")
        
        socketio.emit('evaluation_complete', {
            'evaluation_id': evaluation_id,
            'results': result
        })
        
    except Exception as e:
        logger.error(f"评测过程出错: {e}")
        socketio.emit('evaluation_error', {'message': f'评测失败: {str(e)}'})
    finally:
        # 清理trace
        from lib.trace_manager import end_trace
        end_trace()

def run_comparison_process(comparison_id, config):
    """对比评测过程"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(async_comparison_process(comparison_id, config))
        
        socketio.emit('comparison_complete', {
            'comparison_id': comparison_id,
            'results': result
        })
        
        # 标记运行完成
        building_status['is_running'] = False
        building_status['current_step'] = '对比评测完成'
        
    except Exception as e:
        logger.error(f"对比评测过程出错: {e}")
        socketio.emit('comparison_error', {'message': f'对比评测失败: {str(e)}'})
        building_status['is_running'] = False
    finally:
        # 清理trace
        from lib.trace_manager import end_trace
        end_trace()

async def _process_single_generation_task(task_item: dict, config: dict, parent_run_manager, progress_callback=None):
    """处理单个生成任务的完整流水线：图构建 → 图采样 → 信息模糊化 → QA生成"""
    from lib.trace_manager import start_trace, TraceManager
    
    index = task_item["index"]
    entity = task_item["entity"]
    task_id = task_item["task_id"]
    
    # 为每个任务创建独立的trace
    batch_trace_id = TraceManager.get_trace_id()
    if batch_trace_id:
        item_trace_id = TraceManager.create_batch_trace_id(batch_trace_id, index)
        start_trace(item_trace_id)
    else:
        # 如果没有batch trace，创建独立的trace
        start_trace(prefix=f"task_{index}")
    
    try:
        # 为每个任务创建独立的运行管理器
        from lib.run_manager import RunManager
        task_run_manager = RunManager()
        task_run_id = task_run_manager.create_new_run(f"task_{index}_{entity}")
        
        # 阶段1：图构建
        if progress_callback:
            progress_callback(
                f"第{index}题: 构建知识图谱中...", 
                None,
                task_id=task_id,
                status="running"
            )
        
        logger.info(f"第{index}题: 开始构建知识图谱")
        
        # 运行图构建过程
        result = await async_building_process(
            entity, 
            config.get('max_nodes', 30), 
            config.get('sample_size', 8), 
            task_run_manager,  # 使用独立的运行管理器
            config.get('max_iterations', 3),
            config.get('sampling_algorithm', 'mixed'),
            progress_callback=lambda step, prog: progress_callback(
                f"第{index}题: {step}", 
                None,
                task_id=task_id,
                status="running"
            ) if progress_callback else None
        )
        
        if not result:
            raise ValueError("图构建失败")
            
        logger.info(f"第{index}题: 知识图谱构建完成")
        
        # 阶段2：结果验证
        if progress_callback:
            progress_callback(
                f"第{index}题: 验证结果完整性...", 
                None,
                task_id=task_id,
                status="running"
            )
        
        # 验证结果完整性
        if not result.get('qa_pair') or not result.get('graph_info'):
            raise ValueError("生成结果不完整")
            
        logger.info(f"第{index}题: 生成任务完成")
        
        # 将结果保存到父运行管理器中
        parent_run_manager.save_result(result, f"task_{index}_{entity}_result.json")
        
        # 标记任务运行完成
        task_run_manager.complete_run(success=True)
        
        return result
        
    except Exception as e:
        logger.error(f"第{index}题: 生成任务失败: {e}")
        if progress_callback:
            progress_callback(
                f"第{index}题: 生成失败 - {str(e)}", 
                None,
                task_id=task_id,
                status="error"
            )
        
        # 如果创建了任务运行管理器，标记为失败
        if 'task_run_manager' in locals():
            task_run_manager.complete_run(success=False, error_message=str(e))
        
        # 返回错误结果
        return {
            "initial_entity": entity,
            "qa_pair": None,
            "graph_info": {"node_count": 0, "relationship_count": 0},
            "error": str(e)
        }
    finally:
        # 清理trace
        from lib.trace_manager import end_trace
        end_trace()

async def async_batch_generation_process(entities, config, run_manager, parallel_workers):
    """异步批量生成过程 - 使用流水线并发模式"""
    try:
        total_tasks = len(entities)
        results = [None] * total_tasks  # 预分配结果数组
        
        # 创建任务队列
        task_queue = asyncio.Queue()
        
        # 完成计数器和锁
        completed_count = 0
        progress_lock = asyncio.Lock()
        
        # 将所有任务放入队列
        for i, entity in enumerate(entities):
            task_item = {
                "index": i + 1,
                "array_index": i,
                "entity": entity,
                "task_id": f"task_{i + 1}"
            }
            await task_queue.put(task_item)
        
        # 添加结束信号
        for _ in range(parallel_workers):
            await task_queue.put(None)
        
        # 使用信号量控制并发数量
        semaphore = asyncio.Semaphore(parallel_workers)
        
        # 进度回调函数
        def progress_callback(message, progress, task_id=None, status=None):
            progress_data = {
                'step': message,
                'progress': progress
            }
            
            if task_id:
                progress_data['task_id'] = task_id
            if message:
                progress_data['message'] = message
            if status:
                progress_data['status'] = status
                
            socketio.emit('batch_progress', progress_data)
        
        # 创建工作协程
        async def worker(worker_id: int):
            """工作协程 - 处理完整的流水线"""
            nonlocal completed_count
            
            while True:
                try:
                    # 从队列获取任务
                    task_item = await task_queue.get()
                    
                    if task_item is None:  # 结束信号
                        logger.debug(f"批量生成工作协程 {worker_id} 收到结束信号，退出")
                        break
                    
                    # 检查是否已经处理完所有任务
                    async with progress_lock:
                        if completed_count >= total_tasks:
                            logger.warning(f"批量生成工作协程 {worker_id}: 已完成所有任务，跳过额外任务")
                            break
                    
                    async with semaphore:
                        # 处理单个任务
                        result = await _process_single_generation_task(
                            task_item, 
                            config, 
                            run_manager,
                            progress_callback=progress_callback
                        )
                        
                        # 将结果存储到正确的位置
                        if result and "array_index" in task_item:
                            array_index = task_item["array_index"]
                            if 0 <= array_index < total_tasks:
                                results[array_index] = result
                        
                        # 即时保存结果（如果启用）
                        instant_save_result(result, config)
                        
                        # 发送单个结果
                        socketio.emit('batch_result', result)
                    
                    # 更新完成计数并通知进度
                    async with progress_lock:
                        completed_count += 1
                        progress_percent = min(completed_count / total_tasks * 100, 100)
                        
                        # 通知任务完成
                        if progress_callback and result:
                            status = "completed" if result.get("qa_pair") else "error"
                            progress_callback(
                                f"第{result.get('index', task_item['index'])}题: 完成 - {status.upper()} ({completed_count}/{total_tasks})", 
                                progress_percent,
                                task_id=task_item["task_id"],
                                status="completed"
                            )
                            
                        logger.debug(f"批量生成工作协程 {worker_id}: 完成第{task_item['index']}个实体 ({completed_count}/{total_tasks})")
                        
                except Exception as e:
                    logger.error(f"批量生成工作协程 {worker_id} 处理任务失败: {e}")
                    # 即使出错也要标记任务完成
                    async with progress_lock:
                        completed_count += 1
                        progress_percent = min(completed_count / total_tasks * 100, 100)
                        
                        # 通知任务失败
                        if progress_callback and task_item:
                            progress_callback(
                                f"第{task_item.get('index', '?')}题: 系统错误 ({completed_count}/{total_tasks})", 
                                progress_percent,
                                task_id=task_item.get("task_id", "unknown"),
                                status="error"
                            )
        
        # 启动工作协程
        workers = [asyncio.create_task(worker(i)) for i in range(parallel_workers)]
        
        # 等待所有工作协程结束
        await asyncio.gather(*workers, return_exceptions=True)
        
        # 过滤掉None结果并确保连续性
        valid_results = [r for r in results if r is not None]
        
        # 验证结果完整性
        if len(valid_results) != total_tasks:
            logger.warning(f"批量生成结果数量不匹配: 期望{total_tasks}个，实际{len(valid_results)}个")
        
        # 按索引排序结果
        valid_results.sort(key=lambda x: x.get("initial_entity", ""))
        
        return valid_results
        
    except Exception as e:
        logger.error(f"异步批量生成过程出错: {e}")
        return []

async def async_evaluation_process(evaluation_id, config):
    """异步评测过程"""
    from lib.trace_manager import TraceManager, start_trace
    
    # 继承或创建trace
    parent_trace = TraceManager.get_trace_id()
    if parent_trace:
        logger.info(f"异步评测继承trace: {parent_trace}")
    else:
        start_trace(prefix=f"eval_async")
        logger.info(f"异步评测创建新trace")
    
    try:
        from lib.evaluator import Evaluator
        
        dataset_id = config.get('dataset_id')
        evaluation_mode = config.get('evaluation_mode', 'R1-0528')
        
        logger.info(f"开始评测，评测ID: {evaluation_id}, 数据集: {dataset_id}, 模式: {evaluation_mode}")
        
        # 确定数据集文件路径
        standard_path = f'evaluation_data/standard_datasets/{dataset_id}'
        generated_path = f'evaluation_data/generated_datasets/{dataset_id}'
        
        dataset_path = None
        if os.path.exists(standard_path):
            dataset_path = standard_path
        elif os.path.exists(generated_path):
            dataset_path = generated_path
        else:
            raise ValueError(f"找不到数据集文件: {dataset_id}")
            
        # 计算总任务数
        total_tasks = 0
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                total_tasks = sum(1 for line in f if line.strip())
        except Exception as e:
            logger.error(f"计算任务总数失败: {e}")
            total_tasks = 0
        
        # 创建评测器
        evaluator = Evaluator()
        
        def progress_callback(message, progress, task_id=None, status=None):
            progress_data = {
                'evaluation_id': evaluation_id,
                'step': message,  # 使用message作为step
                'progress': progress
            }
            
            # 添加任务级别的信息
            if task_id:
                progress_data['task_id'] = task_id
            if message:
                progress_data['message'] = message
            if status:
                progress_data['status'] = status
                
            socketio.emit('evaluation_progress', progress_data)
        
        # 执行评测
        dataset_name = dataset_id.replace('.jsonl', '')
        batch_size = config.get('batch_size', 10)
        result = await evaluator.evaluate_dataset(
            dataset_path=dataset_path,
            dataset_name=dataset_name,
            mode=evaluation_mode,
            progress_callback=progress_callback,
            batch_size=batch_size
        )
        
        # 将total_tasks信息传递给前端
        config['total_tasks'] = total_tasks
        
        return result
        
    except Exception as e:
        logger.error(f"异步评测过程出错: {e}")
        raise

async def async_comparison_process(comparison_id, config):
    """异步对比评测过程"""
    try:
        from lib.comparison_evaluator import ComparisonEvaluator
        
        logger.info(f"开始对比评测，对比ID: {comparison_id}")
        
        # 创建对比评测器
        evaluator = ComparisonEvaluator()
        
        def progress_callback(message, progress, task_id=None, status=None, details=None):
            progress_data = {
                'comparison_id': comparison_id,
                'message': message,
                'percentage': progress if progress is not None else 0
            }
            
            # 添加任务级别的信息
            if task_id:
                progress_data['task_id'] = task_id
            if status:
                progress_data['status'] = status
            if details:
                progress_data['details'] = details
                
            socketio.emit('comparison_progress', progress_data)
        
        # 执行对比评测
        result = await evaluator.compare_datasets(config, progress_callback)
        
        return result
        
    except Exception as e:
        logger.error(f"异步对比评测过程出错: {e}")
        raise


# Runs QA生成相关API
runs_qa_generator = RunsQAGenerator()

@app.route('/api/runs/list', methods=['GET'])
def list_runs():
    """获取所有可用的运行记录"""
    try:
        runs = runs_qa_generator.list_available_runs()
        return jsonify({
            'success': True,
            'runs': runs
        })
    except Exception as e:
        logger.error(f"获取运行记录列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/runs/<run_id>/graph', methods=['GET'])
def get_run_graph(run_id):
    """获取指定运行记录的图数据"""
    try:
        graph_data = asyncio.run(runs_qa_generator.extract_graph_from_run(run_id))
        return jsonify({
            'success': True,
            'graph_data': graph_data
        })
    except Exception as e:
        logger.error(f"获取运行记录图数据失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/runs/generate-qa', methods=['POST'])
def generate_qa_from_runs():
    """从运行记录生成QA（支持QPS限制）"""
    from lib.trace_manager import start_trace
    
    try:
        # 启动trace
        trace_id = start_trace(prefix="runs")
        
        data = request.get_json()
        run_ids = data.get('run_ids', [])
        sample_size = data.get('sample_size', 10)
        sampling_algorithm = data.get('sampling_algorithm', 'mixed')
        questions_per_run = data.get('questions_per_run', 1)
        use_unified_qa = data.get('use_unified_qa', True)
        qps_limit = data.get('qps_limit', 2.0)
        parallel_workers = data.get('parallel_workers', 1)
        
        logger.info(f"开始从Runs生成QA，运行记录数: {len(run_ids)}, QPS限制: {qps_limit}")
        
        if not run_ids:
            return jsonify({
                'success': False,
                'error': '请选择至少一个运行记录'
            }), 400
        
        # 启动异步任务
        task_id = f"runs_qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        def generate_qa_task():
            try:
                # 进度回调函数
                def progress_callback(message, progress):
                    socketio.emit('runs_qa_progress', {
                        'task_id': task_id,
                        'message': message,
                        'progress': progress
                    })
                
                if len(run_ids) == 1:
                    # 单个运行记录
                    progress_callback("正在处理单个运行记录...", 10)
                    results = asyncio.run(runs_qa_generator.generate_qa_from_run(
                        run_id=run_ids[0],
                        sample_size=sample_size,
                        sampling_algorithm=sampling_algorithm,
                        num_questions=questions_per_run,
                        use_unified_qa=use_unified_qa
                    ))
                    
                    progress_callback("保存结果文件...", 90)
                    # 保存结果
                    output_file = f"qa_output/runs_qa_{task_id}.jsonl"
                    runs_qa_generator.save_qa_results(results, output_file)
                    
                    socketio.emit('runs_qa_complete', {
                        'task_id': task_id,
                        'success': True,
                        'results_count': len(results),
                        'output_file': output_file,
                        'qa_results': results  # 包含实际的QA内容
                    })
                else:
                    # 多个运行记录 - 使用QPS限制
                    progress_callback(f"开始批量处理 {len(run_ids)} 个记录（QPS限制: {qps_limit}）...", 5)
                    
                    results = asyncio.run(runs_qa_generator.batch_generate_from_multiple_runs_with_qps_limit(
                        run_ids=run_ids,
                        sample_size=sample_size,
                        sampling_algorithm=sampling_algorithm,
                        questions_per_run=questions_per_run,
                        use_unified_qa=use_unified_qa,
                        qps_limit=qps_limit,
                        parallel_workers=parallel_workers,
                        progress_callback=progress_callback
                    ))
                    
                    # 合并所有结果
                    all_results = []
                    for run_id, run_results in results.items():
                        all_results.extend(run_results)
                    
                    # 保存结果
                    output_file = f"qa_output/runs_qa_batch_{task_id}.jsonl"
                    runs_qa_generator.save_qa_results(all_results, output_file)
                    
                    socketio.emit('runs_qa_complete', {
                        'task_id': task_id,
                        'success': True,
                        'results_count': len(all_results),
                        'output_file': output_file,
                        'runs_processed': len(run_ids),
                        'qa_results': all_results  # 包含实际的QA内容
                    })
                    
            except Exception as e:
                logger.error(f"Runs QA生成任务失败: {e}")
                socketio.emit('runs_qa_complete', {
                    'task_id': task_id,
                    'success': False,
                    'error': str(e)
                })
        
        # 在后台线程中运行
        thread = threading.Thread(target=generate_qa_task)
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'QA生成任务已启动'
        })
        
    except Exception as e:
        logger.error(f"启动Runs QA生成失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/qa_output/<filename>')
def download_qa_file(filename):
    """下载QA结果文件"""
    try:
        return send_from_directory('qa_output', filename, as_attachment=True)
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        return jsonify({'error': '文件不存在或无法访问'}), 404


# 数据管理相关API
@app.route('/api/data_management/load/<filename>')
def load_data_file(filename):
    """加载数据文件，支持从多个目录查找"""
    try:
        import os
        import json
        from datetime import datetime
        
        # 定义要搜索的目录（按优先级排序）
        search_dirs = [
            "evaluation_data/generated_datasets",
            "evaluation_data/final_datasets", 
            "evaluation_data/final_datasets/label_datasets"
        ]
        
        # 查找文件
        file_path = None
        for search_dir in search_dirs:
            potential_path = os.path.join(search_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
        
        if not file_path:
            return jsonify({'success': False, 'error': '文件不存在'}), 404
        
        # 读取文件数据
        data = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        item = json.loads(line.strip())
                        # 确保必要字段存在
                        if 'question' not in item:
                            item['question'] = ''
                        if 'answer' not in item:
                            item['answer'] = ''
                        if 'reasoning_path' not in item:
                            item['reasoning_path'] = item.get('reasoning', '')
                        if 'mapped_reasoning_path' not in item:
                            item['mapped_reasoning_path'] = ''
                        if 'question_language' not in item:
                            item['question_language'] = 'unknown'
                        if 'answer_language' not in item:
                            item['answer_language'] = 'unknown'
                        
                        data.append(item)
                    except json.JSONDecodeError as e:
                        logger.warning(f"跳过无效JSON行 {line_num}: {e}")
                        continue
        
        # 获取文件信息
        file_stats = os.stat(file_path)
        file_info = {
            'filename': filename,
            'count': len(data),
            'size': file_stats.st_size,
            'modified_time': datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'directory': os.path.dirname(file_path)
        }
        
        return jsonify({
            'success': True,
            'data': data,
            'fileInfo': file_info
        })
        
    except Exception as e:
        logger.error(f"加载数据文件失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/detect_languages', methods=['POST'])
def detect_languages():
    """检测问题和答案的语言"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        items = data.get('data', [])
        
        if not filename or not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        logger.info(f"开始语言检测，共 {len(items)} 条数据")
        
        # 先使用简单检测，如果用户需要LLM检测可以单独调用
        results = []
        for item in items:
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            # 使用简单规则检测语言
            question_lang = detect_language_simple(question)
            answer_lang = detect_language_simple(answer)
            
            results.append({
                **item,
                'question_language': question_lang,
                'answer_language': answer_lang
            })
        
        logger.info(f"语言检测完成，处理了 {len(results)} 条数据")
        
        return jsonify({
            'success': True,
            'data': results
        })
        
    except Exception as e:
        logger.error(f"语言检测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/detect_languages_llm', methods=['POST'])
def detect_languages_llm():
    """使用LLM检测问题和答案的语言(高精度但较慢)"""
    try:
        data = request.get_json()
        items = data.get('data', [])
        
        if not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        logger.info(f"开始LLM语言检测，共 {len(items)} 条数据")
        
        # 批量检测语言
        from lib.llm_client import LLMClient
        llm_client = LLMClient()
        
        # 准备批量检测的文本
        batch_texts = []
        for i, item in enumerate(items):
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            # 截取文本避免token过多，每个字段最多500字符
            question_sample = question[:500] if question else ''
            answer_sample = answer[:500] if answer else ''
            
            batch_texts.append({
                'index': i,
                'question': question_sample,
                'answer': answer_sample
            })
        
        # 创建批量语言检测的prompt
        prompt_parts = ["请检测以下批量文本的语言类型，返回JSON数组格式：\n"]
        
        for text_item in batch_texts:
            prompt_parts.append(f"[{text_item['index']}] 问题: {text_item['question']}")
            prompt_parts.append(f"[{text_item['index']}] 答案: {text_item['answer']}\n")
        
        prompt_parts.append("""
请为每个索引返回语言检测结果，格式如下：
[
  {"index": 0, "question_language": "语言代码", "answer_language": "语言代码"},
  {"index": 1, "question_language": "语言代码", "answer_language": "语言代码"}
]

请使用ISO 639-1语言代码，支持的语言包括：
- zh: 中文 (Chinese)
- en: 英文 (English)
- ja: 日文 (Japanese)
- ko: 韩文 (Korean)
- fr: 法文 (French)
- de: 德文 (German)
- es: 西班牙文 (Spanish)
- it: 意大利文 (Italian)
- pt: 葡萄牙文 (Portuguese)
- ru: 俄文 (Russian)
- ar: 阿拉伯文 (Arabic)
- hi: 印地文 (Hindi)
- th: 泰文 (Thai)
- vi: 越南文 (Vietnamese)
- unknown: 实在无法确定的语言

只返回JSON数组，不要其他文字。""")
        
        full_prompt = '\n'.join(prompt_parts)
        
        # 检查prompt长度
        if len(full_prompt) > 150000:
            # 如果prompt太长，分批处理
            return process_large_batch_detection(items, llm_client)
        
        try:
            import asyncio
            response = asyncio.run(llm_client.generate_response(full_prompt))
            logger.info(f"LLM语言检测响应长度: {len(response)}")
            
            # 尝试解析JSON响应
            try:
                # 提取JSON部分
                json_start = response.find('[')
                json_end = response.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    detection_results = json.loads(json_str)
                else:
                    raise json.JSONDecodeError("未找到有效的JSON数组", response, 0)
                
                # 创建结果字典
                results_dict = {}
                for result in detection_results:
                    if isinstance(result, dict) and 'index' in result:
                        results_dict[result['index']] = result
                
                # 组装最终结果
                results = []
                for i, item in enumerate(items):
                    if i in results_dict:
                        result = results_dict[i]
                        question_lang = result.get('question_language', 'unknown')
                        answer_lang = result.get('answer_language', 'unknown')
                        
                        # 验证语言代码
                        valid_langs = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ar', 'hi', 'th', 'vi', 'unknown']
                        if question_lang not in valid_langs:
                            question_lang = 'unknown'
                        if answer_lang not in valid_langs:
                            answer_lang = 'unknown'
                            
                        results.append({
                            **item,
                            'question_language': question_lang,
                            'answer_language': answer_lang
                        })
                    else:
                        # 如果LLM没有返回这个索引的结果，使用简单检测
                        results.append({
                            **item,
                            'question_language': detect_language_simple(item.get('question', '')),
                            'answer_language': detect_language_simple(item.get('answer', ''))
                        })
                
                logger.info(f"LLM语言检测完成，处理了 {len(results)} 条数据")
                
                return jsonify({
                    'success': True,
                    'data': results
                })
                
            except json.JSONDecodeError as e:
                logger.warning(f"LLM返回非JSON格式，回退到简单检测: {e}")
                # 如果LLM返回的不是有效JSON，回退到简单检测
                results = []
                for item in items:
                    results.append({
                        **item,
                        'question_language': detect_language_simple(item.get('question', '')),
                        'answer_language': detect_language_simple(item.get('answer', ''))
                    })
                
                return jsonify({
                    'success': True,
                    'data': results
                })
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            # 发生错误时回退到简单检测
            results = []
            for item in items:
                results.append({
                    **item,
                    'question_language': detect_language_simple(item.get('question', '')),
                    'answer_language': detect_language_simple(item.get('answer', ''))
                })
            
            return jsonify({
                'success': True,
                'data': results
            })
        
    except Exception as e:
        logger.error(f"LLM语言检测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def process_large_batch_detection(items, llm_client):
    """处理大批量数据的语言检测"""
    import asyncio
    
    async def detect_single_item(item):
        """检测单个条目的语言"""
        try:
            question = item.get('question', '')
            answer = item.get('answer', '')
            
            # 截取文本避免token过多
            question_sample = question[:500] if question else ''
            answer_sample = answer[:500] if answer else ''
            
            # 创建单个检测的prompt
            prompt = f"""请检测以下文本的语言类型：

问题文本: {question_sample}
答案文本: {answer_sample}

请判断每个文本的主要语言，只返回以下格式的JSON：
{{"question_language": "语言代码", "answer_language": "语言代码"}}

请使用ISO 639-1语言代码，支持的语言包括：
- zh: 中文 (Chinese)
- en: 英文 (English)
- ja: 日文 (Japanese)
- ko: 韩文 (Korean)
- fr: 法文 (French)
- de: 德文 (German)
- es: 西班牙文 (Spanish)
- it: 意大利文 (Italian)
- pt: 葡萄牙文 (Portuguese)
- ru: 俄文 (Russian)
- ar: 阿拉伯文 (Arabic)
- hi: 印地文 (Hindi)
- th: 泰文 (Thai)
- vi: 越南文 (Vietnamese)
- unknown: 实在无法确定的语言"""
            
            response = await llm_client.generate_response(prompt)
            
            try:
                # 提取JSON部分
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    result = json.loads(json_str)
                    
                    question_lang = result.get('question_language', 'unknown')
                    answer_lang = result.get('answer_language', 'unknown')
                    
                    # 验证语言代码
                    valid_langs = ['zh', 'en', 'ja', 'ko', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'ar', 'hi', 'th', 'vi', 'unknown']
                    if question_lang not in valid_langs:
                        question_lang = 'unknown'
                    if answer_lang not in valid_langs:
                        answer_lang = 'unknown'
                    
                    return {
                        **item,
                        'question_language': question_lang,
                        'answer_language': answer_lang
                    }
                else:
                    raise json.JSONDecodeError("未找到有效的JSON", response, 0)
                    
            except json.JSONDecodeError:
                # 回退到简单检测
                return {
                    **item,
                    'question_language': detect_language_simple(question),
                    'answer_language': detect_language_simple(answer)
                }
                
        except Exception as e:
            logger.error(f"单个项目检测失败: {e}")
            return {
                **item,
                'question_language': detect_language_simple(item.get('question', '')),
                'answer_language': detect_language_simple(item.get('answer', ''))
            }
    
    async def process_all():
        tasks = [detect_single_item(item) for item in items]
        return await asyncio.gather(*tasks)
    
    results = asyncio.run(process_all())
    
    return jsonify({
        'success': True,
        'data': results
    })

def detect_language_simple(text):
    """简单的语言检测函数"""
    if not text or len(text.strip()) == 0:
        return 'unknown'
    
    # 移除空白字符进行统计
    text_clean = ''.join(text.split())
    if len(text_clean) == 0:
        return 'unknown'
    
    # 统计中文字符（包括中文标点）
    chinese_count = sum(1 for char in text_clean if '\u4e00' <= char <= '\u9fff' or 
                       '\u3000' <= char <= '\u303f' or '\uff00' <= char <= '\uffef')
    
    # 统计英文字母
    english_count = sum(1 for char in text_clean if char.isalpha() and ord(char) < 128)
    
    # 统计总字符数（排除空格和常见标点）
    total_chars = len(text_clean)
    
    if total_chars == 0:
        return 'unknown'
    
    chinese_ratio = chinese_count / total_chars
    english_ratio = english_count / total_chars
    
    logger.debug(f"语言检测 - 文本长度: {total_chars}, 中文比例: {chinese_ratio:.2f}, 英文比例: {english_ratio:.2f}")
    
    # 调整阈值，提高检测准确性
    if chinese_ratio > 0.05:  # 如果中文字符超过5%
        return 'zh'
    elif english_ratio > 0.3:  # 如果英文字符超过30%
        return 'en'
    else:
        return 'unknown'

@app.route('/api/data_management/save', methods=['POST'])
def save_data_file():
    """保存数据文件"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        items = data.get('data', [])
        
        if not filename or not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        import os
        import json
        from datetime import datetime
        
        # 定义要搜索的目录（按优先级排序）
        search_dirs = [
            "evaluation_data/generated_datasets",
            "evaluation_data/final_datasets", 
            "evaluation_data/final_datasets/label_datasets"
        ]
        
        # 查找原始文件位置
        file_path = None
        for search_dir in search_dirs:
            potential_path = os.path.join(search_dir, filename)
            if os.path.exists(potential_path):
                file_path = potential_path
                break
        
        # 如果文件不存在，默认保存到generated_datasets目录
        if not file_path:
            file_path = f'evaluation_data/generated_datasets/{filename}'
        
        # 创建备份
        if os.path.exists(file_path):
            backup_path = f'{file_path}.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            import shutil
            shutil.copy2(file_path, backup_path)
            logger.info(f"创建备份文件: {backup_path}")
        
        # 保存数据
        with open(file_path, 'w', encoding='utf-8') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        logger.info(f"数据文件已保存: {file_path}, 共 {len(items)} 条记录")
        
        return jsonify({
            'success': True,
            'message': f'已保存 {len(items)} 条记录'
        })
        
    except Exception as e:
        logger.error(f"保存数据文件失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/save_as', methods=['POST'])
def save_as_data_file():
    """另存为新数据文件"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        items = data.get('data', [])
        scope = data.get('scope', 'filtered')
        original_file = data.get('original_file', '')
        
        if not filename or not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        import os
        import json
        from datetime import datetime
        
        # 确定保存路径，默认保存到generated_datasets目录
        file_path = f'evaluation_data/generated_datasets/{filename}'
        
        # 检查文件是否已存在
        if os.path.exists(file_path):
            return jsonify({'success': False, 'error': f'文件 {filename} 已存在，请选择其他文件名'}), 400
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 保存数据
        with open(file_path, 'w', encoding='utf-8') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        
        # 记录操作信息
        scope_desc = {
            'filtered': '筛选后的数据',
            'all': '全部数据',
            'selected': '选中的数据'
        }.get(scope, '数据')
        
        logger.info(f"另存为新文件: {file_path}, 来源: {original_file}, 范围: {scope_desc}, 共 {len(items)} 条数据")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'count': len(items),
            'scope': scope_desc,
            'path': file_path
        })
        
    except Exception as e:
        logger.error(f"另存为失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# 实体映射和变量替换相关API
@app.route('/api/data_management/extract_entities', methods=['POST'])
def extract_entities():
    """从推理路径中提取实体和变量"""
    try:
        data = request.get_json()
        reasoning_path = data.get('reasoning_path', '')
        
        if not reasoning_path:
            return jsonify({'success': False, 'error': '推理路径不能为空'}), 400
        
        # 提取实体和变量
        entities = extract_entities_from_text(reasoning_path)
        
        return jsonify({
            'success': True,
            'entities': entities
        })
        
    except Exception as e:
        logger.error(f"提取实体失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/replace_entities', methods=['POST'])
def replace_entities():
    """替换推理路径中的实体"""
    try:
        data = request.get_json()
        reasoning_path = data.get('reasoning_path', '')
        entity_mapping = data.get('entity_mapping', {})
        
        if not reasoning_path:
            return jsonify({'success': False, 'error': '推理路径不能为空'}), 400
        
        # 执行实体替换
        new_reasoning_path = replace_entities_in_text(reasoning_path, entity_mapping)
        
        return jsonify({
            'success': True,
            'new_reasoning_path': new_reasoning_path,
            'replacements_made': len([k for k, v in entity_mapping.items() if k != v and k in reasoning_path])
        })
        
    except Exception as e:
        logger.error(f"替换实体失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def extract_entities_from_text(text):
    """从文本中提取可能的实体"""
    import re
    
    entities = []
    
    # 1. 提取专有名词（大写字母开头的词）
    proper_nouns = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b', text)
    entities.extend(proper_nouns)
    
    # 2. 提取括号中的内容（通常是实体的具体名称）
    parentheses_content = re.findall(r'\*\*([^*]+)\*\*', text)
    entities.extend(parentheses_content)
    
    # 3. 提取年份
    years = re.findall(r'\b(19|20)\d{2}\b', text)
    entities.extend(years)
    
    # 4. 提取地名和人名的特殊模式
    geographic_patterns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s*,\s*[A-Z][a-z]+)*\b', text)
    entities.extend(geographic_patterns)
    
    # 5. 去重并排序（按长度排序，长的在前面，避免替换时的冲突）
    unique_entities = list(set(entities))
    unique_entities = [e for e in unique_entities if len(e.strip()) > 2]  # 过滤太短的
    unique_entities.sort(key=len, reverse=True)
    
    # 6. 统计每个实体的出现次数
    entity_info = []
    for entity in unique_entities:
        count = text.count(entity)
        if count > 0:
            entity_info.append({
                'entity': entity,
                'count': count,
                'type': classify_entity_type(entity)
            })
    
    return entity_info

def classify_entity_type(entity):
    """简单分类实体类型"""
    import re
    
    if re.match(r'\b(19|20)\d{2}\b', entity):
        return 'year'
    elif entity[0].isupper() and ' ' in entity:
        return 'proper_name'
    elif entity[0].isupper():
        return 'name'
    else:
        return 'other'

def replace_entities_in_text(text, entity_mapping):
    """在文本中替换实体"""
    import re
    
    new_text = text
    
    # 按长度倒序排列，确保先替换长的实体，避免部分匹配问题
    sorted_entities = sorted(entity_mapping.items(), key=lambda x: len(x[0]), reverse=True)
    
    for old_entity, new_entity in sorted_entities:
        if old_entity != new_entity and old_entity.strip() and new_entity.strip():
            # 使用正则表达式进行精确匹配，避免部分匹配
            pattern = re.escape(old_entity)
            new_text = re.sub(pattern, new_entity, new_text)
    
    return new_text

@app.route('/api/data_management/get_languages', methods=['POST'])
def get_available_languages():
    """获取当前数据集中存在的语言列表"""
    try:
        data = request.get_json()
        items = data.get('data', [])
        
        if not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        # 收集所有出现的语言
        question_languages = set()
        answer_languages = set()
        
        for item in items:
            q_lang = item.get('question_language', 'unknown')
            a_lang = item.get('answer_language', 'unknown')
            
            if q_lang and q_lang.strip():
                question_languages.add(q_lang.strip())
            if a_lang and a_lang.strip():
                answer_languages.add(a_lang.strip())
        
        # 语言代码到显示名称的映射
        language_names = {
            'zh': '中文',
            'en': 'English',
            'ja': '日本語',
            'ko': '한국어',
            'fr': 'Français',
            'de': 'Deutsch',
            'es': 'Español',
            'it': 'Italiano',
            'pt': 'Português',
            'ru': 'Русский',
            'ar': 'العربية',
            'hi': 'हिन्दी',
            'th': 'ไทย',
            'vi': 'Tiếng Việt',
            'unknown': '未知语言'
        }
        
        # 构建语言选项
        question_options = []
        answer_options = []
        
        for lang in sorted(question_languages):
            question_options.append({
                'code': lang,
                'name': language_names.get(lang, lang)
            })
        
        for lang in sorted(answer_languages):
            answer_options.append({
                'code': lang,
                'name': language_names.get(lang, lang)
            })
        
        return jsonify({
            'success': True,
            'question_languages': question_options,
            'answer_languages': answer_options
        })
        
    except Exception as e:
        logger.error(f"获取语言列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/detect_domain_tags', methods=['POST'])
def detect_domain_tags():
    """
    [已废弃] 使用LLM检测问题的领域标签
    注意：此接口已废弃，请使用 detect_folder_domain_tags 接口，该接口具有完整的标签管理功能
    """
    try:
        data = request.get_json()
        items = data.get('data', [])
        existing_tags = data.get('existing_tags', [])
        
        if not items:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        logger.info(f"[已废弃接口] 开始领域标签检测，共 {len(items)} 条数据")
        
        from lib.llm_client import LLMClient
        llm_client = LLMClient()
        
        # 统一使用按字符数分批的逻辑
        results = process_batch_domain_detection(items, existing_tags, llm_client)
        # 收集所有标签
        all_tags = set(existing_tags)
        for result in results:
            if 'domain_tags' in result:
                all_tags.update(result['domain_tags'])
        
        logger.info(f"[已废弃接口] 领域标签检测完成，检测到 {len(all_tags)} 个不同标签")
        return jsonify({
            'success': True,
            'results': results,
            'all_tags': sorted(list(all_tags))
        })
        
    except Exception as e:
        logger.error(f"[已废弃接口] 领域标签检测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/data_management/detect_folder_domain_tags', methods=['POST'])
def detect_folder_domain_tags():
    """检测文件夹下所有JSONL文件的领域标签"""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')
        force_reprocess = data.get('force_reprocess', False)
        
        if not folder_path:
            return jsonify({'success': False, 'error': '请提供文件夹路径'}), 400
        
        # 确保路径存在
        if not os.path.exists(folder_path):
            return jsonify({'success': False, 'error': '文件夹不存在'}), 400
        
        if force_reprocess:
            logger.info(f"开始强制重新处理文件夹: {folder_path}")
        else:
            logger.info(f"开始处理文件夹: {folder_path}")
        
        from lib.llm_client import LLMClient
        llm_client = LLMClient()
        
        # 处理文件夹
        result = process_folder_domain_detection(folder_path, llm_client, force_reprocess)
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"文件夹领域标签检测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/data_management/get_domain_tags_info', methods=['GET'])
def get_domain_tags_info():
    """获取领域标签信息"""
    try:
        folder_path = request.args.get('folder_path', '')
        logger.info(f"获取领域标签信息请求，文件夹路径: {folder_path}")
        
        if not folder_path:
            logger.warning("未提供文件夹路径")
            return jsonify({'success': False, 'error': '请提供文件夹路径'}), 400
        
        # 检查文件夹是否存在
        if not os.path.exists(folder_path):
            logger.error(f"文件夹不存在: {folder_path}")
            return jsonify({'success': False, 'error': f'文件夹不存在: {folder_path}'}), 400
        
        if not os.path.isdir(folder_path):
            logger.error(f"路径不是文件夹: {folder_path}")
            return jsonify({'success': False, 'error': f'路径不是文件夹: {folder_path}'}), 400
            
        info_file = os.path.join(folder_path, 'domain_tags_info.json')
        logger.info(f"检查标签信息文件: {info_file}")
        
        if os.path.exists(info_file):
            logger.info("找到标签信息文件，正在读取...")
            try:
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                logger.info(f"成功读取标签信息，包含 {len(info.get('tags', {}))} 个标签")
            except json.JSONDecodeError as e:
                logger.error(f"标签信息文件格式错误: {e}")
                return jsonify({'success': False, 'error': f'标签信息文件格式错误: {e}'}), 500
            except UnicodeDecodeError as e:
                logger.error(f"标签信息文件编码错误: {e}")
                return jsonify({'success': False, 'error': f'标签信息文件编码错误: {e}'}), 500
        else:
            logger.info("未找到标签信息文件，返回默认信息")
            info = {
                'tags': {},
                'total_processed': 0,
                'last_updated': None,
                'file_processing_status': {}
            }
        
        logger.info(f"成功获取领域标签信息")
        return jsonify({
            'success': True,
            'info': info
        })
        
    except PermissionError as e:
        logger.error(f"权限错误: {e}")
        return jsonify({'success': False, 'error': f'权限错误，无法访问文件夹: {e}'}), 403
    except Exception as e:
        logger.error(f"获取领域标签信息失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


@app.route('/api/data_management/get_folder_data', methods=['GET'])
def get_folder_data():
    """获取文件夹中的所有JSON数据"""
    try:
        folder_path = request.args.get('folder_path', '')
        logger.info(f"获取文件夹数据请求，文件夹路径: {folder_path}")
        
        if not folder_path:
            logger.warning("未提供文件夹路径")
            return jsonify({'success': False, 'error': '请提供文件夹路径'}), 400
        
        # 检查文件夹是否存在
        if not os.path.exists(folder_path):
            logger.error(f"文件夹不存在: {folder_path}")
            return jsonify({'success': False, 'error': f'文件夹不存在: {folder_path}'}), 400
        
        if not os.path.isdir(folder_path):
            logger.error(f"路径不是文件夹: {folder_path}")
            return jsonify({'success': False, 'error': f'路径不是文件夹: {folder_path}'}), 400
        
        # 查找所有带标签的JSONL文件
        all_data = []
        processed_files = 0
        
        # 检查tagged子目录是否存在
        tagged_dir = os.path.join(folder_path, 'tagged')
        if os.path.exists(tagged_dir):
            search_dir = tagged_dir
        else:
            # 兼容旧版本，如果tagged目录不存在，还是从原目录查找
            search_dir = folder_path
            
        for filename in os.listdir(search_dir):
            if filename.endswith('_with_tags.jsonl'):
                file_path = os.path.join(search_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line_num, line in enumerate(f, 1):
                            line = line.strip()
                            if line:
                                try:
                                    item = json.loads(line)
                                    # 添加文件信息
                                    item['_source_file'] = filename
                                    item['_line_number'] = line_num
                                    all_data.append(item)
                                except json.JSONDecodeError as e:
                                    logger.warning(f"文件 {filename} 第 {line_num} 行JSON格式错误: {e}")
                                    continue
                    processed_files += 1
                    logger.info(f"已处理文件: {filename}")
                except Exception as e:
                    logger.error(f"读取文件 {filename} 失败: {e}")
                    continue
        
        logger.info(f"成功获取文件夹数据，共 {len(all_data)} 条数据，来自 {processed_files} 个文件")
        return jsonify({
            'success': True,
            'data': all_data,
            'total_items': len(all_data),
            'processed_files': processed_files
        })
        
    except PermissionError as e:
        logger.error(f"权限错误: {e}")
        return jsonify({'success': False, 'error': f'权限错误，无法访问文件夹: {e}'}), 403
    except Exception as e:
        logger.error(f"获取文件夹数据失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'服务器内部错误: {str(e)}'}), 500


def process_folder_domain_detection(folder_path, llm_client, force_reprocess=False):
    """处理文件夹下所有JSONL文件的领域标签检测"""
    import os
    import json
    from datetime import datetime
    
    try:
        # 初始化标签信息管理器
        tag_manager = DomainTagManager(folder_path)
        
        # 获取文件夹下所有JSONL文件
        jsonl_files = []
        for file in os.listdir(folder_path):
            if file.endswith('.jsonl') and not file.endswith('_with_tags.jsonl'):
                jsonl_files.append(file)
        
        if not jsonl_files:
            return {
                'message': '文件夹中没有找到JSONL文件',
                'processed_files': 0,
                'total_items': 0
            }
        
        logger.info(f"找到 {len(jsonl_files)} 个JSONL文件")
        
        total_processed_items = 0
        processed_files = 0
        cleared_files = 0
        
        for filename in jsonl_files:
            file_path = os.path.join(folder_path, filename)
            
                            # 如果是强制重新处理，先清理旧数据（无论之前是否处理过）
            if force_reprocess:
                if filename in tag_manager.info['file_processing_status']:
                    logger.info(f"强制重新处理文件: {filename}，先清理旧的处理数据")
                    tag_manager.clear_file_processing_data(filename)
                    cleared_files += 1
                    
                    # 删除旧的with_tags文件
                    tagged_dir = os.path.join(folder_path, 'tagged')
                    output_filename = filename.replace('.jsonl', '_with_tags.jsonl')
                    output_path = os.path.join(tagged_dir, output_filename)
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                            logger.info(f"已删除旧的标签文件: {output_path}")
                        except Exception as e:
                            logger.warning(f"删除旧标签文件失败: {e}")
                else:
                    logger.info(f"强制重新处理文件: {filename}，文件之前未处理过")
            else:
                # 非强制重新处理模式：检查是否需要处理该文件
                if tag_manager.is_file_processed(filename, file_path):
                    logger.info(f"跳过已处理的文件: {filename}")
                    continue
            
            logger.info(f"开始处理文件: {filename}")
            
            # 加载文件数据
            items = []
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            items.append(json.loads(line.strip()))
            except Exception as e:
                logger.error(f"读取文件 {filename} 失败: {e}")
                continue
            
            if not items:
                logger.info(f"文件 {filename} 为空，跳过")
                continue
            
            # 处理文件中的数据
            try:
                # 获取当前最新的标签集合
                current_tags = tag_manager.get_all_tags()
                
                # 分批处理数据
                results = process_batch_domain_detection_with_manager(
                    items, current_tags, llm_client, tag_manager
                )
                
                # 创建tagged子目录
                tagged_dir = os.path.join(folder_path, 'tagged')
                os.makedirs(tagged_dir, exist_ok=True)
                
                # 保存带标签的结果文件到子目录
                output_filename = filename.replace('.jsonl', '_with_tags.jsonl')
                output_path = os.path.join(tagged_dir, output_filename)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    for i, item in enumerate(items):
                        # 添加领域标签到原数据
                        enhanced_item = item.copy()
                        if i < len(results):
                            enhanced_item['domain_tags'] = results[i].get('domain_tags', [])
                        else:
                            enhanced_item['domain_tags'] = []
                        f.write(json.dumps(enhanced_item, ensure_ascii=False) + '\n')
                
                # 更新处理状态
                tag_manager.mark_file_processed(filename, len(items), results)
                
                total_processed_items += len(items)
                processed_files += 1
                
                if force_reprocess:
                    logger.info(f"文件 {filename} 重新处理完成，处理了 {len(items)} 条数据，已覆盖旧的标签文件")
                else:
                    logger.info(f"文件 {filename} 处理完成，处理了 {len(items)} 条数据")
                
            except Exception as e:
                logger.error(f"处理文件 {filename} 时出错: {e}")
                continue
        
        # 如果是强制重新处理，重新计算所有标签统计确保准确性
        if force_reprocess:
            logger.info("强制重新处理完成，重新计算所有标签统计")
            tag_manager.recalculate_all_tags()
            logger.info(f"强制重新处理概要: 清理了 {cleared_files} 个文件的旧数据，重新处理了 {processed_files} 个文件，清理了无用的标签")
        
        # 保存最终的标签信息
        tag_manager.save_info()
        
        mode_message = "重新处理" if force_reprocess else "处理"
        result_data = {
            'message': f'{mode_message}完成',
            'processed_files': processed_files,
            'total_files': len(jsonl_files),
            'total_items': total_processed_items,
            'tags_count': len(tag_manager.get_all_tags()),
            'force_reprocess': force_reprocess
        }
        
        if force_reprocess:
            result_data['cleared_files'] = cleared_files
            # 添加标签使用情况统计
            active_tags = sum(1 for tag_info in tag_manager.info['tags'].values() if tag_info.get('count', 0) > 0)
            result_data['active_tags'] = active_tags
            result_data['empty_tags'] = len(tag_manager.get_all_tags()) - active_tags
            
        return result_data
        
    except Exception as e:
        logger.error(f"文件夹处理失败: {e}")
        raise


class DomainTagManager:
    """领域标签信息管理器"""
    
    def __init__(self, folder_path):
        self.folder_path = folder_path
        self.info_file = os.path.join(folder_path, 'domain_tags_info.json')
        self.info = self._load_info()
    
    def _load_info(self):
        """加载标签信息"""
        if os.path.exists(self.info_file):
            try:
                with open(self.info_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载标签信息文件失败: {e}")
        
        # 返回默认结构
        return {
            'tags': {},
            'total_processed': 0,
            'last_updated': None,
            'file_processing_status': {}
        }
    
    def save_info(self):
        """保存标签信息"""
        from datetime import datetime
        self.info['last_updated'] = datetime.now().isoformat()
        
        # 最终验证数据一致性
        total_tag_count = sum(tag_info.get('count', 0) for tag_info in self.info['tags'].values())
        total_processed = self.info.get('total_processed', 0)
        
        if total_tag_count != total_processed and total_processed > 0:
            logger.warning(f"保存前发现数据不一致: 标签总计数({total_tag_count}) != 条目总数({total_processed})")
            # 可选：自动修正
            logger.info("正在修正total_processed...")
            self.info['total_processed'] = total_tag_count
        
        try:
            with open(self.info_file, 'w', encoding='utf-8') as f:
                json.dump(self.info, f, ensure_ascii=False, indent=2)
            logger.info(f"标签信息已保存: {len(self.info['tags'])} 个标签，{self.info['total_processed']} 条记录")
        except Exception as e:
            logger.error(f"保存标签信息文件失败: {e}")
    
    def get_all_tags(self):
        """获取所有标签列表"""
        return list(self.info['tags'].keys())
    
    def add_tag(self, tag_name, description=None):
        """添加新标签"""
        if tag_name not in self.info['tags']:
            self.info['tags'][tag_name] = {
                'count': 0,
                'description': description or ''
            }
    
    def update_tag_count(self, tag_name, count_increment=1):
        """更新标签计数"""
        if tag_name in self.info['tags']:
            self.info['tags'][tag_name]['count'] += count_increment
        else:
            self.add_tag(tag_name)
            self.info['tags'][tag_name]['count'] = count_increment
    
    def is_file_processed(self, filename, file_path):
        """检查文件是否已处理"""
        if filename not in self.info['file_processing_status']:
            return False
        
        file_status = self.info['file_processing_status'][filename]
        if not file_status.get('processed', False):
            return False
        
        # 检查文件是否被修改
        try:
            from datetime import datetime
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            recorded_modified_time = file_status.get('file_modified', '')
            
            if file_modified_time != recorded_modified_time:
                logger.info(f"文件 {filename} 已被修改，需要重新处理")
                return False
        except Exception as e:
            logger.error(f"检查文件修改时间失败: {e}")
            return False
        
        return True
    
    def clear_file_processing_data(self, filename):
        """清除文件的处理数据（用于重新处理）"""
        if filename in self.info['file_processing_status']:
            file_status = self.info['file_processing_status'][filename]
            
            # 从总处理数中减去该文件的处理数量
            if 'processed_count' in file_status:
                self.info['total_processed'] -= file_status['processed_count']
                if self.info['total_processed'] < 0:
                    self.info['total_processed'] = 0
            
            # 尝试从with_tags文件中精确计算该文件的标签贡献
            try:
                tagged_file_path = os.path.join(self.folder_path, 'tagged', filename.replace('.jsonl', '_with_tags.jsonl'))
                if os.path.exists(tagged_file_path):
                    logger.info(f"从with_tags文件精确计算文件 {filename} 的标签计数")
                    with open(tagged_file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                item = json.loads(line.strip())
                                domain_tags = item.get('domain_tags', [])
                                if isinstance(domain_tags, list):
                                    for tag in domain_tags:
                                        if tag in self.info['tags']:
                                            old_count = self.info['tags'][tag]['count']
                                            self.info['tags'][tag]['count'] -= 1
                                            if self.info['tags'][tag]['count'] < 0:
                                                self.info['tags'][tag]['count'] = 0
                                            logger.debug(f"标签 '{tag}' 计数: {old_count} -> {self.info['tags'][tag]['count']}")
                    logger.info(f"已从with_tags文件精确减去文件 {filename} 的标签计数")
                else:
                    # 如果with_tags文件不存在，使用备用方法
                    file_tags = file_status.get('tags', [])
                    if file_tags and file_status.get('processed_count', 0) > 0:
                        avg_per_tag = file_status['processed_count'] // len(file_tags)
                        logger.info(f"使用备用方法减去文件 {filename} 的标签计数，每个标签平均: {avg_per_tag}")
                        for tag in file_tags:
                            if tag in self.info['tags']:
                                old_count = self.info['tags'][tag]['count']
                                self.info['tags'][tag]['count'] -= avg_per_tag
                                if self.info['tags'][tag]['count'] < 0:
                                    self.info['tags'][tag]['count'] = 0
                                logger.debug(f"标签 '{tag}' 计数: {old_count} -> {self.info['tags'][tag]['count']}")
                    logger.info(f"使用备用方法完成文件 {filename} 的标签计数清理")
            except Exception as e:
                logger.warning(f"清除文件 {filename} 的标签计数时出错: {e}")
            
            # 清除文件处理状态
            del self.info['file_processing_status'][filename]
            logger.info(f"已清除文件 {filename} 的处理数据，准备重新处理")

    def mark_file_processed(self, filename, processed_count, file_tags=None):
        """标记文件已处理"""
        from datetime import datetime
        file_path = os.path.join(self.folder_path, filename)
        try:
            file_modified_time = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
        except Exception:
            file_modified_time = datetime.now().isoformat()
        
        # 收集文件中的所有标签
        all_file_tags = set()
        if file_tags:
            for result in file_tags:
                tags = result.get('domain_tags', [])
                if isinstance(tags, list):
                    all_file_tags.update(tags)
        
        self.info['file_processing_status'][filename] = {
            'processed': True,
            'processed_count': processed_count,
            'last_processed': datetime.now().isoformat(),
            'file_modified': file_modified_time,
            'tags': list(all_file_tags)  # 保存文件包含的所有标签
        }
        
        self.info['total_processed'] += processed_count

    def recalculate_all_tags(self):
        """重新计算所有标签统计（用于强制重新处理后确保数据准确性）"""
        logger.info("开始重新计算所有标签统计...")
        
        # 清空所有现有标签，重新开始
        old_tags = list(self.info['tags'].keys())
        self.info['tags'] = {}
        
        # 初始化预定义标签（确保所有预定义标签都存在，即使计数为0）
        predefined_tags = {'体育', '学术', '政治', '娱乐', '文学', '文化', '经济', '科技', '历史', '医疗', '其他'}
        for tag in predefined_tags:
            self.add_tag(tag)
        
        # 重置总处理数
        self.info['total_processed'] = 0
        
        # 遍历所有已处理的文件，重新计算
        tagged_dir = os.path.join(self.folder_path, 'tagged')
        if os.path.exists(tagged_dir):
            recalculated_files = 0
            found_tags = set()
            
            for filename, file_status in self.info['file_processing_status'].items():
                if file_status.get('processed', False):
                    tagged_filename = filename.replace('.jsonl', '_with_tags.jsonl')
                    tagged_file_path = os.path.join(tagged_dir, tagged_filename)
                    
                    if os.path.exists(tagged_file_path):
                        try:
                            file_item_count = 0
                            file_tags = set()
                            
                            with open(tagged_file_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.strip():
                                        file_item_count += 1
                                        item = json.loads(line.strip())
                                        domain_tags = item.get('domain_tags', [])
                                        if isinstance(domain_tags, list):
                                            # 在单标签模式下，每个条目应该只有一个标签
                                            if len(domain_tags) > 1:
                                                logger.warning(f"发现多标签条目 {domain_tags}，将只使用第一个有效标签")
                                            
                                            # 只选择第一个有效的预定义标签
                                            selected_tag = None
                                            for tag in domain_tags:
                                                found_tags.add(tag)
                                                if tag in predefined_tags:
                                                    selected_tag = tag
                                                    break
                                                else:
                                                    logger.warning(f"发现非预定义标签 '{tag}'")
                                            
                                            # 如果没有找到有效标签，使用"其他"
                                            if not selected_tag:
                                                selected_tag = '其他'
                                            
                                            # 只为选中的标签计数一次
                                            file_tags.add(selected_tag)
                                            if selected_tag in self.info['tags']:
                                                self.info['tags'][selected_tag]['count'] += 1
                                            else:
                                                # 如果标签不在info中，添加它
                                                self.add_tag(selected_tag)
                                                self.info['tags'][selected_tag]['count'] += 1
                            
                            # 更新文件的处理数量和标签列表
                            file_status['processed_count'] = file_item_count
                            file_status['tags'] = list(file_tags)
                            self.info['total_processed'] += file_item_count
                            recalculated_files += 1
                            
                            logger.debug(f"文件 {filename}: {file_item_count} 条数据，标签: {sorted(file_tags)}")
                            
                        except Exception as e:
                            logger.warning(f"重新计算文件 {filename} 的标签统计时出错: {e}")
                    else:
                        logger.warning(f"标签文件不存在: {tagged_file_path}")
            
            # 清理不再使用的标签（不在预定义列表中的标签）
            tags_to_remove = []
            for tag_name in self.info['tags']:
                if tag_name not in predefined_tags:
                    tags_to_remove.append(tag_name)
            
            if tags_to_remove:
                logger.info(f"清理非预定义标签: {tags_to_remove}")
                for tag_name in tags_to_remove:
                    old_count = self.info['tags'][tag_name].get('count', 0)
                    del self.info['tags'][tag_name]
                    logger.debug(f"已删除标签 '{tag_name}' (原计数: {old_count})")
            else:
                logger.info("没有需要清理的非预定义标签")
            
            logger.info(f"重新计算完成，处理了 {recalculated_files} 个文件的标签统计")
            logger.info(f"发现的标签: {sorted(found_tags)}")
            logger.info(f"清理了 {len(old_tags) - len(self.info['tags'])} 个旧标签")
            logger.info(f"总处理条目数: {self.info['total_processed']}")
            
            # 打印最终的标签统计（只显示有数据的标签）
            active_tags = 0
            total_tag_count = 0
            for tag_name, tag_info in sorted(self.info['tags'].items()):
                count = tag_info['count']
                total_tag_count += count
                if count > 0:
                    percentage = (count / self.info['total_processed'] * 100) if self.info['total_processed'] > 0 else 0
                    logger.info(f"标签 '{tag_name}': {count} 次 ({percentage:.1f}%)")
                    active_tags += 1
                else:
                    logger.debug(f"标签 '{tag_name}': {count} 次 (无数据)")
            
            logger.info(f"共 {active_tags} 个标签有数据，{len(self.info['tags']) - active_tags} 个标签无数据")
            logger.info(f"标签总计数: {total_tag_count}，条目总数: {self.info['total_processed']}")
            
            # 验证数据一致性
            if total_tag_count != self.info['total_processed']:
                logger.warning(f"数据不一致！标签总计数({total_tag_count}) != 条目总数({self.info['total_processed']})")
            else:
                logger.info("数据一致性验证通过")
        else:
            logger.warning(f"标签目录不存在: {tagged_dir}")


def process_batch_domain_detection_with_manager(items, existing_tags, llm_client, tag_manager):
    """带标签管理器的批量领域标签检测"""
    try:
        max_chars_per_batch = 70000  # 每批最大字符数
        all_results = []
        
        logger.info(f"分批处理 {len(items)} 个数据项，每批最大 {max_chars_per_batch} 字符")
        
        current_batch = []
        current_batch_chars = 0
        batch_count = 0
        
        for i, item in enumerate(items):
            question = item.get('question', '')
            reasoning_path = item.get('mapped_reasoning_path', '')
            
            # 计算当前项目的字符数（不截断）
            item_chars = len(question) + len(reasoning_path)
            
            # 检查是否需要开始新批次
            if current_batch and (current_batch_chars + item_chars > max_chars_per_batch):
                # 处理当前批次
                batch_count += 1
                logger.info(f"处理第 {batch_count} 批，包含 {len(current_batch)} 个项目，总字符数: {current_batch_chars}")
                
                # 获取最新的标签集合（每批次都获取最新的）
                current_tags = tag_manager.get_all_tags()
                batch_results = _process_batch_with_manager(current_batch, current_tags, llm_client, tag_manager, batch_count)
                all_results.extend(batch_results)
                
                # 重置批次
                current_batch = []
                current_batch_chars = 0
            
            # 添加到当前批次
            current_batch.append({
                'item': item,
                'global_index': i,
                'question': question,
                'reasoning_path': reasoning_path
            })
            current_batch_chars += item_chars
        
        # 处理最后一个批次
        if current_batch:
            batch_count += 1
            logger.info(f"处理第 {batch_count} 批，包含 {len(current_batch)} 个项目，总字符数: {current_batch_chars}")
            current_tags = tag_manager.get_all_tags()
            batch_results = _process_batch_with_manager(current_batch, current_tags, llm_client, tag_manager, batch_count)
            all_results.extend(batch_results)
        
        # 按索引排序结果
        all_results.sort(key=lambda x: x['index'])
        
        # 确保所有项目都有结果，缺失的标记为"其他"
        for i in range(len(items)):
            if not any(result['index'] == i for result in all_results):
                all_results.append({'index': i, 'domain_tags': ['其他']})
                tag_manager.update_tag_count('其他')
        
        # 再次排序
        all_results.sort(key=lambda x: x['index'])
        
        return all_results
        
    except Exception as e:
        logger.error(f"批量处理出错: {e}")
        # 返回默认结果（标记为"其他"）
        for i in range(len(items)):
            tag_manager.update_tag_count('其他')
        return [{'index': i, 'domain_tags': ['其他']} for i in range(len(items))]


def _process_batch_with_manager(batch_items, existing_tags, llm_client, tag_manager, batch_number):
    """处理单个批次并更新标签管理器"""
    try:
        # 准备当前批次的文本
        batch_texts = []
        for j, batch_item in enumerate(batch_items):
            batch_texts.append({
                'index': j,  # 批次内的索引
                'global_index': batch_item['global_index'],  # 全局索引
                'question': batch_item['question'],
                'reasoning_path': batch_item['reasoning_path']
            })
        
        # 创建当前批次的prompt
        existing_tags_str = ', '.join(sorted(existing_tags)) if existing_tags else '无'
        
        prompt_parts = [
            "请分析以下问题和推理路径，为每个问题识别对应的领域标签。",
            "",
            "请根据问题内容和推理过程，为每个问题选择一个最符合的领域标签。",
            "请只从以下预定义的领域标签中选择一个最符合的标签，不要创建新标签：",
            "",
            "可选标签：",
            "- 体育：运动竞技、体育赛事、健身锻炼",
            "- 学术：科学研究、学术理论、教育知识",
            "- 政治：政府政策、政治制度、国际关系",
            "- 娱乐：影视音乐、游戏娱乐、明星八卦",
            "- 文学：文学作品、诗歌散文、文学创作",
            "- 文化：传统文化、艺术文化、社会文化",
            "- 经济：商业金融、市场经济、投资理财",
            "- 科技：计算机技术、人工智能、科技产品",
            "- 历史：历史事件、历史人物、历史研究",
            "- 医疗：医学治疗、健康养生、疾病诊断",
            "- 其他：不属于以上任何领域的问题",
            "",
            "分类规则：",
            "1. 多领域相关时：选择问题核心内容和主要目的最相关的领域",
            "2. 相关性判断：只有当问题与某个领域有明确、直接的关联时才选择该领域",
            "3. 避免强行归类：如果问题与所有预定义领域的相关性都很弱，果断选择'其他'",
            "4. 优先级判断：问题的主要讨论焦点 > 背景信息 > 附带提及的内容",
            "",
            "示例：",
            "- 'NBA球员的营养饮食建议' → 体育（核心是体育相关的饮食，而非一般医疗）",
            "- '如何用Python分析股票数据' → 科技（核心是编程技术，而非金融分析）",
            "- '明星在电影中的历史服装' → 娱乐（核心是影视内容，历史只是背景）",
            "- '今天天气真好' → 其他（与所有领域相关性都很弱）",
            "",
            "数据列表：\n"
        ]
        
        for text_item in batch_texts:
            prompt_parts.append(f"[{text_item['index']}] 问题: {text_item['question']}")
            if text_item['reasoning_path']:
                prompt_parts.append(f"[{text_item['index']}] 推理: {text_item['reasoning_path']}")
            prompt_parts.append("")
        
        prompt_parts.append("""
请为每个索引返回领域标签识别结果，格式如下：
[
  {"index": 0, "domain_tags": ["体育"]},
  {"index": 1, "domain_tags": ["医疗"]},
  {"index": 2, "domain_tags": ["其他"]}
]

重要提醒：
- 只能使用以上列出的11个标签：体育、学术、政治、娱乐、文学、文化、经济、科技、历史、医疗、其他
- 每个问题只能选择一个最符合的标签
- 多领域交叉时，选择问题核心内容最相关的那个领域
- 相关性不足时，宁可选择"其他"也不要强行归类到不太相关的领域
- 必须从预定义列表中选择，只返回中文标签名称

只返回JSON数组，不要其他文字。""")
        
        full_prompt = '\n'.join(prompt_parts)
        logger.info(f"第 {batch_number} 批次包含 {len(batch_texts)} 个问题，索引范围: {[item['global_index'] for item in batch_texts]}，单标签模式: {sorted(PREDEFINED_DOMAIN_TAGS)}")
        
        batch_results = []
        
        try:
            import asyncio
            response = asyncio.run(llm_client.generate_response(full_prompt))
            
            # 解析当前批次的结果
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                detection_results = json.loads(json_str)
                
            for result in detection_results:
                if isinstance(result, dict) and 'index' in result:
                    batch_index = result['index']
                    if 0 <= batch_index < len(batch_texts):
                        global_index = batch_texts[batch_index]['global_index']
                        tags = result.get('domain_tags', [])
                        if isinstance(tags, list):
                            # 使用预定义的标签列表
                            valid_tags = PREDEFINED_DOMAIN_TAGS
                            
                            # 如果模型返回了多个标签，记录警告
                            if len(tags) > 1:
                                logger.warning(f"模型返回了多个标签 {tags}，将只选择第一个有效标签")
                            
                            selected_tag = None
                            
                            # 只选择第一个有效的标签
                            for tag in tags:
                                if isinstance(tag, str) and tag.strip():
                                    clean_tag = tag.strip()
                                    # 验证标签是否在预定义列表中
                                    if clean_tag in valid_tags:
                                        selected_tag = clean_tag
                                        break  # 找到第一个有效标签就停止
                                    else:
                                        # 如果标签不在预定义列表中，记录日志
                                        logger.warning(f"检测到未预定义标签 '{clean_tag}'，将寻找其他有效标签或使用'其他'")
                            
                            # 如果没有找到有效标签，默认使用"其他"
                            if not selected_tag:
                                selected_tag = '其他'
                                logger.info(f"未找到有效标签，默认使用'其他'")
                            
                            clean_tags = [selected_tag]
                            # 实时更新标签管理器
                            tag_manager.update_tag_count(selected_tag)
                            
                            # 只为每个问题添加一次结果，不是每个标签添加一次
                            batch_results.append({
                                'index': global_index,
                                'domain_tags': clean_tags
                            })
                            logger.debug(f"批次 {batch_number}: 为全局索引 {global_index} 选择标签 '{selected_tag}'")
                    else:
                        logger.warning(f"批次索引 {batch_index} 超出范围，批次大小: {len(batch_texts)}")
        
        except Exception as e:
            logger.error(f"处理第 {batch_number} 批时出错: {e}")
            # 为当前批次添加默认结果（标记为"其他"）
            for batch_item in batch_items:
                batch_results.append({
                    'index': batch_item['global_index'],
                    'domain_tags': ['其他']
                })
                tag_manager.update_tag_count('其他')
        
        logger.info(f"批次 {batch_number} 处理完成，输入 {len(batch_texts)} 个问题，输出 {len(batch_results)} 个结果")
        return batch_results

    except Exception as e:
        logger.error(f"批次 {batch_number} 处理异常: {e}")
        # 为当前批次添加默认结果（标记为"其他"）
        batch_results = []
        for batch_item in batch_items:
            batch_results.append({
                'index': batch_item['global_index'],
                'domain_tags': ['其他']
            })
            tag_manager.update_tag_count('其他')
        return batch_results


def process_batch_domain_detection(items, existing_tags, llm_client):
    """
    [已废弃] 处理领域标签检测，按字符数智能分批
    注意：此函数已废弃，请使用 process_batch_domain_detection_with_manager，该函数具有完整的标签管理功能
    """
    try:
        max_chars_per_batch = 70000  # 每批最大字符数
        all_results = []
        all_tags = set(existing_tags)
        
        logger.info(f"[已废弃函数] 分批处理 {len(items)} 个数据项，每批最大 {max_chars_per_batch} 字符")
        
        current_batch = []
        current_batch_chars = 0
        batch_count = 0
        
        for i, item in enumerate(items):
            question = item.get('question', '')
            reasoning_path = item.get('mapped_reasoning_path', '')
            
            # 计算当前项目的字符数（不截断）
            item_chars = len(question) + len(reasoning_path)
            
            # 检查是否需要开始新批次
            if current_batch and (current_batch_chars + item_chars > max_chars_per_batch):
                # 处理当前批次
                batch_count += 1
                logger.info(f"[已废弃函数] 处理第 {batch_count} 批，包含 {len(current_batch)} 个项目，总字符数: {current_batch_chars}")
                _process_batch(current_batch, all_results, all_tags, llm_client, batch_count)
                
                # 重置批次
                current_batch = []
                current_batch_chars = 0
            
            # 添加到当前批次
            current_batch.append({
                'item': item,
                'global_index': i,
                'question': question,
                'reasoning_path': reasoning_path
            })
            current_batch_chars += item_chars
        
        # 处理最后一个批次
        if current_batch:
            batch_count += 1
            logger.info(f"[已废弃函数] 处理第 {batch_count} 批，包含 {len(current_batch)} 个项目，总字符数: {current_batch_chars}")
            _process_batch(current_batch, all_results, all_tags, llm_client, batch_count)
        
        # 按索引排序结果
        all_results.sort(key=lambda x: x['index'])
        
        # 确保所有项目都有结果
        for i in range(len(items)):
            if not any(result['index'] == i for result in all_results):
                all_results.append({'index': i, 'domain_tags': []})
        
        # 再次排序
        all_results.sort(key=lambda x: x['index'])
        
        return all_results
        
    except Exception as e:
        logger.error(f"大批量处理出错: {e}")
        # 返回空结果
        return [{'index': i, 'domain_tags': []} for i in range(len(items))]


def _process_batch(batch_items, all_results, all_tags, llm_client, batch_number):
    """
    [已废弃] 处理单个批次的领域标签检测
    注意：此函数已废弃，请使用 _process_batch_with_manager，该函数具有完整的标签管理功能
    """
    try:
        # 准备当前批次的文本
        batch_texts = []
        for j, batch_item in enumerate(batch_items):
            batch_texts.append({
                'index': j,  # 批次内的索引
                'global_index': batch_item['global_index'],  # 全局索引
                'question': batch_item['question'],
                'reasoning_path': batch_item['reasoning_path']
            })
            
            # 创建当前批次的prompt
            existing_tags_str = ', '.join(sorted(all_tags)) if all_tags else '无'
            
            prompt_parts = [
                "请分析以下问题和推理路径，为每个问题识别对应的领域标签。",
                f"当前已存在的标签: {existing_tags_str}",
                "",
                "请根据问题内容和推理过程，识别每个问题属于的领域。一个问题可以有多个标签。",
                "优先使用已存在的标签，如果需要新标签请确保标签简洁明确。",
                "",
                "数据列表：\n"
            ]
            
            for text_item in batch_texts:
                prompt_parts.append(f"[{text_item['index']}] 问题: {text_item['question']}")
                if text_item['reasoning_path']:
                    prompt_parts.append(f"[{text_item['index']}] 推理: {text_item['reasoning_path']}")
                prompt_parts.append("")
            
            prompt_parts.append("""
请为每个索引返回领域标签识别结果，格式如下：
[
  {"index": 0, "domain_tags": ["标签1", "标签2"]},
  {"index": 1, "domain_tags": ["标签3"]}
]

标签建议包括但不限于：
- 医学: 医疗诊断、疾病治疗、药物知识、医学检查
- 法律: 法律条文、司法程序、法律咨询、合同法务
- 科技: 计算机科学、人工智能、软件工程、网络技术
- 教育: 教学方法、学科知识、教育理论、学习指导
- 金融: 投资理财、银行业务、保险知识、经济分析
- 生活: 日常生活、健康养生、美食烹饪、家居装修
- 历史: 历史事件、人物传记、文化传承、历史研究
- 文学: 文学作品、写作技巧、语言艺术、文学批评
- 科学: 物理化学、生物学、地理学、天文学
- 商业: 企业管理、市场营销、商业策略、创业指导

只返回JSON数组，不要其他文字。""")
            
            full_prompt = '\n'.join(prompt_parts)
            logger.info(f"当前批次的prompt: {full_prompt}")
            
            try:
                import asyncio
                response = asyncio.run(llm_client.generate_response(full_prompt))
                
                # 解析当前批次的结果
                json_start = response.find('[')
                json_end = response.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = response[json_start:json_end]
                    detection_results = json.loads(json_str)
                    
                    for result in detection_results:
                        if isinstance(result, dict) and 'index' in result:
                            batch_index = result['index']
                            if 0 <= batch_index < len(batch_texts):
                                global_index = batch_texts[batch_index]['global_index']
                                tags = result.get('domain_tags', [])
                                if isinstance(tags, list):
                                    clean_tags = []
                                    for tag in tags:
                                        if isinstance(tag, str) and tag.strip():
                                            clean_tag = tag.strip()
                                            clean_tags.append(clean_tag)
                                            all_tags.add(clean_tag)
                                    
                                    all_results.append({
                                        'index': global_index,
                                        'domain_tags': clean_tags
                                    })
                
            except Exception as e:
                logger.error(f"处理第 {batch_number} 批时出错: {e}")
                # 为当前批次添加空结果
                for batch_item in batch_items:
                    all_results.append({
                    'index': batch_item['global_index'],
                        'domain_tags': []
                    })
        
    except Exception as e:
        logger.error(f"批次 {batch_number} 处理异常: {e}")
        # 为当前批次添加空结果
        for batch_item in batch_items:
            all_results.append({
                'index': batch_item['global_index'],
                    'domain_tags': []
        })
        
    except Exception as e:
        logger.error(f"大批量领域标签检测失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/convert_json_to_jsonl', methods=['POST'])
def convert_json_to_jsonl():
    """将JSON文件转换为JSONL格式"""
    try:
        data = request.get_json()
        filename = data.get('filename', '')
        content = data.get('content', '')
        count = data.get('count', 0)
        
        if not filename or not content:
            return jsonify({'success': False, 'error': '参数不完整'}), 400
        
        # 确保文件名以.jsonl结尾
        if not filename.endswith('.jsonl'):
            filename += '.jsonl'
        
        # 保存到generated_datasets目录
        output_dir = os.path.join('evaluation_data', 'generated_datasets')
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = os.path.join(output_dir, filename)
        
        # 检查文件是否已存在
        if os.path.exists(output_path):
            # 生成唯一文件名
            base_name = filename.replace('.jsonl', '')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{base_name}_{timestamp}.jsonl"
            output_path = os.path.join(output_dir, filename)
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"JSON转JSONL完成: {filename}, 包含 {count} 个对象")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'count': count,
            'path': output_path
        })
        
    except Exception as e:
        logger.error(f"JSON转JSONL失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data_management/detect_leakage', methods=['POST'])
def detect_information_leakage():
    """检测推理路径中的信息泄漏"""
    try:
        data = request.get_json()
        question = data.get('question', '')
        reasoning_map = data.get('reasoning_map', '')
        entity_mapping = data.get('entity_mapping', {})
        qps_limit = data.get('qps_limit', 2.0)  # 添加QPS限制参数
        
        if not question or not reasoning_map:
            return jsonify({
                'success': False, 
                'error': '问题和推理路径不能为空'
            }), 400
        
        logger.info(f"开始信息泄漏检测 - 问题长度: {len(question)}, 推理路径长度: {len(reasoning_map)}, QPS限制: {qps_limit}")
        
        # 使用OpenRouter客户端进行检测，支持QPS限制
        from lib.llm_client import get_qa_llm_client
        llm_client = get_qa_llm_client(enable_rate_limiting=True, qps=qps_limit)
        
        # 调用同步检测方法
        try:
            detection_result = llm_client.detect_information_leakage(
                question=question,
                reasoning_map=reasoning_map,
                entity_mapping=entity_mapping
            )
                
        except Exception as e:
            logger.error(f"信息泄漏检测调用失败: {e}")
            detection_result = {'has_leakage': False, 'error': str(e)}
        
        logger.info(f"检测结果: 有泄漏={detection_result.get('has_leakage', False)}")
        
        return jsonify({
            'success': True,
            'data': detection_result
        })
        
    except Exception as e:
        logger.error(f"信息泄漏检测失败: {e}")
        return jsonify({
            'success': False, 
            'error': f'检测失败: {str(e)}'
        }), 500

@app.route('/api/data_management/detect_leakage_batch', methods=['POST'])
def detect_information_leakage_batch():
    """批量检测信息泄漏（后端并发处理，突破浏览器并发限制）"""
    
    try:
        data = request.get_json()
        items = data.get('items', [])
        auto_fix = data.get('auto_fix', True)
        qps_limit = data.get('qps_limit', 2.0)
        max_workers = min(int(qps_limit), 50)  # 限制最大并发数
        
        if not items:
            return jsonify({
                'success': False,
                'error': '没有提供检测数据'
            }), 400
        
        # 过滤有效数据项
        valid_items = []
        for i, item in enumerate(items):
            if item.get('question') and (item.get('reasoning_path') or item.get('reasoning_map')):
                valid_items.append((i, item))
        
        if not valid_items:
            return jsonify({
                'success': False,
                'error': '没有找到包含question和reasoning_path的有效数据'
            }), 400
        
        logger.info(f"开始批量信息泄漏检测 - 数据项数: {len(valid_items)}, QPS限制: {qps_limit}, 最大并发: {max_workers}")
        
        # 初始化统计
        results = {}
        stats = {
            'processed': 0,
            'leakage_count': 0,
            'fixed_count': 0,
            'error_count': 0,
            'unknown_count': 0
        }
        stats_lock = Lock()
        
        def process_single_item(index_and_item):
            """处理单个数据项"""
            original_index, item = index_and_item
            
            try:
                question = item.get('question', '')
                reasoning_map = item.get('reasoning_path') or item.get('reasoning_map', '')
                entity_mapping = item.get('entity_mapping', {})
                
                # 使用独立的客户端实例避免状态冲突
                from lib.llm_client import get_qa_llm_client
                llm_client = get_qa_llm_client(enable_rate_limiting=True, qps=qps_limit)
                
                detection_result = llm_client.detect_information_leakage(
                    question=question,
                    reasoning_map=reasoning_map,
                    entity_mapping=entity_mapping
                )
                
                has_leakage = detection_result.get('has_leakage', False)
                
                # 处理结果
                result = {
                    'original_index': original_index,
                    'processed': True,
                    'has_leakage': has_leakage,
                    'leaked_info': detection_result.get('leaked_info', []),
                    'detection_time': time.time(),
                    'fixed': False
                }
                
                # 自动修复逻辑
                if has_leakage == True and auto_fix and detection_result.get('fixed_reasoning_map'):
                    result['fixed_reasoning_map'] = detection_result.get('fixed_reasoning_map')
                    result['fixed_entity_mapping'] = detection_result.get('fixed_entity_mapping')
                    result['fixed'] = True
                
                # 更新统计
                with stats_lock:
                    stats['processed'] += 1
                    if has_leakage == True:
                        stats['leakage_count'] += 1
                        if result['fixed']:
                            stats['fixed_count'] += 1
                    elif has_leakage == 'unknown':
                        stats['unknown_count'] += 1
                
                return result
                
            except Exception as e:
                logger.error(f"处理第{original_index}项时出错: {e}")
                with stats_lock:
                    stats['error_count'] += 1
                return {
                    'original_index': original_index,
                    'processed': False,
                    'error': str(e)
                }
        
        # 使用线程池进行并发处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_item = {
                executor.submit(process_single_item, item_data): item_data 
                for item_data in valid_items
            }
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_item):
                try:
                    result = future.result()
                    results[result['original_index']] = result
                except Exception as e:
                    item_data = future_to_item[future]
                    logger.error(f"线程处理失败: {e}")
                    with stats_lock:
                        stats['error_count'] += 1
                    results[item_data[0]] = {
                        'original_index': item_data[0],
                        'processed': False,
                        'error': str(e)
                    }
        
        logger.info(f"批量检测完成 - 处理: {stats['processed']}, 泄漏: {stats['leakage_count']}, 修复: {stats['fixed_count']}, 错误: {stats['error_count']}")
        
        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'stats': stats,
                'total_items': len(valid_items),
                'max_workers': max_workers
            }
        })
        
    except Exception as e:
        logger.error(f"批量信息泄漏检测失败: {e}")
        return jsonify({
            'success': False,
            'error': f'批量检测失败: {str(e)}'
        }), 500

# 最终数据管理相关API
@app.route('/final-datasets')
def final_datasets():
    """最终数据管理页面"""
    return render_template('final_datasets.html')

@app.route('/api/final_datasets/load', methods=['GET'])
def load_final_datasets():
    """加载最终数据集"""
    try:
        logger.info("开始加载最终数据集")
        
        import hashlib
        import json
        from pathlib import Path
        
        final_datasets_dir = Path('evaluation_data/final_datasets')
        if not final_datasets_dir.exists():
            return jsonify({
                'success': False,
                'error': '最终数据集目录不存在'
            }), 404
        
        all_data = []
        file_mapping = {}  # 跟踪哪些文件被加载了
        
        def load_jsonl_file(file_path, source_name):
            """加载JSONL文件"""
            data = []
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                # 添加数据源信息
                                item['source'] = source_name
                                # 注意：不在加载时自动生成ID，让用户明确点击"生成ID"按钮来生成并保存
                                data.append(item)
                            except json.JSONDecodeError as e:
                                logger.warning(f"解析JSON失败 {file_path}:{line_num} - {e}")
                                continue
            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {e}")
            return data
        

        
        # 先扫描tagged目录，收集带标签的文件
        tagged_dir = final_datasets_dir / 'tagged'
        tagged_files = set()
        
        if tagged_dir.exists():
            for tagged_file in tagged_dir.glob('*.jsonl'):
                # 提取基础文件名（去掉_with_tags后缀）
                base_name = tagged_file.stem
                if base_name.endswith('_with_tags'):
                    original_name = base_name[:-10]  # 去掉'_with_tags'
                    tagged_files.add(original_name)
                    
                    # 加载带标签的文件
                    data = load_jsonl_file(tagged_file, base_name)
                    all_data.extend(data)
                    file_mapping[base_name] = len(data)
                    logger.info(f"加载带标签文件: {tagged_file.name} ({len(data)} 条记录)")
        
        # 再扫描主目录，加载没有标签版本的文件
        for jsonl_file in final_datasets_dir.glob('*.jsonl'):
            file_stem = jsonl_file.stem
            # 如果已经有带标签的版本，跳过原版本
            if file_stem not in tagged_files:
                data = load_jsonl_file(jsonl_file, file_stem)
                all_data.extend(data)
                file_mapping[file_stem] = len(data)
                logger.info(f"加载原始文件: {jsonl_file.name} ({len(data)} 条记录)")
        
        # 去重处理（基于question和answer的组合）
        seen_combinations = set()
        unique_data = []
        
        for item in all_data:
            question = item.get('question', '')
            answer = item.get('answer', '')
            combination = (question.strip(), answer.strip())
            
            if combination not in seen_combinations:
                seen_combinations.add(combination)
                unique_data.append(item)
        
        removed_duplicates = len(all_data) - len(unique_data)
        if removed_duplicates > 0:
            logger.info(f"去重处理: 移除了 {removed_duplicates} 条重复数据")
        
        logger.info(f"最终数据集加载完成: {len(unique_data)} 条记录，来自 {len(file_mapping)} 个文件")
        
        return jsonify({
            'success': True,
            'data': unique_data,
            'file_mapping': file_mapping,
            'stats': {
                'total_records': len(unique_data),
                'total_files': len(file_mapping),
                'duplicates_removed': removed_duplicates
            }
        })
        
    except Exception as e:
        logger.error(f"加载最终数据集失败: {e}")
        return jsonify({
            'success': False,
            'error': f'加载数据失败: {str(e)}'
        }), 500

@app.route('/api/final_datasets/update_id', methods=['POST'])
def update_data_id():
    """更新数据项的唯一ID"""
    try:
        data = request.get_json()
        old_id = data.get('old_id')
        new_id = data.get('new_id')
        source_file = data.get('source_file')
        
        if not all([old_id, new_id, source_file]):
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        # 实际更新文件中的ID
        file_path = Path('evaluation_data/final_datasets') / f"{source_file}.jsonl"
        if not file_path.exists():
            # 尝试在tagged目录中查找
            file_path = Path('evaluation_data/final_datasets/tagged') / f"{source_file}.jsonl"
        
        if not file_path.exists():
            return jsonify({
                'success': False,
                'error': f'文件不存在: {source_file}'
            }), 404
        
        # 读取文件内容
        updated_lines = []
        found = False
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                        if item.get('unique_id') == old_id:
                            item['unique_id'] = new_id
                            found = True
                            logger.info(f"更新ID: {old_id} -> {new_id} 在文件 {source_file}")
                        updated_lines.append(json.dumps(item, ensure_ascii=False))
                    except json.JSONDecodeError:
                        updated_lines.append(line)
        
        if not found:
            return jsonify({
                'success': False,
                'error': f'未找到ID为 {old_id} 的数据项'
            }), 404
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            for line in updated_lines:
                f.write(line + '\n')
        
        return jsonify({
            'success': True,
            'message': 'ID更新成功'
        })
        
    except Exception as e:
        logger.error(f"更新数据ID失败: {e}")
        return jsonify({
            'success': False,
            'error': f'更新ID失败: {str(e)}'
        }), 500

@app.route('/api/final_datasets/generate_missing_ids', methods=['POST'])
def generate_missing_ids():
    """为没有unique_id的数据项生成ID并保存到文件"""
    try:
        import hashlib
        from pathlib import Path
        
        final_datasets_dir = Path('evaluation_data/final_datasets')
        if not final_datasets_dir.exists():
            return jsonify({
                'success': False,
                'error': '最终数据集目录不存在'
            }), 404
        
        updated_files = []
        total_generated = 0
        existing_ids = set()  # 跟踪已存在的ID，确保不重复
        
        # 首先收集所有现有的ID
        def collect_existing_ids():
            nonlocal existing_ids
            for file_path in final_datasets_dir.rglob('*.jsonl'):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    item = json.loads(line)
                                    if item.get('unique_id'):
                                        existing_ids.add(item['unique_id'])
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    logger.warning(f"读取文件失败 {file_path}: {e}")
        
        collect_existing_ids()
        logger.info(f"收集到 {len(existing_ids)} 个现有ID")
        
        def process_file(file_path, source_name):
            """处理单个文件，生成缺失的ID"""
            nonlocal total_generated
            updated_lines = []
            generated_count = 0
            
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line:
                        try:
                            item = json.loads(line)
                            if 'unique_id' not in item or not item['unique_id'] or item['unique_id'].strip() == '':
                                # 生成新的唯一ID，确保不重复
                                content = str(item.get('question', '')) + str(item.get('answer', ''))
                                import uuid
                                import random
                                
                                # 重复生成直到找到唯一ID
                                attempts = 0
                                while attempts < 10:  # 最多尝试10次
                                    # 使用多个因子确保唯一性
                                    hash_input = f"{content}{source_name}{line_num}{time.time()}{random.random()}".encode('utf-8')
                                    hash_value = hashlib.md5(hash_input).hexdigest()[:8]
                                    
                                    # 使用UUID的一部分增加唯一性
                                    uuid_part = str(uuid.uuid4()).replace('-', '')[:8]
                                    
                                    # 使用完整时间戳（微秒级）
                                    timestamp = str(int(time.time() * 1000000))[-8:]
                                    
                                    new_id = f"fd_{hash_value}_{uuid_part}_{timestamp}"
                                    
                                    if new_id not in existing_ids:
                                        item['unique_id'] = new_id
                                        existing_ids.add(new_id)  # 添加到已存在ID集合
                                        break
                                    
                                    attempts += 1
                                    time.sleep(0.001)  # 短暂延迟确保时间戳不同
                                
                                if attempts >= 10:
                                    # 如果10次都重复，使用UUID兜底
                                    item['unique_id'] = f"fd_uuid_{str(uuid.uuid4()).replace('-', '')[:16]}"
                                    existing_ids.add(item['unique_id'])
                                generated_count += 1
                                logger.info(f"生成ID: {item['unique_id']} 在文件 {source_name}:{line_num}")
                            updated_lines.append(json.dumps(item, ensure_ascii=False))
                        except json.JSONDecodeError as e:
                            logger.warning(f"解析JSON失败 {file_path}:{line_num} - {e}")
                            updated_lines.append(line)
            
            if generated_count > 0:
                # 写回文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    for line in updated_lines:
                        f.write(line + '\n')
                
                updated_files.append({
                    'file': source_name,
                    'generated_count': generated_count
                })
                total_generated += generated_count
                logger.info(f"文件 {source_name} 生成了 {generated_count} 个ID")
            
            return generated_count
        
        # 使用与加载数据时相同的逻辑：优先处理tagged版本，避免重复处理
        tagged_dir = final_datasets_dir / 'tagged'
        tagged_files = set()
        
        # 先处理tagged目录下的文件
        if tagged_dir.exists():
            for tagged_file in tagged_dir.glob('*.jsonl'):
                base_name = tagged_file.stem
                if base_name.endswith('_with_tags'):
                    original_name = base_name[:-10]  # 去掉'_with_tags'
                    tagged_files.add(original_name)
                    process_file(tagged_file, base_name)
                else:
                    process_file(tagged_file, base_name)
        
        # 再处理主目录下的文件，但跳过已经有tagged版本的文件
        for jsonl_file in final_datasets_dir.glob('*.jsonl'):
            file_stem = jsonl_file.stem
            # 如果已经有带标签的版本，跳过原版本
            if file_stem not in tagged_files:
                process_file(jsonl_file, file_stem)
        
        logger.info(f"批量生成ID完成: 总共生成了 {total_generated} 个ID，涉及 {len(updated_files)} 个文件")
        
        return jsonify({
            'success': True,
            'message': f'批量生成ID完成',
            'stats': {
                'total_generated': total_generated,
                'updated_files': updated_files
            }
        })
        
    except Exception as e:
        logger.error(f"批量生成ID失败: {e}")
        return jsonify({
            'success': False,
            'error': f'批量生成ID失败: {str(e)}'
                 }), 500

@app.route('/api/final_datasets/clean_dirty_ids', methods=['POST'])
def clean_dirty_ids():
    """清理脏数据：删除普通版本文件中的unique_id字段（如果存在对应的with_tags版本）"""
    try:
        from pathlib import Path
        
        final_datasets_dir = Path('evaluation_data/final_datasets')
        if not final_datasets_dir.exists():
            return jsonify({
                'success': False,
                'error': '最终数据集目录不存在'
            }), 404
        
        cleaned_files = []
        total_cleaned = 0
        
        # 先扫描tagged目录，收集with_tags文件列表
        tagged_dir = final_datasets_dir / 'tagged'
        tagged_files = set()
        
        if tagged_dir.exists():
            for tagged_file in tagged_dir.glob('*.jsonl'):
                base_name = tagged_file.stem
                if base_name.endswith('_with_tags'):
                    original_name = base_name[:-10]  # 去掉'_with_tags'
                    tagged_files.add(original_name)
        
        logger.info(f"找到 {len(tagged_files)} 个with_tags文件: {tagged_files}")
        
        # 处理主目录下对应的普通版本文件
        for original_name in tagged_files:
            original_file = final_datasets_dir / f"{original_name}.jsonl"
            if original_file.exists():
                logger.info(f"清理文件 {original_file.name} 中的unique_id字段")
                
                updated_lines = []
                cleaned_count = 0
                
                with open(original_file, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                if 'unique_id' in item:
                                    del item['unique_id']
                                    cleaned_count += 1
                                    logger.info(f"删除ID: {original_file.name}:{line_num}")
                                updated_lines.append(json.dumps(item, ensure_ascii=False))
                            except json.JSONDecodeError as e:
                                logger.warning(f"解析JSON失败 {original_file}:{line_num} - {e}")
                                updated_lines.append(line)
                
                if cleaned_count > 0:
                    # 写回文件
                    with open(original_file, 'w', encoding='utf-8') as f:
                        for line in updated_lines:
                            f.write(line + '\n')
                    
                    cleaned_files.append({
                        'file': original_name,
                        'cleaned_count': cleaned_count
                    })
                    total_cleaned += cleaned_count
                    logger.info(f"文件 {original_name} 清理了 {cleaned_count} 个ID")
                else:
                    logger.info(f"文件 {original_name} 没有需要清理的ID")
        
        logger.info(f"脏数据清理完成: 总共清理了 {total_cleaned} 个ID，涉及 {len(cleaned_files)} 个文件")
        
        return jsonify({
            'success': True,
            'message': f'脏数据清理完成',
            'stats': {
                'total_cleaned': total_cleaned,
                'cleaned_files': cleaned_files,
                'scanned_files': len(tagged_files)
            }
        })
        
    except Exception as e:
        logger.error(f"清理脏数据失败: {e}")
        return jsonify({
            'success': False,
            'error': f'清理失败: {str(e)}'
        }), 500

@app.route('/api/final_datasets/check_duplicates', methods=['GET'])
def check_duplicate_ids():
    """检查数据集中是否有重复的唯一ID"""
    try:
        from pathlib import Path
        from collections import Counter
        
        final_datasets_dir = Path('evaluation_data/final_datasets')
        if not final_datasets_dir.exists():
            return jsonify({
                'success': False,
                'error': '最终数据集目录不存在'
            }), 404
        
        all_ids = []
        id_sources = {}  # 记录每个ID来自哪个文件
        
        # 收集所有ID
        for file_path in final_datasets_dir.rglob('*.jsonl'):
            source_name = file_path.stem
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                item = json.loads(line)
                                unique_id = item.get('unique_id')
                                if unique_id:
                                    all_ids.append(unique_id)
                                    if unique_id not in id_sources:
                                        id_sources[unique_id] = []
                                    id_sources[unique_id].append({
                                        'file': source_name,
                                        'line': line_num,
                                        'question': item.get('question', '')[:50] + '...' if len(item.get('question', '')) > 50 else item.get('question', '')
                                    })
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                logger.warning(f"读取文件失败 {file_path}: {e}")
        
        # 统计重复
        id_counts = Counter(all_ids)
        duplicates = {id_val: count for id_val, count in id_counts.items() if count > 1}
        
        duplicate_details = {}
        for dup_id in duplicates:
            duplicate_details[dup_id] = {
                'count': duplicates[dup_id],
                'sources': id_sources[dup_id]
            }
        
        logger.info(f"ID重复检查完成: 总计 {len(all_ids)} 个ID，{len(duplicates)} 个重复")
        
        return jsonify({
            'success': True,
            'stats': {
                'total_ids': len(all_ids),
                'unique_ids': len(id_counts),
                'duplicate_count': len(duplicates),
                'missing_ids': len([1 for file_path in final_datasets_dir.rglob('*.jsonl') 
                                  for line in open(file_path, 'r', encoding='utf-8') 
                                  if line.strip() and not json.loads(line.strip()).get('unique_id', '')])
            },
            'duplicates': duplicate_details
        })
        
    except Exception as e:
        logger.error(f"检查ID重复失败: {e}")
        return jsonify({
            'success': False,
            'error': f'检查失败: {str(e)}'
        }), 500

@app.route('/api/final_datasets/export', methods=['POST'])
def export_final_datasets():
    """导出筛选后的数据"""
    try:
        data = request.get_json()
        filtered_data = data.get('data', [])
        export_format = data.get('format', 'jsonl')
        
        if not filtered_data:
            return jsonify({
                'success': False,
                'error': '没有要导出的数据'
            }), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == 'jsonl':
            # 导出为JSONL格式
            output_lines = []
            for item in filtered_data:
                output_lines.append(json.dumps(item, ensure_ascii=False))
            
            output_content = '\n'.join(output_lines)
            filename = f'final_datasets_export_{timestamp}.jsonl'
            
        elif export_format == 'json':
            # 导出为JSON格式
            output_content = json.dumps(filtered_data, ensure_ascii=False, indent=2)
            filename = f'final_datasets_export_{timestamp}.json'
            
        else:
            return jsonify({
                'success': False,
                'error': '不支持的导出格式'
            }), 400
        
        # 保存到临时文件
        import tempfile
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename)
        
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(output_content)
        
        logger.info(f"导出数据成功: {filename} ({len(filtered_data)} 条记录)")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'download_url': f'/api/download/{filename}',
            'record_count': len(filtered_data)
        })
        
    except Exception as e:
        logger.error(f"导出数据失败: {e}")
        return jsonify({
            'success': False,
            'error': f'导出失败: {str(e)}'
        }), 500

@app.route('/api/download/<filename>')
def download_exported_file(filename):
    """下载导出的文件"""
    try:
        import tempfile
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        logger.error(f"下载文件失败: {e}")
        return jsonify({
            'success': False,
            'error': f'下载失败: {str(e)}'
        }), 500

if __name__ == '__main__':
    print("🚀 启动知识图谱构建Web应用...")
    print("🌐 访问地址: http://localhost:5000")
    print("📊 在浏览器中查看实时构建过程")
    print("📝 日志和Trace功能已启用")
    print("🔍 日志文件位置: ~/Downloads/logs/app_YYYYMMDD.log") 
    print("📋 Trace功能: 每个请求都有唯一的trace ID用于追踪")
    print("="*50)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, threaded=True)