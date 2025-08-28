// 对比评测页面JavaScript逻辑

class ComparisonEvaluation {
  constructor() {
    this.socket = null;
    this.currentEvaluation = null;
    this.dataFiles = {
      datasetA: null,
      datasetB: null
    };
    this.config = {
      sampleCount: 10,
      evaluator: 'gemini',
      criteria: '中文互联网QA质量',
      workers: 2
    };
    this.comparisonResults = [];
    this.dropdownEventsBound = false;
    this.init();
  }

  init() {
    this.setupSocketConnection();
    this.bindEvents();
    this.loadDataFiles();
    this.loadHistory();
  }

  setupSocketConnection() {
    this.socket = io();
    
    this.socket.on('connect', () => {
      console.log('Socket连接成功');
    });

    this.socket.on('comparison_progress', (data) => {
      this.updateProgress(data);
    });

    this.socket.on('comparison_result', (data) => {
      this.handleComparisonResult(data);
    });

    this.socket.on('comparison_complete', (data) => {
      this.handleComparisonComplete(data);
    });

    this.socket.on('comparison_error', (data) => {
      this.showError('评测出错: ' + data.message);
      this.hideLoading();
      this.setRunningState(false);
    });
  }

  bindEvents() {
    // 参数设置事件
    document.getElementById('sampleCount').addEventListener('input', (e) => {
      this.config.sampleCount = parseInt(e.target.value);
      this.validateSampleCount();
    });

    document.getElementById('evaluator').addEventListener('change', (e) => {
      this.config.evaluator = e.target.value;
    });

    document.getElementById('criteria').addEventListener('change', (e) => {
      this.config.criteria = e.target.value;
    });

    document.getElementById('workers').addEventListener('input', (e) => {
      this.config.workers = parseInt(e.target.value);
    });

    // 按钮事件
    document.getElementById('startBtn').addEventListener('click', () => {
      this.startComparison();
    });

    document.getElementById('stopBtn').addEventListener('click', () => {
      this.stopComparison();
    });

    // 历史记录点击事件
    document.addEventListener('click', (e) => {
      if (e.target.closest('.history-item')) {
        const historyId = e.target.closest('.history-item').dataset.historyId;
        this.loadHistoryDetail(historyId);
      }
    });
  }

  async loadDataFiles() {
    try {
      const response = await fetch('/api/evaluation_data/list');
      const data = await response.json();
      
      this.renderFileOptions(data.standard || [], data.generated || []);
    } catch (error) {
      console.error('加载数据文件失败:', error);
      this.showError('加载数据文件失败');
      
      // 在错误情况下显示错误信息
      ['datasetA', 'datasetB'].forEach(datasetType => {
        const menuElement = document.getElementById(`${datasetType}-menu`);
        menuElement.innerHTML = `
          <div class="dropdown-loading">
            <span>❌ 加载数据文件失败</span>
          </div>
        `;
      });
    }
  }

  renderFileOptions(standardFiles, generatedFiles) {
    // 渲染数据集A的选项
    this.renderDropdownOptions('datasetA', standardFiles, generatedFiles);
    // 渲染数据集B的选项
    this.renderDropdownOptions('datasetB', standardFiles, generatedFiles);
    
    // 绑定下拉菜单事件（只绑定一次）
    if (!this.dropdownEventsBound) {
      this.bindDropdownEvents();
      this.dropdownEventsBound = true;
    }
  }

  renderDropdownOptions(datasetType, standardFiles, generatedFiles) {
    const menuElement = document.getElementById(`${datasetType}-menu`);
    
    let menuHTML = '';
    
    // 标准数据集分类
    if (standardFiles.length > 0) {
      menuHTML += `
        <div class="dropdown-section">
          <div class="dropdown-section-title">📚 标准数据集</div>
          ${standardFiles.map(file => `
            <div class="dropdown-item" data-file="${file.id}" data-type="standard" data-dataset="${datasetType}">
              <div class="dropdown-item-name">${file.name}</div>
              <div class="dropdown-item-meta">
                <span>${file.count} 条数据</span>
                <span>创建于 ${file.created_at}</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }
    
    // 生成数据集分类
    if (generatedFiles.length > 0) {
      menuHTML += `
        <div class="dropdown-section">
          <div class="dropdown-section-title">🤖 生成数据集</div>
          ${generatedFiles.map(file => `
            <div class="dropdown-item" data-file="${file.id}" data-type="generated" data-dataset="${datasetType}">
              <div class="dropdown-item-name">${file.name}</div>
              <div class="dropdown-item-meta">
                <span>${file.count} 条数据</span>
                <span>创建于 ${file.created_at}</span>
              </div>
            </div>
          `).join('')}
        </div>
      `;
    }
    
    if (!menuHTML) {
      menuHTML = `
        <div class="dropdown-loading">
          <span>暂无可用的数据文件</span>
        </div>
      `;
    }
    
    menuElement.innerHTML = menuHTML;
  }

  bindDropdownEvents() {
    // 绑定下拉按钮点击事件
    ['datasetA', 'datasetB'].forEach(datasetType => {
      const btn = document.getElementById(`${datasetType}-btn`);
      const menu = document.getElementById(`${datasetType}-menu`);
      
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        
        // 关闭其他下拉菜单
        const otherDataset = datasetType === 'datasetA' ? 'datasetB' : 'datasetA';
        this.closeDropdown(otherDataset);
        
        // 切换当前下拉菜单
        this.toggleDropdown(datasetType);
      });
      
      // 绑定选项点击事件
      menu.addEventListener('click', (e) => {
        const item = e.target.closest('.dropdown-item');
        if (item) {
          const fileId = item.dataset.file;
          const fileType = item.dataset.type;
          const fileName = item.querySelector('.dropdown-item-name').textContent;
          const fileCount = item.querySelector('.dropdown-item-meta span').textContent;
          
          this.selectDataFile(datasetType, fileId, fileType, fileName, fileCount);
          this.closeDropdown(datasetType);
        }
      });
    });
    
    // 点击外部关闭下拉菜单
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dataset-dropdown')) {
        this.closeAllDropdowns();
      }
    });
  }

  toggleDropdown(datasetType) {
    const btn = document.getElementById(`${datasetType}-btn`);
    const menu = document.getElementById(`${datasetType}-menu`);
    
    const isActive = btn.classList.contains('active');
    
    if (isActive) {
      this.closeDropdown(datasetType);
    } else {
      this.openDropdown(datasetType);
    }
  }

  openDropdown(datasetType) {
    const btn = document.getElementById(`${datasetType}-btn`);
    const menu = document.getElementById(`${datasetType}-menu`);
    
    btn.classList.add('active');
    menu.classList.add('show');
  }

  closeDropdown(datasetType) {
    const btn = document.getElementById(`${datasetType}-btn`);
    const menu = document.getElementById(`${datasetType}-menu`);
    
    btn.classList.remove('active');
    menu.classList.remove('show');
  }

  closeAllDropdowns() {
    ['datasetA', 'datasetB'].forEach(datasetType => {
      this.closeDropdown(datasetType);
    });
  }

  selectDataFile(datasetType, fileId, fileType, fileName, fileCount) {
    // 保存选择的文件信息
    this.dataFiles[datasetType] = {
      id: fileId,
      type: fileType,
      name: fileName,
      count: parseInt(fileCount)
    };

    // 更新下拉按钮显示
    this.updateDropdownButton(datasetType, fileName);
    
    // 显示选中的文件信息
    this.showSelectedFile(datasetType);
    
    // 验证采样数量
    this.validateSampleCount();
  }

  updateDropdownButton(datasetType, fileName) {
    const btn = document.getElementById(`${datasetType}-btn`);
    const selectedText = btn.querySelector('.selected-text');
    
    selectedText.textContent = fileName;
    selectedText.classList.add('has-selection');
  }

  showSelectedFile(datasetType) {
    const infoElement = document.getElementById(`${datasetType}-info`);
    const file = this.dataFiles[datasetType];
    
    infoElement.style.display = 'flex';
    infoElement.querySelector('.file-name').textContent = file.name;
    infoElement.querySelector('.file-count').textContent = `${file.count} 条数据`;
  }

  validateSampleCount() {
    const sampleInput = document.getElementById('sampleCount');
    const startBtn = document.getElementById('startBtn');
    
    if (!this.dataFiles.datasetA || !this.dataFiles.datasetB) {
      startBtn.disabled = true;
      return;
    }

    const maxSample = Math.min(this.dataFiles.datasetA.count, this.dataFiles.datasetB.count);
    const currentSample = parseInt(sampleInput.value);

    if (currentSample > maxSample) {
      sampleInput.value = maxSample;
      this.config.sampleCount = maxSample;
      this.showWarning(`采样数量已调整为 ${maxSample}，不能超过任一数据集的数据量`);
    }

    sampleInput.setAttribute('max', maxSample);
    startBtn.disabled = currentSample <= 0 || currentSample > maxSample;
  }

  async startComparison() {
    if (!this.validateConfiguration()) {
      return;
    }

    this.setRunningState(true);
    this.showLoading('正在启动对比评测...');
    this.clearResults();

    const config = {
      datasetA: this.dataFiles.datasetA,
      datasetB: this.dataFiles.datasetB,
      sampleCount: this.config.sampleCount,
      evaluator: this.config.evaluator,
      criteria: this.config.criteria,
      workers: this.config.workers
    };

    try {
      const response = await fetch('/api/comparison/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
      });

      const result = await response.json();
      
      if (response.ok) {
        this.currentEvaluation = result.comparison_id;
        this.showInfo('对比评测已开始，ID: ' + result.comparison_id);
        this.hideLoading();
      } else {
        throw new Error(result.error || '启动失败');
      }
    } catch (error) {
      this.showError('启动对比评测失败: ' + error.message);
      this.hideLoading();
      this.setRunningState(false);
    }
  }

  async stopComparison() {
    if (!this.currentEvaluation) {
      return;
    }

    try {
      const response = await fetch('/api/comparison/stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ comparison_id: this.currentEvaluation })
      });

      if (response.ok) {
        this.showInfo('对比评测已停止');
        this.setRunningState(false);
      }
    } catch (error) {
      this.showError('停止对比评测失败: ' + error.message);
    }
  }

  validateConfiguration() {
    if (!this.dataFiles.datasetA || !this.dataFiles.datasetB) {
      this.showError('请选择两个数据文件');
      return false;
    }

    if (this.dataFiles.datasetA.id === this.dataFiles.datasetB.id) {
      this.showError('不能选择相同的数据文件');
      return false;
    }

    if (this.config.sampleCount <= 0) {
      this.showError('采样数量必须大于0');
      return false;
    }

    const maxSample = Math.min(this.dataFiles.datasetA.count, this.dataFiles.datasetB.count);
    if (this.config.sampleCount > maxSample) {
      this.showError(`采样数量不能超过 ${maxSample}`);
      return false;
    }

    return true;
  }

  updateProgress(data) {
    const progressBar = document.querySelector('.progress-bar');
    const progressText = document.querySelector('.progress-text');
    const progressPercentage = document.querySelector('.progress-percentage');

    if (progressBar && data.percentage !== undefined) {
      progressBar.style.width = `${data.percentage}%`;
    }

    if (progressText && data.message) {
      progressText.textContent = data.message;
    }

    if (progressPercentage && data.percentage !== undefined) {
      progressPercentage.textContent = `${data.percentage.toFixed(1)}%`;
    }

    // 更新状态详情
    if (data.details) {
      this.updateStatusDetails(data.details);
    }
  }

  updateStatusDetails(details) {
    const statusDetails = document.querySelector('.status-details');
    if (!statusDetails) return;

    statusDetails.innerHTML = `
      <div class="status-item">
        <span class="status-label">已完成对比</span>
        <span class="status-value">${details.completed || 0} / ${details.total || 0}</span>
      </div>
      <div class="status-item">
        <span class="status-label">数据集A胜利</span>
        <span class="status-value">${details.datasetA_wins || 0}</span>
      </div>
      <div class="status-item">
        <span class="status-label">数据集B胜利</span>
        <span class="status-value">${details.datasetB_wins || 0}</span>
      </div>
      <div class="status-item">
        <span class="status-label">并列</span>
        <span class="status-value">${details.ties || 0}</span>
      </div>
    `;
  }

  handleComparisonResult(data) {
    // 处理单次对比结果
    this.comparisonResults.push(data);
    this.renderLatestResult(data);
  }

  handleComparisonComplete(data) {
    this.showSuccess('对比评测完成');
    this.hideLoading();
    this.setRunningState(false);
    
    // 渲染完整结果
    this.renderCompleteResults(data.results || data);
    
    // 延迟更新历史记录，确保服务器端已保存
    setTimeout(() => {
      this.loadHistory();
    }, 500);
  }

  renderLatestResult(result) {
    // 实时更新最新的对比结果到界面
    const resultsContainer = document.querySelector('.comparison-results');
    if (!resultsContainer) return;

    // 这里可以添加实时结果的显示逻辑
    // 例如显示最新完成的对比项
  }

  renderCompleteResults(data) {
    const resultsContainer = document.querySelector('.comparison-results');
    if (!resultsContainer) return;

    // 计算获胜情况 - 修正winner字段判断
    const datasetA_wins = data.results.filter(r => r.winner === 'A').length;
    const datasetB_wins = data.results.filter(r => r.winner === 'B').length;
    const ties = data.results.filter(r => r.winner === 'T').length;
    
    const winner = datasetA_wins > datasetB_wins ? 'A' : 
                   datasetB_wins > datasetA_wins ? 'B' : 'T';

    resultsContainer.innerHTML = `
      <div class="result-summary">
        <div class="winner-announcement">
          <h2 class="winner-title">🏆 对比评测结果</h2>
          <div class="winner-dataset">
            ${winner === 'T' ? '平局' : 
              winner === 'A' ? data.datasetA_name : data.datasetB_name} 获胜
          </div>
        </div>
        
        <div class="score-comparison">
          <div class="score-card ${winner === 'A' ? 'winner' : ''}">
            <div class="dataset-name">${data.datasetA_name}</div>
            <div class="win-count">${datasetA_wins}</div>
            <div class="win-ratio">${(datasetA_wins / data.results.length * 100).toFixed(1)}% 胜率</div>
          </div>
          <div class="score-card ${winner === 'B' ? 'winner' : ''}">
            <div class="dataset-name">${data.datasetB_name}</div>
            <div class="win-count">${datasetB_wins}</div>
            <div class="win-ratio">${(datasetB_wins / data.results.length * 100).toFixed(1)}% 胜率</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span>📋</span>
          详细对比记录
        </div>
        <div class="card-body" style="padding: 0;">
          <div class="comparison-list">
            ${data.results.map((result, index) => this.renderComparisonItem(result, index + 1, data)).join('')}
          </div>
        </div>
      </div>
    `;
  }

  renderComparisonItem(result, index, data) {
    const winnerClass = result.winner === 'A' ? 'dataset-a' : 
                       result.winner === 'B' ? 'dataset-b' : 'tie';
    
    const winnerText = result.winner === 'A' ? data.datasetA_name : 
                      result.winner === 'B' ? data.datasetB_name : '平局';

    return `
      <div class="comparison-item">
        <div class="item-header">
          <span class="item-index">第 ${index} 题</span>
          <span class="winner-badge ${winnerClass}">${winnerText}</span>
        </div>
        
        <div class="qa-comparison">
          <div class="qa-side ${result.winner === 'A' ? 'winner' : ''}">
            <div class="qa-label">${data.datasetA_name} 问题</div>
            <div class="qa-text">${result.datasetA_qa ? result.datasetA_qa.question : (result.question || '')}</div>
            <div class="qa-label">${data.datasetA_name} 答案</div>
            <div class="qa-text">${result.datasetA_qa ? result.datasetA_qa.answer : (result.datasetA_answer || '')}</div>
          </div>
          
          <div class="qa-side ${result.winner === 'B' ? 'winner' : ''}">
            <div class="qa-label">${data.datasetB_name} 问题</div>
            <div class="qa-text">${result.datasetB_qa ? result.datasetB_qa.question : (result.question || '')}</div>
            <div class="qa-label">${data.datasetB_name} 答案</div>
            <div class="qa-text">${result.datasetB_qa ? result.datasetB_qa.answer : (result.datasetB_answer || '')}</div>
          </div>
        </div>
        
        ${result.reason ? `
          <div class="evaluation-reason">
            <div class="reason-title">🤖 评价理由</div>
            <div class="reason-text">${result.reason}</div>
          </div>
        ` : ''}
      </div>
    `;
  }

  async loadHistory() {
    try {
      const response = await fetch('/api/comparison/history');
      const data = await response.json();
      
      this.renderHistory(data.history || []);
    } catch (error) {
      console.error('加载历史记录失败:', error);
    }
  }

  renderHistory(history) {
    const historyContainer = document.querySelector('.history-list');
    if (!historyContainer) return;

    if (history.length === 0) {
      historyContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📊</div>
          <div class="empty-title">暂无历史记录</div>
          <div class="empty-description">完成对比评测后，结果将显示在这里</div>
        </div>
      `;
      return;
    }

    historyContainer.innerHTML = history.map(item => {
      // 格式化获胜者显示
      let winnerDisplay = '平局';
      if (item.winner === 'datasetA' || item.winner === 'A') {
        winnerDisplay = item.datasetA_name;
      } else if (item.winner === 'datasetB' || item.winner === 'B') {
        winnerDisplay = item.datasetB_name;
      }
      
      return `
        <div class="history-item" data-history-id="${item.id}">
          <div class="history-header">
            <div class="history-datasets">${item.datasetA_name} vs ${item.datasetB_name}</div>
            <div class="history-date">${item.completed_at}</div>
          </div>
          <div class="history-result">
            获胜者: <span class="history-winner">${winnerDisplay}</span> 
            (${item.datasetA_score || 0} : ${item.datasetB_score || 0})
          </div>
        </div>
      `;
    }).join('');
  }

  async loadHistoryDetail(historyId) {
    try {
      const response = await fetch(`/api/comparison/history/${historyId}`);
      const data = await response.json();
      
      if (response.ok) {
        this.renderCompleteResults(data);
        // 滚动到结果区域
        document.querySelector('.comparison-results')?.scrollIntoView({ 
          behavior: 'smooth' 
        });
      }
    } catch (error) {
      this.showError('加载历史详情失败: ' + error.message);
    }
  }

  setRunningState(isRunning) {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const configInputs = document.querySelectorAll('.form-input, .form-select');

    startBtn.disabled = isRunning;
    stopBtn.style.display = isRunning ? 'inline-flex' : 'none';
    
    configInputs.forEach(input => {
      input.disabled = isRunning;
    });

    // 显示/隐藏进度面板
    const progressSection = document.querySelector('.progress-section');
    if (progressSection) {
      progressSection.style.display = isRunning ? 'block' : 'none';
    }
  }

  clearResults() {
    const resultsContainer = document.querySelector('.comparison-results');
    if (resultsContainer) {
      resultsContainer.innerHTML = '';
    }
    this.comparisonResults = [];
  }

  showLoading(message = '加载中...') {
    const overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.innerHTML = `
      <div class="loading-content">
        <div class="loading-spinner-large"></div>
        <div class="loading-text">${message}</div>
      </div>
    `;
    overlay.id = 'loadingOverlay';
    document.body.appendChild(overlay);
  }

  hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
      overlay.remove();
    }
  }

  showSuccess(message) {
    this.showNotification(message, 'success');
  }

  showError(message) {
    this.showNotification(message, 'error');
  }

  showWarning(message) {
    this.showNotification(message, 'warning');
  }

  showInfo(message) {
    this.showNotification(message, 'info');
  }

  showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 16px 20px;
      border-radius: 8px;
      color: white;
      font-weight: 500;
      z-index: 10000;
      max-width: 400px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      animation: slideIn 0.3s ease;
    `;

    const colors = {
      success: '#10b981',
      error: '#ef4444',
      warning: '#f59e0b',
      info: '#3b82f6'
    };

    notification.style.background = colors[type] || colors.info;
    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
      notification.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => notification.remove(), 300);
    }, 3000);
  }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
  new ComparisonEvaluation();
});

// 添加CSS动画
const style = document.createElement('style');
style.textContent = `
  @keyframes slideIn {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  @keyframes slideOut {
    from {
      transform: translateX(0);
      opacity: 1;
    }
    to {
      transform: translateX(100%);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style); 