/**
 * 数据评测页面JavaScript
 */

class DataEvaluationManager {
  constructor() {
    // Socket.IO连接
    this.socket = io();
    
    // 全局变量
    this.currentDataset = null;
    this.isEvaluating = false;
    this.evaluationResultsData = [];
    this.comparisonChart = null;
    this.taskProgress = {
      total: 0,
      completed: 0,
      tasks: []
    };

    // DOM元素
    this.standardDatasets = document.getElementById('standard-datasets');
    this.generatedDatasets = document.getElementById('generated-datasets');
    this.overviewContent = document.getElementById('overview-content');
    this.evaluationContent = document.getElementById('evaluation-content');
    this.panelTitle = document.getElementById('panel-title');
    this.startEvaluationBtn = document.getElementById('start-evaluation-btn');
    this.stopEvaluationBtn = document.getElementById('stop-evaluation-btn');
    this.evaluationResults = document.getElementById('evaluation-results');
    this.uploadArea = document.getElementById('upload-area');
    this.fileInput = document.getElementById('file-input');

    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadDatasets();
    this.initializeUpload();
    this.updateComparisonChart();
  }

  setupEventListeners() {
    // 开始评测按钮
    this.startEvaluationBtn?.addEventListener('click', () => this.startEvaluation());
    
    // 停止评测按钮  
    this.stopEvaluationBtn?.addEventListener('click', () => this.stopEvaluation());

    // Socket.IO事件
    this.socket.on('evaluation_progress', (data) => this.handleEvaluationProgress(data));
    this.socket.on('evaluation_result', (data) => this.handleEvaluationResult(data));
    this.socket.on('evaluation_complete', (data) => this.handleEvaluationComplete(data));
    this.socket.on('evaluation_error', (data) => this.handleEvaluationError(data));
  }

  // 加载数据集列表
  loadDatasets() {
    console.log('开始加载数据集...');
    fetch('/api/evaluation_data/list')
      .then(response => {
        console.log('API响应状态:', response.status);
        return response.json();
      })
      .then(data => {
        console.log('获取到的数据集:', data);
        this.updateDatasetList('standard', data.standard || []);
        this.updateDatasetList('generated', data.generated || []);
      })
      .catch(error => {
        console.error('加载数据集失败:', error);
      });
  }

  // 更新数据集列表
  updateDatasetList(type, datasets) {
    console.log(`更新${type}数据集列表:`, datasets);
    const container = type === 'standard' ? this.standardDatasets : this.generatedDatasets;
    console.log(`容器元素:`, container);
    
    if (!container) return;
    
    container.innerHTML = '';

    if (datasets.length === 0) {
      console.log(`${type}数据集为空`);
      container.innerHTML = '<li style="color: #718096; font-size: 12px; padding: 8px;">暂无数据</li>';
      return;
    }

    datasets.forEach(dataset => {
      const item = document.createElement('li');
      item.className = 'dataset-item';
      item.onclick = () => this.selectDataset(dataset);
      
      item.innerHTML = `
        <div class="dataset-name">${dataset.name}</div>
        <div class="dataset-meta">
          ${dataset.count || 0} 条记录 | 
          ${new Date(dataset.created_at).toLocaleDateString()}
        </div>
      `;
      
      container.appendChild(item);
    });
  }

  // 选择数据集
  selectDataset(dataset) {
    this.currentDataset = dataset;
    
    // 更新UI
    document.querySelectorAll('.dataset-item').forEach(item => {
      item.classList.remove('active');
    });
    event.currentTarget.classList.add('active');
    
    // 显示评测界面
    this.showEvaluationPanel(dataset);
  }

  // 显示评测面板
  showEvaluationPanel(dataset) {
    if (this.overviewContent) this.overviewContent.style.display = 'none';
    if (this.evaluationContent) this.evaluationContent.style.display = 'block';
    if (this.panelTitle) this.panelTitle.textContent = `${dataset.name} - 评测`;
    
    // 显示历史评测记录
    this.showEvaluationHistory(dataset);
    
    // 加载数据集详情
    this.loadDatasetDetails(dataset.id);
  }

  // 加载数据集详情
  loadDatasetDetails(datasetId) {
    fetch(`/api/evaluation_data/details/${datasetId}`)
      .then(response => response.json())
      .then(data => {
        if (data.evaluation_history && data.evaluation_history.length > 0) {
          this.showEvaluationHistory(data.evaluation_history);
        }
      })
      .catch(error => {
        console.error('加载数据集详情失败:', error);
      });
  }

  // 开始评测
  startEvaluation() {
    if (!this.currentDataset || this.isEvaluating) return;
    
    const config = {
      dataset_id: this.currentDataset.id,
      evaluation_mode: document.getElementById('evaluation-mode')?.value || 'R1-0528',
      batch_size: parseInt(document.getElementById('batch-size')?.value) || 10
    };
    
    this.isEvaluating = true;
    this.resetProgress();
    this.updateEvaluationUI();
    
    fetch('/api/evaluation/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    })
    .then(response => response.json())
    .then(data => {
      if (data.error) {
        throw new Error(data.error);
      }
      console.log('评测已开始:', data.evaluation_id);
      
      // 初始化进度
      this.taskProgress.total = data.total_tasks || 0;
      this.updateProgressInfo('评测开始', 0);
    })
    .catch(error => {
      console.error('开始评测失败:', error);
      alert('开始评测失败: ' + error.message);
      this.isEvaluating = false;
      this.updateEvaluationUI();
    });
  }

  // 停止评测
  stopEvaluation() {
    fetch('/api/evaluation/stop', {
      method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
      console.log('评测已停止');
      this.isEvaluating = false;
      this.updateEvaluationUI();
    })
    .catch(error => {
      console.error('停止评测失败:', error);
    });
  }

  // 更新评测UI状态
  updateEvaluationUI() {
    if (this.startEvaluationBtn) {
      this.startEvaluationBtn.disabled = this.isEvaluating;
    }
    if (this.stopEvaluationBtn) {
      this.stopEvaluationBtn.disabled = !this.isEvaluating;
    }
    
    if (this.isEvaluating) {
      if (this.startEvaluationBtn) {
        this.startEvaluationBtn.innerHTML = '<span>⏳ 评测中...</span>';
      }
      const progressEl = document.getElementById('evaluation-progress');
      if (progressEl) progressEl.style.display = 'block';
    } else {
      if (this.startEvaluationBtn) {
        this.startEvaluationBtn.innerHTML = '<span>🚀 开始评测</span>';
      }
      const progressEl = document.getElementById('evaluation-progress');
      if (progressEl) progressEl.style.display = 'none';
    }
  }

  // 更新进度信息
  updateProgressInfo(step, progress) {
    const progressElement = document.getElementById('progress-fill');
    const overallProgressElement = document.getElementById('overall-progress');
    const completedTasksElement = document.getElementById('completed-tasks');
    const totalTasksElement = document.getElementById('total-tasks');
    
    // 只在progress不为null时更新进度条
    if (progress !== null && progress !== undefined) {
      if (progressElement) progressElement.style.width = `${progress}%`;
      if (overallProgressElement) overallProgressElement.textContent = `${progress.toFixed(1)}%`;
    }
    
    // 更新任务计数
    if (completedTasksElement) completedTasksElement.textContent = this.taskProgress.completed;
    if (totalTasksElement) totalTasksElement.textContent = this.taskProgress.total;
  }

  // 添加任务到任务列表
  addTaskToList(taskId, message, status = 'running') {
    const taskList = document.getElementById('task-list');
    if (!taskList) return;
    
    const taskItem = document.createElement('div');
    taskItem.className = `task-item ${status}`;
    taskItem.id = `task-${taskId}`;
    
    taskItem.innerHTML = `
      <div class="task-status-icon ${status}"></div>
      <div class="task-message">${message}</div>
    `;
    
    taskList.appendChild(taskItem);
    
    // 滚动到底部
    taskList.scrollTop = taskList.scrollHeight;
  }

  // 更新任务状态
  updateTaskStatus(taskId, message, status) {
    const taskItem = document.getElementById(`task-${taskId}`);
    if (taskItem) {
      taskItem.className = `task-item ${status}`;
      const iconEl = taskItem.querySelector('.task-status-icon');
      if (iconEl) iconEl.className = `task-status-icon ${status}`;
      const messageEl = taskItem.querySelector('.task-message');
      if (messageEl) messageEl.textContent = message;
    }
  }

  // 重置进度
  resetProgress() {
    this.taskProgress = {
      total: 0,
      completed: 0,
      tasks: []
    };
    
    const taskList = document.getElementById('task-list');
    if (taskList) taskList.innerHTML = '';
    this.updateProgressInfo('', 0);
  }

  // 显示评测结果
  showEvaluationResults(results) {
    console.log('showEvaluationResults 接收到的数据:', results);
    console.log('数据类型:', typeof results);
    console.log('是否为数组:', Array.isArray(results));
    
    if (!results || !Array.isArray(results)) {
      console.error('传入的结果不是有效的数组:', results);
      return;
    }
    
    if (this.evaluationResults) {
      this.evaluationResults.style.display = 'block';
    }
    
    // 更新汇总数据
    const totalQuestions = results.length;
    const correctCount = results.filter(r => r.correct).length;
    
    console.log('总题数:', totalQuestions);
    console.log('正确数量:', correctCount);
    
    // 计算平均得分 (正确答案按1分计算，错误答案按0分计算)
    const avgScore = totalQuestions > 0 ? (correctCount / totalQuestions).toFixed(2) : 0;
    
    console.log('平均得分:', avgScore);
    
    // 检查DOM元素是否存在
    const totalQuestionsEl = document.getElementById('total-questions');
    const correctCountEl = document.getElementById('correct-count');
    const avgScoreEl = document.getElementById('avg-score');
    
    console.log('DOM元素检查:', {
      totalQuestionsEl: !!totalQuestionsEl,
      correctCountEl: !!correctCountEl,
      avgScoreEl: !!avgScoreEl
    });
    
    if (totalQuestionsEl) totalQuestionsEl.textContent = totalQuestions;
    if (correctCountEl) correctCountEl.textContent = correctCount;
    if (avgScoreEl) avgScoreEl.textContent = avgScore;
    
    // 更新详细结果表格
    this.updateResultsTable(results);
  }

  // 更新结果表格
  updateResultsTable(results) {
    console.log('updateResultsTable 接收到的数据:', results);
    
    const container = document.getElementById('results-table-content');
    if (!container) {
      console.error('找不到 results-table-content 元素');
      return;
    }
    
    container.innerHTML = '';
    
    if (!results || !Array.isArray(results)) {
      console.error('传入的结果不是有效的数组:', results);
      return;
    }
    
    results.forEach((result, index) => {
      const item = document.createElement('div');
      item.className = 'result-item';
      
      const statusClass = result.correct ? 'status-correct' : 'status-incorrect';
      const statusText = result.correct ? '✓ 正确' : '✗ 错误';
      const score = result.correct ? 1 : 0; // 正确为1分，错误为0分
      
      item.innerHTML = `
        <div class="result-question">
          <strong>Q${index + 1}:</strong> ${(result.question || '').substring(0, 100)}...
        </div>
        <div class="result-status">
          <span class="status-badge ${statusClass}">${statusText}</span>
        </div>
        <div class="result-score">${score.toFixed(2)}</div>
      `;
      
      container.appendChild(item);
    });
    
    console.log('表格更新完成，共', results.length, '条记录');
  }

  // 初始化文件上传
  initializeUpload() {
    if (!this.uploadArea || !this.fileInput) return;

    // 拖拽上传
    this.uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      this.uploadArea.classList.add('dragover');
    });
    
    this.uploadArea.addEventListener('dragleave', (e) => {
      e.preventDefault();
      this.uploadArea.classList.remove('dragover');
    });
    
    this.uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      this.uploadArea.classList.remove('dragover');
      this.handleFiles(e.dataTransfer.files);
    });
    
    // 点击上传
    this.uploadArea.addEventListener('click', () => {
      this.fileInput.click();
    });
    
    this.fileInput.addEventListener('change', () => {
      this.handleFiles(this.fileInput.files);
    });
  }

  // 处理上传文件
  handleFiles(files) {
    Array.from(files).forEach(file => {
      if (file.type === 'application/json' || file.name.endsWith('.jsonl')) {
        this.uploadDataset(file);
      } else {
        alert('只支持JSON和JSONL格式的文件');
      }
    });
  }

  // 上传数据集
  uploadDataset(file) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('type', 'import');
    
    fetch('/api/evaluation_data/upload', {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        alert('上传成功！');
        this.loadDatasets(); // 刷新数据集列表
      } else {
        throw new Error(data.error || '上传失败');
      }
    })
    .catch(error => {
      console.error('上传失败:', error);
      alert('上传失败: ' + error.message);
    });
  }

  // Socket.IO事件处理
  handleEvaluationProgress(data) {
    console.log('评测进度:', data);
    
    // 更新进度信息
    const progress = data.progress; // 不要将null转换为0
    this.updateProgressInfo(data.step, progress);
    
    // 如果有任务信息，添加到任务列表
    if (data.task_id && data.message) {
      const taskId = data.task_id;
      const message = data.message;
      const status = data.status || 'running';
      
      // 检查任务是否已存在
      const existingTask = document.getElementById(`task-${taskId}`);
      if (existingTask) {
        this.updateTaskStatus(taskId, message, status);
      } else {
        this.addTaskToList(taskId, message, status);
      }
      
      // 更新完成计数
      if (status === 'completed') {
        this.taskProgress.completed++;
        // 只在有具体进度值时更新进度条
        if (progress !== null && progress !== undefined) {
          this.updateProgressInfo(data.step, progress);
        }
      }
    }
  }

  handleEvaluationResult(data) {
    console.log('收到评测结果:', data);
    this.evaluationResultsData.push(data);
    
    // 实时更新结果显示
    if (this.evaluationResultsData.length > 0) {
      this.showEvaluationResults(this.evaluationResultsData);
    }
  }

  handleEvaluationComplete(data) {
    console.log('评测完成:', data);
    this.isEvaluating = false;
    this.updateEvaluationUI();
    
    if (data.results) {
      // 修复数据结构处理：data.results是完整的评测结果对象，data.results.results是结果数组
      this.evaluationResultsData = data.results.results || [];
      console.log('评测结果数据:', this.evaluationResultsData);
      
      if (this.evaluationResultsData.length > 0) {
        this.showEvaluationResults(this.evaluationResultsData);
      } else {
        console.error('评测结果数据为空');
      }
      
      // 刷新对比图表
      this.updateComparisonChart();
      
      // 刷新历史记录
      if (this.currentDataset) {
        this.showEvaluationHistory(this.currentDataset);
      }
    }
  }

  handleEvaluationError(data) {
    console.error('评测错误:', data);
    alert('评测出错: ' + data.message);
    this.isEvaluating = false;
    this.updateEvaluationUI();
  }

  // 更新得分对比图表
  updateComparisonChart() {
    const modeSelect = document.getElementById('comparison-mode');
    const mode = modeSelect ? modeSelect.value : 'R1-0528';
    console.log('更新对比图表，评测模式:', mode);
    
    // 从API获取实际的评测结果
    fetch(`/api/evaluation_data/results?mode=${mode}`)
      .then(response => response.json())
      .then(data => {
        const chartContainer = document.getElementById('comparison-chart');
        if (!chartContainer) return;
        
        if (!data.results || data.results.length === 0) {
          chartContainer.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #718096;">
              <div style="text-align: center;">
                <div style="font-size: 3rem; margin-bottom: 16px;">📊</div>
                <p>暂无评测数据，请先运行评测</p>
              </div>
            </div>
          `;
          return;
        }

        // 初始化或重新初始化图表
        if (this.comparisonChart) {
          this.comparisonChart.dispose();
        }
        this.comparisonChart = echarts.init(chartContainer);

        // 准备数据并按成功率排序
        const sortedData = data.results
          .map(item => ({
            name: item.name,
            accuracy: item.accuracy || 0,
            count: item.count || 0
          }))
          .sort((a, b) => a.accuracy - b.accuracy); // 按成功率从低到高排序

        const datasets = sortedData.map(item => item.name);
        const scores = sortedData.map(item => item.accuracy);
        const counts = sortedData.map(item => item.count);

        // 配置图表
        const option = {
          title: {
            text: '数据集评测得分对比',
            left: 'center',
            textStyle: {
              fontSize: 16,
              fontWeight: 'bold'
            }
          },
          tooltip: {
            trigger: 'item',
            formatter: function(params) {
              const dataIndex = params.dataIndex;
              const name = params.name;
              const accuracy = scores[dataIndex];
              const count = counts[dataIndex];
              return `${name}<br/>成功率: ${accuracy.toFixed(1)}%<br/>数据条数: ${count}`;
            }
          },
          xAxis: {
            type: 'category',
            data: datasets,
            axisLabel: {
              rotate: 45,
              interval: 0
            }
          },
          yAxis: {
            type: 'value',
            name: '成功率 (%)',
            min: 0,
            max: 100,
            axisLabel: {
              formatter: '{value}%'
            }
          },
          series: [
            {
              name: '成功率',
              type: 'bar',
              data: scores,
              barWidth: '40%',  // 控制柱子宽度
              itemStyle: {
                color: '#4facfe'  // 统一使用蓝色
              },
              label: {
                show: true,
                position: 'top',
                formatter: '{c}%'
              }
            }
          ]
        };

        this.comparisonChart.setOption(option);

        // 窗口大小改变时重新调整图表
        const resizeHandler = () => {
          if (this.comparisonChart) {
            this.comparisonChart.resize();
          }
        };
        window.addEventListener('resize', resizeHandler);
      })
      .catch(error => {
        console.error('加载评测结果失败:', error);
        const chartContainer = document.getElementById('comparison-chart');
        if (chartContainer) {
          chartContainer.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #ef4444;">
              <div style="text-align: center;">
                <div style="font-size: 3rem; margin-bottom: 16px;">❌</div>
                <p>加载评测结果失败</p>
              </div>
            </div>
          `;
        }
      });
  }

  // 显示历史评测记录
  showEvaluationHistory(dataset) {
    const container = document.getElementById('history-container');
    if (!container) return;
    
    // 从API获取实际的历史评测记录
    fetch(`/api/evaluation_data/history/${dataset.id}`)
      .then(response => response.json())
      .then(data => {
        if (!data.history || data.history.length === 0) {
          container.innerHTML = `
            <div class="no-history">
              <div style="text-align: center; color: #718096; padding: 40px;">
                <div style="font-size: 3rem; margin-bottom: 16px;">📋</div>
                <p>暂无评测记录</p>
                <p style="font-size: 14px;">运行评测后，结果将在这里显示</p>
              </div>
            </div>
          `;
          return;
        }

        container.innerHTML = data.history.map(item => `
          <div class="history-item">
            <div class="history-info">
              <div class="history-title">${item.mode} 评测</div>
              <div class="history-meta">
                ${item.completed_at} • ${item.total_questions} 题
              </div>
            </div>
            <div class="history-scores">
              <div class="score-item">
                <div class="score-value">${item.accuracy}%</div>
                <div class="score-label">准确率</div>
              </div>
              <div class="score-item">
                <div class="score-value">${item.correct_count}/${item.total_questions}</div>
                <div class="score-label">正确数</div>
              </div>
            </div>
          </div>
        `).join('');
      })
      .catch(error => {
        console.error('加载历史记录失败:', error);
        container.innerHTML = `
          <div style="text-align: center; color: #ef4444; padding: 20px;">
            加载历史记录失败
          </div>
        `;
      });
  }
}

// 全局函数 - 兼容现有的HTML中的onclick调用
let dataEvaluationManager;

function viewHistory() {
  if (dataEvaluationManager && dataEvaluationManager.currentDataset) {
    console.log('查看评测历史');
    // 可以在这里添加打开历史详情模态框的逻辑
  }
}

function exportResults() {
  if (dataEvaluationManager && dataEvaluationManager.evaluationResultsData.length > 0) {
    const blob = new Blob([JSON.stringify(dataEvaluationManager.evaluationResultsData, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evaluation_results_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

function refreshDatasets() {
  if (dataEvaluationManager) {
    dataEvaluationManager.loadDatasets();
  }
}

function updateComparisonChart() {
  if (dataEvaluationManager) {
    dataEvaluationManager.updateComparisonChart();
  }
}

// 页面加载时初始化
document.addEventListener('DOMContentLoaded', function() {
  dataEvaluationManager = new DataEvaluationManager();
}); 