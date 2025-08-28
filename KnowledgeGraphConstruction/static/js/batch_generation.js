/**
 * 批量生成页面JavaScript
 */

class BatchGenerationManager {
  constructor() {
    // Socket.IO连接
    this.socket = io();
    
    // 全局变量
    this.isBatchGenerating = false;
    this.generatedResults = [];
    this.currentBatchId = null;
    this.taskProgress = {
      total: 0,
      completed: 0,
      tasks: []
    };
    
    // DOM元素
    this.startBatchBtn = document.getElementById('start-batch-btn');
    this.stopBatchBtn = document.getElementById('stop-batch-btn');
    this.saveToEvaluationBtn = document.getElementById('save-to-evaluation-btn');
    this.saveEntitySetBtn = document.getElementById('save-entity-set-btn');
    this.previewEntitiesBtn = document.getElementById('preview-entities-btn');
    this.progressFill = document.getElementById('progress-fill');
    this.progressText = document.getElementById('progress-text');
    this.completedCountEl = document.getElementById('completed-count');
    this.totalCountEl = document.getElementById('total-count');
    this.resultsContainer = document.getElementById('results-container');
    this.importMethodSelect = document.getElementById('import-method');
    this.manualInputSection = document.getElementById('manual-input-section');
    this.fileUploadSection = document.getElementById('file-upload-section');
    this.inputHelpText = document.getElementById('input-help-text');
    this.entitySetsList = document.getElementById('entity-sets-list');
    this.selectedEntitySetSelect = document.getElementById('selected-entity-set');
    this.entitySetInfo = document.getElementById('entity-set-info');
    this.entitySetDetails = document.getElementById('entity-set-details');
    this.taskList = document.getElementById('task-list');
    this.enableInstantSaveCheckbox = document.getElementById('enable-instant-save');
    this.saveFilenameGroup = document.getElementById('save-filename-group');
    this.saveFilenameInput = document.getElementById('save-filename');
    this.enableResumeCheckbox = document.getElementById('enable-resume');
    this.resumeFileSelect = document.getElementById('resume-file');

    this.init();
  }

  init() {
    this.setupEventListeners();
    this.updateUI();
    this.loadEntitySets();
    this.loadGeneratedFiles();
  }

  setupEventListeners() {
    // 导入方式切换
    this.importMethodSelect?.addEventListener('change', () => this.handleImportMethodChange());
    
    // 按钮事件
    this.previewEntitiesBtn?.addEventListener('click', () => this.previewEntities());
    this.startBatchBtn?.addEventListener('click', () => this.startBatchGeneration());
    this.stopBatchBtn?.addEventListener('click', () => this.stopBatchGeneration());
    this.saveToEvaluationBtn?.addEventListener('click', () => this.saveToEvaluation());
    this.saveEntitySetBtn?.addEventListener('click', () => this.saveEntitySet());
    
    // 即时保存和断点续传
    this.enableInstantSaveCheckbox?.addEventListener('change', () => this.handleInstantSaveChange());
    this.enableResumeCheckbox?.addEventListener('change', () => this.handleResumeChange());
    this.selectedEntitySetSelect?.addEventListener('change', () => this.handleEntitySetChange());

    // Socket.IO事件
    this.socket.on('connect', () => console.log('已连接到服务器'));
    this.socket.on('disconnect', () => console.log('已断开与服务器的连接'));
    this.socket.on('batch_progress', (data) => this.handleBatchProgress(data));
    this.socket.on('batch_result', (data) => this.handleBatchResult(data));
    this.socket.on('batch_complete', (data) => this.handleBatchComplete(data));
    this.socket.on('batch_error', (data) => this.handleBatchError(data));
            this.socket.on('log_message', (data) => {
            // 包含trace信息的日志显示
            let message = data.message;
            if (data.trace_id && data.trace_id !== 'NO_TRACE') {
                message = `[${data.trace_id}] ${message}`;
            }
            console.log(`[${data.level}] ${message}`);
        });
  }

  handleImportMethodChange() {
    const method = this.importMethodSelect.value;
    if (method === 'csv_file') {
      if (this.manualInputSection) this.manualInputSection.style.display = 'none';
      if (this.fileUploadSection) {
        this.fileUploadSection.style.display = 'block';
        this.fileUploadSection.classList.add('active');
      }
    } else {
      if (this.manualInputSection) this.manualInputSection.style.display = 'block';
      if (this.fileUploadSection) {
        this.fileUploadSection.style.display = 'none';
        this.fileUploadSection.classList.remove('active');
      }
      
      // 更新提示文本
      if (this.inputHelpText) {
        if (method === 'manual_newline') {
          this.inputHelpText.textContent = '每行输入一个实体名称';
        } else if (method === 'manual_comma') {
          this.inputHelpText.textContent = '使用逗号分割多个实体，例如：量子计算机,人工智能,基因编辑';
        } else if (method === 'manual_semicolon') {
          this.inputHelpText.textContent = '使用分号分割多个实体，例如：量子计算机;人工智能;基因编辑';
        }
      }
    }
  }

  previewEntities() {
    const seedSource = document.getElementById('seed-source')?.value;
    const count = parseInt(document.getElementById('generation-count')?.value) || 10;
    const categoryFilter = document.getElementById('category-filter')?.value;
    
    if (seedSource === 'manual') {
      const manualEntities = document.getElementById('manual-entities')?.value
        .split('\n')
        .map(e => e.trim())
        .filter(e => e.length > 0);
      
      if (!manualEntities || manualEntities.length === 0) {
        alert('请输入至少一个实体');
        return;
      }
      
      this.showEntityPreview(manualEntities);
    } else if (seedSource === 'wikidata') {
      // 调用后端API预览WikiData实体
      fetch('/api/preview_entities', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source: 'wikidata',
          count: count,
          category: categoryFilter
        })
      })
      .then(response => response.json())
      .then(data => {
        if (data.entities) {
          this.showEntityPreview(data.entities);
        } else {
          alert('获取实体预览失败');
        }
      })
      .catch(error => {
        console.error('预览实体失败:', error);
        alert('预览实体失败');
      });
    } else {
      const entities = this.parseEntities();
      if (!entities || entities.length === 0) {
        alert('请提供实体数据');
        return;
      }
      
      this.showEntityPreview(entities);
    }
  }

  startBatchGeneration() {
    if (this.isBatchGenerating) return;
    
    const config = this.getGenerationConfig();
    if (!this.validateConfig(config)) return;
    
    // 重置状态
    this.isBatchGenerating = true;
    this.generatedResults = [];
    this.updateUI();
    this.resetTaskList();
    this.clearResults();
    
    // 发送批量生成请求
    fetch('/api/batch_generation/start', {
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
      this.currentBatchId = data.batch_id;
      this.taskProgress.total = data.count || 0;
      this.updateProgressInfo('批量生成开始', 0);
    })
    .catch(error => {
      console.error('批量生成失败:', error);
      this.isBatchGenerating = false;
      this.updateUI();
    });
  }

  stopBatchGeneration() {
    if (!this.isBatchGenerating) return;
    
    fetch('/api/batch_generation/stop', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({batch_id: this.currentBatchId})
    })
    .then(response => response.json())
    .then(data => {
      console.log('已停止批量生成');
      this.isBatchGenerating = false;
      this.updateUI();
    })
    .catch(error => {
      console.error('停止失败:', error);
    });
  }

  saveToEvaluation() {
    if (this.generatedResults.length === 0) {
      alert('没有可保存的结果');
      return;
    }
    
    const datasetName = prompt('请输入数据集名称:', `batch_${new Date().toISOString().slice(0, 10)}`);
    if (!datasetName) return;
    
    fetch('/api/evaluation_data/save', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name: datasetName,
        type: 'generated',
        data: this.generatedResults,
        metadata: {
          generated_at: new Date().toISOString(),
          batch_id: this.currentBatchId,
          count: this.generatedResults.length
        }
      })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        console.log(`数据已保存到评测数据集: ${datasetName}`);
        alert('保存成功！');
      } else {
        throw new Error(data.error || '保存失败');
      }
    })
    .catch(error => {
      console.error('保存失败:', error);
      alert('保存失败');
    });
  }

  saveEntitySet() {
    const entitySetName = document.getElementById('entity-set-name')?.value.trim();
    if (!entitySetName) {
      alert('请输入实体集名称');
      return;
    }
    
    const entities = this.parseEntities();
    if (!entities || entities.length === 0) {
      alert('请提供实体数据');
      return;
    }
    
    const importMethod = this.importMethodSelect.value;
    
    if (importMethod === 'csv_file') {
      const fileInput = document.getElementById('csv-file');
      const file = fileInput?.files[0];
      if (!file) {
        alert('请选择CSV文件');
        return;
      }
      
      const formData = new FormData();
      formData.append('file', file);
      formData.append('name', entitySetName);
      
      fetch('/api/entity_sets/upload', {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          console.log(`实体集 "${entitySetName}" 保存成功，共${data.count}个实体`);
          this.loadEntitySets();
          // 清空表单
          document.getElementById('entity-set-name').value = '';
          document.getElementById('csv-file').value = '';
        } else {
          throw new Error(data.error || '保存失败');
        }
      })
      .catch(error => {
        console.error('保存实体集失败:', error);
        alert('保存失败');
      });
    } else {
      // 手动输入方式
      fetch('/api/entity_sets/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: entitySetName,
          entities: entities,
          import_method: importMethod
        })
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          console.log(`实体集 "${entitySetName}" 保存成功，共${data.count}个实体`);
          this.loadEntitySets();
          // 清空表单
          document.getElementById('entity-set-name').value = '';
          document.getElementById('manual-entities').value = '';
        } else {
          throw new Error(data.error || '保存失败');
        }
      })
      .catch(error => {
        console.error('保存实体集失败:', error);
        alert('保存失败');
      });
    }
  }

  handleInstantSaveChange() {
    if (this.enableInstantSaveCheckbox.checked) {
      if (this.saveFilenameGroup) this.saveFilenameGroup.classList.add('active');
      // 自动生成文件名
      const now = new Date();
      const timestamp = now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_');
      if (this.saveFilenameInput) this.saveFilenameInput.value = `batch_generated_${timestamp}.jsonl`;
      
      // 加载已有的生成文件列表
      this.loadGeneratedFiles();
    } else {
      if (this.saveFilenameGroup) this.saveFilenameGroup.classList.remove('active');
    }
  }

  handleResumeChange() {
    if (this.enableResumeCheckbox.checked) {
      this.loadGeneratedFiles();
    }
  }

  handleEntitySetChange() {
    const selectedName = this.selectedEntitySetSelect.value;
    if (selectedName) {
      fetch(`/api/entity_sets/info/${selectedName}`)
        .then(response => response.json())
        .then(data => {
          if (data.success && this.entitySetInfo && this.entitySetDetails) {
            this.entitySetInfo.classList.add('active');
            this.entitySetDetails.innerHTML = `
              <strong>实体集：</strong>${data.entity_set.name}<br>
              <strong>实体数量：</strong>${data.entity_set.count}<br>
              <strong>创建时间：</strong>${new Date(data.entity_set.created_at).toLocaleString()}<br>
              <strong>导入方式：</strong>${data.entity_set.import_method}
            `;
          } else {
            if (this.entitySetInfo) this.entitySetInfo.classList.remove('active');
          }
        })
        .catch(error => {
          console.error('获取实体集信息失败:', error);
          if (this.entitySetInfo) this.entitySetInfo.classList.remove('active');
        });
    } else {
      if (this.entitySetInfo) this.entitySetInfo.classList.remove('active');
    }
  }

  // Socket.IO事件处理
  handleBatchProgress(data) {
    console.log('批量生成进度:', data);
    
    // 更新进度信息
    const progress = data.progress;
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
        this.updateProgressInfo(data.step, progress);
      }
    }
  }

  handleBatchResult(data) {
    console.log('批量生成结果:', data);
    this.addResult(data);
    
    // 如果启用了即时保存，显示保存状态
    const enableInstantSave = this.enableInstantSaveCheckbox?.checked;
    if (enableInstantSave) {
      const entityName = data.initial_entity || data.entity || 'unknown';
      console.log(`✅ 即时保存: ${entityName}`);
    }
  }

  handleBatchComplete(data) {
    console.log('批量生成完成:', data);
    this.isBatchGenerating = false;
    this.updateUI();
    
    // 显示完成信息，包括即时保存状态
    let completeMessage = data.message || '批量生成完成';
    if (data.instant_save) {
      completeMessage += ' (即时保存模式)';
    }
    if (data.saved_file) {
      completeMessage += ` - 文件: ${data.saved_file}`;
    }
    
    this.updateProgressInfo(completeMessage, 100);
    
    // 如果启用了即时保存，刷新文件列表
    const enableInstantSave = this.enableInstantSaveCheckbox?.checked;
    if (enableInstantSave) {
      setTimeout(() => this.loadGeneratedFiles(), 1000); // 延迟1秒刷新文件列表
    }
  }

  handleBatchError(data) {
    console.error('批量生成错误:', data);
    this.isBatchGenerating = false;
    this.updateUI();
  }

  // 工具方法
  addTaskToList(taskId, message, status = 'running') {
    if (!this.taskList) return;
    
    const taskItem = document.createElement('div');
    taskItem.className = `task-item ${status}`;
    taskItem.id = `task-${taskId}`;
    
    taskItem.innerHTML = `
      <div class="task-status-icon ${status}"></div>
      <div class="task-message">${message}</div>
    `;
    
    this.taskList.appendChild(taskItem);
    
    // 滚动到底部
    this.taskList.scrollTop = this.taskList.scrollHeight;
  }

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

  resetTaskList() {
    this.taskProgress = {
      total: 0,
      completed: 0,
      tasks: []
    };
    
    if (this.taskList) this.taskList.innerHTML = '';
    this.updateProgressInfo('', 0);
  }

  updateProgressInfo(step, progress) {
    // 只在progress不为null时更新进度条
    if (progress !== null && progress !== undefined) {
      if (this.progressFill) this.progressFill.style.width = `${progress}%`;
      if (this.progressText) this.progressText.textContent = `${progress.toFixed(1)}%`;
    }
    
    // 更新任务计数
    if (this.completedCountEl) this.completedCountEl.textContent = this.taskProgress.completed;
    if (this.totalCountEl) this.totalCountEl.textContent = this.taskProgress.total;
  }

  parseEntities() {
    const importMethod = this.importMethodSelect.value;
    
    if (importMethod === 'csv_file') {
      // CSV文件会在上传时处理
      return null;
    } else {
      const textValue = document.getElementById('manual-entities')?.value.trim();
      if (!textValue) return [];
      
      let entities = [];
      if (importMethod === 'manual_newline') {
        entities = textValue.split('\n');
      } else if (importMethod === 'manual_comma') {
        entities = textValue.split(',');
      } else if (importMethod === 'manual_semicolon') {
        entities = textValue.split(';');
      }
      
      return entities
        .map(e => e.trim())
        .filter(e => e.length > 0);
    }
  }

  showEntityPreview(entities) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-content small">
        <div class="modal-header">
          <h3>实体预览 (${entities.length}个)</h3>
        </div>
        <div class="modal-body">
          <div class="entity-preview-list">
            ${entities.map((entity, index) => `
              <div class="entity-preview-item">
                <span class="entity-preview-index">${index + 1}.</span>
                <span>${entity}</span>
              </div>
            `).join('')}
          </div>
        </div>
        <div class="modal-footer">
          <button onclick="this.parentElement.parentElement.parentElement.remove()" class="btn btn-primary">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  loadEntitySets() {
    fetch('/api/entity_sets/list')
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          this.updateEntitySetsList(data.entity_sets);
          this.updateEntitySetsSelect(data.entity_sets);
        } else {
          console.error('加载实体集列表失败:', data.error);
        }
      })
      .catch(error => {
        console.error('加载实体集列表失败:', error);
      });
  }

  updateEntitySetsList(entitySets) {
    if (!this.entitySetsList) return;
    
    if (!entitySets || entitySets.length === 0) {
      this.entitySetsList.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📁</div>
          <p>暂无保存的实体集</p>
        </div>
      `;
      return;
    }
    
    const html = entitySets.map(entitySet => `
      <div class="entity-set-card">
        <div class="entity-set-card-content">
          <div>
            <div class="entity-set-card-title">${entitySet.name}</div>
            <div class="entity-set-card-meta">
              实体数量: ${entitySet.count} | 
              创建时间: ${new Date(entitySet.created_at).toLocaleString()} |
              导入方式: ${entitySet.import_method}
            </div>
          </div>
          <button onclick="batchGenerationManager.deleteEntitySet('${entitySet.name}')" class="btn-small btn-delete">删除</button>
        </div>
      </div>
    `).join('');
    
    this.entitySetsList.innerHTML = html;
  }

  updateEntitySetsSelect(entitySets) {
    if (!this.selectedEntitySetSelect) return;
    
    this.selectedEntitySetSelect.innerHTML = '<option value="">请选择实体集...</option>';
    
    if (entitySets && entitySets.length > 0) {
      entitySets.forEach(entitySet => {
        const option = document.createElement('option');
        option.value = entitySet.name;
        option.textContent = `${entitySet.name} (${entitySet.count}个实体)`;
        this.selectedEntitySetSelect.appendChild(option);
      });
    }
  }

  deleteEntitySet(name) {
    if (!confirm(`确定要删除实体集 "${name}" 吗？`)) {
      return;
    }
    
    fetch(`/api/entity_sets/delete/${name}`, {
      method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        console.log(`实体集 "${name}" 删除成功`);
        this.loadEntitySets();
      } else {
        throw new Error(data.error || '删除失败');
      }
    })
    .catch(error => {
      console.error('删除实体集失败:', error);
      alert('删除失败');
    });
  }

  loadGeneratedFiles() {
    fetch('/api/generated_files/list')
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          this.updateResumeFileSelect(data.files);
        } else {
          console.error('加载生成文件列表失败:', data.error);
        }
      })
      .catch(error => {
        console.error('加载生成文件列表失败:', error);
      });
  }

  updateResumeFileSelect(files) {
    if (!this.resumeFileSelect) return;
    
    this.resumeFileSelect.innerHTML = '<option value="">从头开始（不续传）</option>';
    
    if (files && files.length > 0) {
      files.forEach(file => {
        const option = document.createElement('option');
        option.value = file.filename;
        option.textContent = `${file.filename} (${file.count}条记录, ${file.modified_time})`;
        this.resumeFileSelect.appendChild(option);
      });
    }
  }

  validateConfig(config) {
    if (!config) {
      return false;
    }
    
    if (!config.entity_set) {
      alert('请选择实体集');
      return false;
    }
    
    return true;
  }

  updateUI() {
    if (this.startBatchBtn) this.startBatchBtn.disabled = this.isBatchGenerating;
    if (this.stopBatchBtn) this.stopBatchBtn.disabled = !this.isBatchGenerating;
    if (this.saveToEvaluationBtn) this.saveToEvaluationBtn.disabled = this.generatedResults.length === 0;
  }

  addResult(result) {
    this.generatedResults.push(result);
    
    const entityName = result.initial_entity || result.entity || 'unknown';
    
    const resultEl = document.createElement('div');
    resultEl.className = 'result-card';
    resultEl.innerHTML = `
      <div class="result-header">
        <div>
          <div class="result-title">${entityName}</div>
          <div class="result-meta">
            节点: ${result.graph_info?.node_count || 0} | 
            关系: ${result.graph_info?.relationship_count || 0} |
            复杂度: ${result.qa_pair?.complexity || 'unknown'}
          </div>
        </div>
      </div>
      <div class="result-question">
        <strong>问题:</strong> ${(result.qa_pair?.question || '').substring(0, 100)}...
      </div>
    `;
    
    if (this.resultsContainer.children.length === 1 && this.resultsContainer.children[0].textContent.includes('点击')) {
      this.resultsContainer.innerHTML = '';
    }
    
    this.resultsContainer.appendChild(resultEl);
    
    // 更新计数
    const completedCountEl = document.getElementById('completed-count');
    if (completedCountEl) completedCountEl.textContent = this.generatedResults.length;
    
    this.updateUI();
  }

  clearResults() {
    if (!this.resultsContainer) return;
    
    this.resultsContainer.innerHTML = `
      <div class="results-empty-state">
        <div class="results-empty-icon">📋</div>
        <p>生成中...</p>
      </div>
    `;
    
    const completedCountEl = document.getElementById('completed-count');
    const totalCountEl = document.getElementById('total-count');
    if (completedCountEl) completedCountEl.textContent = '0';
    if (totalCountEl) totalCountEl.textContent = '0';
  }

  getGenerationConfig() {
    const selectedEntitySet = this.selectedEntitySetSelect?.value;
    
    if (!selectedEntitySet) {
      alert('请选择实体集');
      return null;
    }
    
    const config = {
      entity_set: selectedEntitySet,
      max_nodes: parseInt(document.getElementById('max-nodes')?.value) || 30,
      max_iterations: parseInt(document.getElementById('max-iterations')?.value) || 3,
      sample_size: parseInt(document.getElementById('sample-size')?.value) || 8,
      sampling_algorithm: document.getElementById('sampling-algorithm')?.value || 'mixed',
      anonymize_probability: parseFloat(document.getElementById('anonymize-prob')?.value) || 0.3,
      parallel_workers: parseInt(document.getElementById('parallel-workers')?.value) || 2
    };
    
    // 即时保存配置
    const enableInstantSave = this.enableInstantSaveCheckbox?.checked;
    if (enableInstantSave) {
      const filename = this.saveFilenameInput?.value.trim();
      if (!filename) {
        alert('请输入保存文件名');
        return null;
      }
      config.instant_save = {
        enabled: true,
        filename: filename
      };
    } else {
      config.instant_save = {
        enabled: false
      };
    }
    
    // 断点续传配置
    const enableResume = this.enableResumeCheckbox?.checked;
    if (enableResume && this.resumeFileSelect?.value) {
      config.resume = {
        enabled: true,
        filename: this.resumeFileSelect.value
      };
    } else {
      config.resume = {
        enabled: false
      };
    }
    
    return config;
  }
}

// 全局函数 - 兼容现有HTML中的onclick调用
let batchGenerationManager;

function viewResult(index) {
  const result = batchGenerationManager.generatedResults[index];
  if (!result) return;
  
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>${result.entity} - 生成结果</h3>
      </div>
      <div class="modal-body">
        <div class="modal-section">
          <h4 class="modal-section-title">图谱信息</h4>
          <p class="modal-info-text">
            节点数: ${result.graph_info?.node_count || 0} | 
            关系数: ${result.graph_info?.relationship_count || 0}
          </p>
        </div>
        
        ${result.qa_pair ? `
        <div class="modal-section">
          <h4 class="modal-section-title">❓ 问题</h4>
          <div class="qa-question-box">
            ${result.qa_pair.question}
          </div>
        </div>
        
        <div class="modal-section">
          <h4 class="modal-section-title">✅ 答案</h4>
          <div class="qa-answer-box">
            ${result.qa_pair.answer}
          </div>
        </div>
        
        ${result.qa_pair.reasoning_path || result.qa_pair.reasoning ? `
        <div class="modal-section">
          <h4 class="modal-section-title">${result.qa_pair.reasoning_path ? '推理路径' : '推理过程'}</h4>
          <div class="qa-reasoning-box">
            ${result.qa_pair.reasoning_path || result.qa_pair.reasoning}
          </div>
        </div>
        ` : ''}
        ` : '<p class="qa-unavailable">QA信息不可用</p>'}
      </div>
      <div class="modal-footer">
        <button onclick="downloadResult(${index})" class="btn btn-secondary">下载JSON</button>
        <button onclick="this.parentElement.parentElement.parentElement.remove()" class="btn btn-primary">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
}

function downloadResult(index) {
  const result = batchGenerationManager.generatedResults[index];
  if (!result) return;
  
  const blob = new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${result.entity}_result.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  console.log('批量生成系统已初始化');
  batchGenerationManager = new BatchGenerationManager();
}); 