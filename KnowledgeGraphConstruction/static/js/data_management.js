// 数据管理页面JavaScript功能

class DataManager {
    constructor() {
        this.currentData = [];
        this.filteredData = [];
        this.currentPage = 1;
        this.pageSize = 10;
        this.currentFile = null;
        this.currentFiles = []; // 当前加载的多个文件信息
        this.selectedFiles = new Set(); // 选中的文件列表
        this.currentDirectory = null; // 当前文件所在目录
        this.editingIndex = -1;
        this.hasChanges = false;
        this.extractedEntities = [];
        this.selectedEntities = [];
        this.entityMapping = {};
        this.autoSaveMode = false;
        
        // 主页面实体替换功能
        this.selectedItems = new Set();
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadDirectoryList();
    }
    
    setupEventListeners() {
        // 文件选择相关
        document.getElementById('directorySelect').addEventListener('change', this.onDirectorySelectChange.bind(this));
        document.getElementById('loadFileBtn').addEventListener('click', this.loadSelectedFiles.bind(this));
        document.getElementById('refreshFilesBtn').addEventListener('click', this.loadDirectoryList.bind(this));
        document.getElementById('selectAllFilesBtn').addEventListener('click', this.selectAllFiles.bind(this));
        document.getElementById('clearFileSelectionBtn').addEventListener('click', this.clearFileSelection.bind(this));

        
        // 筛选相关
        document.getElementById('applyFilterBtn').addEventListener('click', this.applyFilters.bind(this));
        document.getElementById('clearFilterBtn').addEventListener('click', this.clearFilters.bind(this));
        document.getElementById('detectLanguageBtn').addEventListener('click', this.detectLanguages.bind(this));
        document.getElementById('detectLanguageLLMBtn').addEventListener('click', this.detectLanguagesLLM.bind(this));
        document.getElementById('saveChangesBtn').addEventListener('click', this.saveChanges.bind(this));
        
        // 模态框相关
        document.getElementById('closeEditModal').addEventListener('click', this.closeEditModal.bind(this));
        document.getElementById('saveEditBtn').addEventListener('click', this.saveEdit.bind(this));
        document.getElementById('cancelEditBtn').addEventListener('click', this.closeEditModal.bind(this));
        
        document.getElementById('closeDeleteModal').addEventListener('click', this.closeDeleteModal.bind(this));
        document.getElementById('confirmDeleteBtn').addEventListener('click', this.confirmDelete.bind(this));
        document.getElementById('cancelDeleteBtn').addEventListener('click', this.closeDeleteModal.bind(this));
        
        // 实体映射相关
        document.getElementById('extractEntitiesBtn').addEventListener('click', this.extractEntities.bind(this));
        document.getElementById('showEntityMappingBtn').addEventListener('click', this.showEntityMapping.bind(this));
        document.getElementById('copyFromOriginalBtn').addEventListener('click', this.copyFromOriginal.bind(this));
        
        // 自动保存模式切换
        document.getElementById('autoSaveMode').addEventListener('change', this.onAutoSaveModeChange.bind(this));
        
        // 搜索框实时搜索
        document.getElementById('keywordFilter').addEventListener('input', this.debounce(this.applyFilters.bind(this), 300));
        
        // 主页面实体替换功能
        document.getElementById('selectAllBtn').addEventListener('click', this.selectAll.bind(this));
        document.getElementById('selectAllDataBtn').addEventListener('click', this.selectAllData.bind(this));
        document.getElementById('clearSelectionBtn').addEventListener('click', this.clearSelection.bind(this));
        document.getElementById('previewAllBtn').addEventListener('click', this.previewAllReasoningPaths.bind(this));
        document.getElementById('hideAllPreviewBtn').addEventListener('click', this.hideAllReasoningPreviews.bind(this));
        document.getElementById('previewReplacementBtn').addEventListener('click', this.previewEntityReplacement.bind(this));
        document.getElementById('applyReplacementBtn').addEventListener('click', this.applyEntityReplacement.bind(this));
        
        // 每页显示数量选择
        document.getElementById('pageSizeSelect').addEventListener('change', this.onPageSizeChange.bind(this));
        
        // 另存为功能
        document.getElementById('saveAsBtn').addEventListener('click', this.showSaveAsModal.bind(this));
        document.getElementById('closeSaveAsModal').addEventListener('click', this.closeSaveAsModal.bind(this));
        document.getElementById('cancelSaveAsBtn').addEventListener('click', this.closeSaveAsModal.bind(this));
        document.getElementById('confirmSaveAsBtn').addEventListener('click', this.confirmSaveAs.bind(this));
        
        // 反向替换功能
        document.getElementById('reverseReplaceBtn').addEventListener('click', this.reverseReplaceEntities.bind(this));
        
        // 筛选改动数据
        document.getElementById('showModifiedOnly').addEventListener('change', this.applyFilters.bind(this));
        
        // 另存为模态框内的事件
        document.getElementById('newFileName').addEventListener('input', this.updateSaveAsPreview.bind(this));
        document.querySelectorAll('input[name="saveScope"]').forEach(radio => {
            radio.addEventListener('change', this.updateSaveAsPreview.bind(this));
        });
        
        // 文本清理功能
        document.getElementById('customCleanBtn').addEventListener('click', this.showCustomCleanModal.bind(this));
        document.getElementById('entityKeyCleanBtn').addEventListener('click', this.cleanEntityKeys.bind(this));
        document.getElementById('closeCustomCleanModal').addEventListener('click', this.closeCustomCleanModal.bind(this));
        document.getElementById('cancelCustomCleanBtn').addEventListener('click', this.closeCustomCleanModal.bind(this));
        document.getElementById('previewCustomCleanBtn').addEventListener('click', this.previewCustomClean.bind(this));
        document.getElementById('applyCustomCleanBtn').addEventListener('click', this.applyCustomClean.bind(this));
        
        // 领域标签功能
        document.getElementById('domainTagFilter').addEventListener('change', this.applyFilters.bind(this));
        
        // 泄漏状态筛选功能
        document.getElementById('leakageStatusFilter').addEventListener('change', this.applyFilters.bind(this));
        
        // JSON转换功能
        document.getElementById('convertJsonBtn').addEventListener('click', this.showConvertJsonModal.bind(this));
        document.getElementById('closeConvertJsonModal').addEventListener('click', this.closeConvertJsonModal.bind(this));
        document.getElementById('cancelConvertBtn').addEventListener('click', this.closeConvertJsonModal.bind(this));
        document.getElementById('jsonFileInput').addEventListener('change', this.onJsonFileSelect.bind(this));
        document.getElementById('previewJsonBtn').addEventListener('click', this.previewJsonConversion.bind(this));
        document.getElementById('executeConvertBtn').addEventListener('click', this.executeJsonConversion.bind(this));
        
        // 信息泄漏检测功能
        document.getElementById('detectLeakageBtn').addEventListener('click', this.detectInformationLeakage.bind(this));
    }
    
    async loadDirectoryList() {
        try {
            const response = await fetch('/api/data_management/directories');
            const data = await response.json();
            
            const directorySelect = document.getElementById('directorySelect');
            directorySelect.innerHTML = '<option value="">请选择数据目录...</option>';
            
            if (data.success && data.directories) {
                data.directories.forEach(dir => {
                    const option = document.createElement('option');
                    option.value = dir.path;
                    option.textContent = `${dir.path} (${dir.file_count}个文件)`;
                    directorySelect.appendChild(option);
                });
            }
            
            // 重置文件选择
            this.resetFileSelection();
        } catch (error) {
            console.error('加载目录列表失败:', error);
            this.showNotification('加载目录列表失败', 'error');
        }
    }
    
    async loadFileList(directory) {
        try {
            if (!directory) {
                this.resetFileSelection();
                return;
            }
            
            const response = await fetch(`/api/data_management/files?directory=${encodeURIComponent(directory)}`);
            const data = await response.json();
            
            const fileContainer = document.getElementById('fileCheckboxContainer');
            fileContainer.innerHTML = '';
            
            if (data.success && data.files) {
                data.files.forEach((file, index) => {
                    const checkboxItem = this.createFileCheckboxItem(file, index);
                    fileContainer.appendChild(checkboxItem);
                });
                
                // 显示文件选择组和控制按钮
                document.getElementById('fileSelectGroup').style.display = 'block';
                document.getElementById('selectAllFilesBtn').style.display = 'inline-block';
                document.getElementById('clearFileSelectionBtn').style.display = 'inline-block';
            }
        } catch (error) {
            console.error('加载文件列表失败:', error);
            this.showNotification('加载文件列表失败', 'error');
        }
    }
    
    createFileCheckboxItem(file, index) {
        const checkboxItem = document.createElement('div');
        checkboxItem.className = 'file-checkbox-item';
        checkboxItem.innerHTML = `
            <input type="checkbox" id="file-${index}" value="${file.filename}" 
                   data-directory="${file.directory}" data-count="${file.count}" 
                   data-size="${file.size}" data-modified="${file.modified_time}"
                   onchange="window.dataManager.onFileCheckboxChange(this)">
            <div class="file-checkbox-content" onclick="window.dataManager.toggleFileCheckbox('file-${index}')">
                <div class="file-checkbox-name">${file.filename}</div>
                <div class="file-checkbox-info">
                    <span>${file.count}条数据</span>
                    <span>${this.formatFileSize(file.size)}</span>
                    <span>${file.modified_time}</span>
                </div>
                <div class="file-checkbox-path">${file.directory}</div>
            </div>
        `;
        return checkboxItem;
    }

    resetFileSelection() {
        const fileContainer = document.getElementById('fileCheckboxContainer');
        fileContainer.innerHTML = '';
        document.getElementById('fileSelectGroup').style.display = 'none';
        document.getElementById('selectAllFilesBtn').style.display = 'none';
        document.getElementById('clearFileSelectionBtn').style.display = 'none';
        document.getElementById('loadFileBtn').disabled = true;
        document.getElementById('fileInfo').style.display = 'none';
        document.getElementById('fileSelectionSummary').style.display = 'none';
        this.selectedFiles.clear();
    }
    
    onDirectorySelectChange() {
        const directorySelect = document.getElementById('directorySelect');
        const selectedDirectory = directorySelect.value;
        
        if (selectedDirectory) {
            this.loadFileList(selectedDirectory);
        } else {
            this.resetFileSelection();
        }
    }
    
    toggleFileCheckbox(checkboxId) {
        const checkbox = document.getElementById(checkboxId);
        checkbox.checked = !checkbox.checked;
        this.onFileCheckboxChange(checkbox);
    }

    onFileCheckboxChange(checkbox) {
        const filename = checkbox.value;
        const checkboxItem = checkbox.closest('.file-checkbox-item');
        
        if (checkbox.checked) {
            this.selectedFiles.add(filename);
            checkboxItem.classList.add('selected');
        } else {
            this.selectedFiles.delete(filename);
            checkboxItem.classList.remove('selected');
        }
        
        this.updateFileSelectionUI();
    }

    updateFileSelectionUI() {
        const count = this.selectedFiles.size;
        const summaryEl = document.getElementById('fileSelectionSummary');
        const countEl = document.getElementById('selectedFileCount');
        const loadBtn = document.getElementById('loadFileBtn');
        
        countEl.textContent = count;
        
        if (count > 0) {
            summaryEl.style.display = 'block';
            loadBtn.disabled = false;
        } else {
            summaryEl.style.display = 'none';
            loadBtn.disabled = true;
        }
        
        // 隐藏文件信息显示，会在加载后重新显示
        document.getElementById('fileInfo').style.display = 'none';
    }

    selectAllFiles() {
        const checkboxes = document.querySelectorAll('#fileCheckboxContainer input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            if (!checkbox.checked) {
                checkbox.checked = true;
                this.onFileCheckboxChange(checkbox);
            }
        });
    }

    clearFileSelection() {
        const checkboxes = document.querySelectorAll('#fileCheckboxContainer input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            if (checkbox.checked) {
                checkbox.checked = false;
                this.onFileCheckboxChange(checkbox);
            }
        });
    }
    
    async loadSelectedFiles() {
        if (this.selectedFiles.size === 0) {
            this.showNotification('请选择至少一个文件', 'warning');
            return;
        }
        
        const loadBtn = document.getElementById('loadFileBtn');
        const spinner = loadBtn.querySelector('.loading-spinner');
        
        try {
            loadBtn.disabled = true;
            spinner.style.display = 'inline-block';
            loadBtn.innerHTML = `<span class="loading-spinner"></span> 加载中... (0/${this.selectedFiles.size})`;
            
            // 获取选中文件的详细信息
            const selectedFileDetails = [];
            document.querySelectorAll('#fileCheckboxContainer input[type="checkbox"]:checked').forEach(checkbox => {
                selectedFileDetails.push({
                    filename: checkbox.value,
                    directory: checkbox.dataset.directory,
                    count: parseInt(checkbox.dataset.count),
                    size: parseInt(checkbox.dataset.size),
                    modified_time: checkbox.dataset.modified
                });
            });
            
            // 并行加载所有选中的文件
            const loadPromises = selectedFileDetails.map((fileDetail, index) => 
                this.loadSingleFile(fileDetail.filename, index + 1, selectedFileDetails.length)
            );
            
            const results = await Promise.all(loadPromises);
            
            // 合并所有文件的数据
            let allData = [];
            let failedFiles = [];
            const loadedFileInfos = [];
            
            results.forEach((result, index) => {
                if (result.success) {
                    // 为每条数据添加来源文件信息
                    const sourceFile = selectedFileDetails[index].filename;
                    result.data.forEach(item => {
                        item._source_file = sourceFile;
                    });
                    allData = allData.concat(result.data);
                    loadedFileInfos.push({
                        ...selectedFileDetails[index],
                        actualCount: result.data.length
                    });
                } else {
                    failedFiles.push(selectedFileDetails[index].filename);
                }
            });
            
            if (allData.length > 0) {
                this.currentData = allData;
                this.filteredData = [...this.currentData];
                this.currentFiles = loadedFileInfos;
                this.currentFile = loadedFileInfos.length === 1 ? loadedFileInfos[0].filename : `${loadedFileInfos.length}个文件`;
                this.currentDirectory = loadedFileInfos[0].directory;
                this.hasChanges = false;
                
                this.displayMultiFileInfo(loadedFileInfos);
                this.displayData();
                this.showDataToolbar();
                this.updateSaveButton();
                this.updateLanguageFilters();
                this.initializeDomainTagFilter();
                
                let message = `成功加载 ${allData.length} 条数据`;
                if (failedFiles.length > 0) {
                    message += `，失败文件: ${failedFiles.join(', ')}`;
                }
                this.showNotification(message, 'success');
            } else {
                throw new Error('所有文件加载失败');
            }
            
        } catch (error) {
            console.error('加载文件失败:', error);
            this.showNotification(`加载文件失败: ${error.message}`, 'error');
        } finally {
            loadBtn.disabled = false;
            spinner.style.display = 'none';
            loadBtn.innerHTML = '<span class="loading-spinner" style="display: none;"></span> 📖 加载选中文件';
        }
    }

    async loadSingleFile(filename, current, total) {
        try {
            // 更新加载进度
            const loadBtn = document.getElementById('loadFileBtn');
            loadBtn.innerHTML = `<span class="loading-spinner"></span> 加载中... (${current}/${total})`;
            
            const response = await fetch(`/api/data_management/load/${filename}`);
            const data = await response.json();
            
            if (data.success) {
                return {
                    success: true,
                    data: data.data,
                    fileInfo: data.fileInfo
                };
            } else {
                return {
                    success: false,
                    error: data.error
                };
            }
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    displayFileInfo(fileInfo) {
        document.getElementById('loadedFiles').textContent = fileInfo.filename;
        document.getElementById('recordCount').textContent = fileInfo.count;
        document.getElementById('totalFileSize').textContent = this.formatFileSize(fileInfo.size);
        document.getElementById('latestModifiedTime').textContent = fileInfo.modified_time;
        document.getElementById('fileInfo').style.display = 'block';
    }

    displayMultiFileInfo(fileInfos) {
        const totalCount = fileInfos.reduce((sum, info) => sum + info.actualCount, 0);
        const totalSize = fileInfos.reduce((sum, info) => sum + info.size, 0);
        const latestModified = fileInfos.reduce((latest, info) => 
            !latest || info.modified_time > latest ? info.modified_time : latest, null);
        
        const fileNames = fileInfos.map(info => info.filename).join(', ');
        
        document.getElementById('loadedFiles').textContent = fileInfos.length === 1 ? 
            fileInfos[0].filename : 
            `${fileInfos.length}个文件: ${fileNames}`;
        document.getElementById('recordCount').textContent = totalCount;
        document.getElementById('totalFileSize').textContent = this.formatFileSize(totalSize);
        document.getElementById('latestModifiedTime').textContent = latestModified;
        document.getElementById('fileInfo').style.display = 'block';
    }
    
    showDataToolbar() {
        document.getElementById('dataToolbar').style.display = 'block';
        document.getElementById('dataCard').style.display = 'block';
        
        // 初始化自动保存模式状态
        document.getElementById('autoSaveMode').checked = this.autoSaveMode;
        this.updateSaveButton();
        this.updateSelectionStatus();
    }
    
    displayData() {
        const dataList = document.getElementById('dataList');
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = startIndex + this.pageSize;
        const pageData = this.filteredData.slice(startIndex, endIndex);
        
        if (pageData.length === 0) {
            dataList.innerHTML = this.getEmptyStateHTML();
            document.getElementById('pagination').style.display = 'none';
        } else {
            dataList.innerHTML = pageData.map((item, index) => 
                this.createDataItemHTML(item, startIndex + index)
            ).join('');
            this.updatePagination();
        }
        
        this.updateDataStats();
        this.attachDataItemEventListeners();
    }
    
    createDataItemHTML(item, index) {
        const isLeakageFixed = item._leakage_fixed === true;
        const hasBackupFields = item.original_reasoning_path || item.original_entity_mapping;
        
        return `
            <div class="data-item ${this.selectedItems.has(index) ? 'selected' : ''} ${this.checkItemModified(item) ? 'modified-item' : ''} ${isLeakageFixed ? 'leakage-fixed' : ''}" data-index="${index}">
                <div class="data-item-header">
                    <div class="data-item-left">
                        <div class="data-item-checkbox show">
                            <input type="checkbox" id="item-${index}" ${this.selectedItems.has(index) ? 'checked' : ''} 
                                   onchange="window.dataManager.toggleItemSelection(${index})">
                            <label for="item-${index}"></label>
                        </div>
                        <div class="data-item-id">#${index + 1}</div>
                        ${item._source_file ? `<span class="source-file-badge">📁 ${item._source_file}</span>` : ''}
                        ${this.checkItemModified(item) ? '<span class="modification-badge">📝 已修改</span>' : ''}
                        ${isLeakageFixed ? '<span class="leakage-fixed-badge">🛡️ 已修正泄漏</span>' : ''}
                        ${hasBackupFields ? '<span class="backup-field-indicator">有备份</span>' : ''}
                    </div>
                    <div class="data-item-actions">
                        <button class="btn btn-sm btn-primary edit-btn" data-index="${index}">
                            ✏️ 编辑
                        </button>
                        <button class="btn btn-sm btn-danger delete-btn" data-index="${index}">
                            🗑️ 删除
                        </button>
                    </div>
                </div>
                <div class="data-item-content">
                    <div class="content-section">
                        <div class="content-label">
                            ❓ 问题
                            ${this.getLanguageBadge(item.question_language)}
                        </div>
                        <div class="content-text">${this.escapeHtml(item.question || '')}</div>
                    </div>
                    <div class="content-section">
                        <div class="content-label">
                            ✅ 答案
                            ${this.getLanguageBadge(item.answer_language)}
                        </div>
                        <div class="content-text">${this.escapeHtml(item.answer || '')}</div>
                    </div>
                    ${item.domain_tags && item.domain_tags.length > 0 ? `
                        <div class="content-section">
                            <div class="content-label">🏷️ 领域标签</div>
                            <div class="domain-tags">
                                ${this.renderDomainTags(item.domain_tags)}
                            </div>
                        </div>
                    ` : ''}
                    ${item.reasoning_path ? `
                        <div class="content-section">
                            <div class="content-label">
                                🧠 推理路径
                                ${item.entity_mapping && Object.keys(item.entity_mapping).length > 0 ? `
                                    <button class="btn btn-xs btn-secondary preview-replace-btn" 
                                            data-index="${index}" 
                                            onclick="window.dataManager.toggleReasoningPreview(${index})">
                                        🔄 预览替换
                                    </button>
                                ` : ''}
                            </div>
                            <div class="reasoning-content" id="reasoning-${index}">
                                <div class="reasoning-original" id="reasoning-original-${index}">
                                    ${this.escapeHtml(item.reasoning_path)}
                                </div>
                                <div class="reasoning-replaced" id="reasoning-replaced-${index}" style="display: none;">
                                    ${item.entity_mapping && Object.keys(item.entity_mapping).length > 0 ? 
                                        this.escapeHtml(this.replaceEntitiesInText(item.reasoning_path, item.entity_mapping)) : 
                                        this.escapeHtml(item.reasoning_path)
                                    }
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    ${item.mapped_reasoning_path ? `
                        <div class="content-section">
                            <div class="content-label">
                                🔄 映射后推理路径
                                <button class="btn btn-xs btn-success apply-replace-btn" 
                                        data-index="${index}" 
                                        onclick="window.dataManager.applyReplacementToItem(${index})"
                                        title="应用此替换结果到当前项目">
                                    ✅ 应用替换
                                </button>
                            </div>
                            <div class="reasoning-content">
                                <div class="reasoning-replaced">
                                    ${this.escapeHtml(item.mapped_reasoning_path)}
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    ${this.renderLeakageDetectionResult(item, index)}
                </div>
            </div>
        `;
    }
    
    getLanguageBadge(language) {
        const langMap = {
            'zh': { text: '中文', class: 'language-zh' },
            'en': { text: 'English', class: 'language-en' },
            'ja': { text: '日本語', class: 'language-ja' },
            'ko': { text: '한국어', class: 'language-ko' },
            'fr': { text: 'Français', class: 'language-fr' },
            'de': { text: 'Deutsch', class: 'language-de' },
            'es': { text: 'Español', class: 'language-es' },
            'it': { text: 'Italiano', class: 'language-it' },
            'pt': { text: 'Português', class: 'language-pt' },
            'ru': { text: 'Русский', class: 'language-ru' },
            'ar': { text: 'العربية', class: 'language-ar' },
            'hi': { text: 'हिन्दी', class: 'language-hi' },
            'th': { text: 'ไทย', class: 'language-th' },
            'vi': { text: 'Tiếng Việt', class: 'language-vi' },
            'unknown': { text: '未知语言', class: 'language-unknown' }
        };
        
        const lang = langMap[language] || { text: language || '未检测', class: 'language-other' };
        return `<span class="language-badge ${lang.class}">${lang.text}</span>`;
    }
    
    attachDataItemEventListeners() {
        document.querySelectorAll('.edit-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                this.editItem(index);
            });
        });
        
        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                this.deleteItem(index);
            });
        });
    }
    
    applyFilters() {
        const questionLang = document.getElementById('questionLangFilter').value;
        const answerLang = document.getElementById('answerLangFilter').value;
        const keyword = document.getElementById('keywordFilter').value.toLowerCase();
        const showModifiedOnly = document.getElementById('showModifiedOnly').checked;
        const domainTag = document.getElementById('domainTagFilter').value;
        const leakageStatus = document.getElementById('leakageStatusFilter').value;
        
        this.filteredData = this.currentData.filter(item => {
            // 语言筛选
            if (questionLang && item.question_language !== questionLang) return false;
            if (answerLang && item.answer_language !== answerLang) return false;
            
            // 标签筛选
            if (domainTag) {
                if (!item.domain_tags || !Array.isArray(item.domain_tags) || !item.domain_tags.includes(domainTag)) {
                    return false;
                }
            }
            
            // 泄漏状态筛选
            if (leakageStatus) {
                const hasLeakageResult = item._leakage_detection_result;
                const isFixed = item._leakage_fixed === true;
                
                switch (leakageStatus) {
                    case 'has_leakage_unfixed':
                        // 有泄漏且未修复
                        if (!hasLeakageResult || hasLeakageResult.has_leakage !== true || isFixed) return false;
                        break;
                    case 'has_leakage_fixed':
                        // 有泄漏且已修复
                        if (!hasLeakageResult || hasLeakageResult.has_leakage !== true || !isFixed) return false;
                        break;
                    case 'no_leakage':
                        // 无泄漏
                        if (!hasLeakageResult || hasLeakageResult.has_leakage !== false) return false;
                        break;
                    case 'unknown':
                        // 未识别
                        if (!hasLeakageResult || hasLeakageResult.has_leakage !== 'unknown') return false;
                        break;
                }
            }
            
            // 关键词搜索
            if (keyword) {
                const searchText = [
                    item.question || '',
                    item.answer || '',
                    item.reasoning_path || '',
                    (item.domain_tags || []).join(' ')
                ].join(' ').toLowerCase();
                
                if (!searchText.includes(keyword)) return false;
            }
            
            // 筛选有改动的数据
            if (showModifiedOnly) {
                const hasModifications = this.checkItemModified(item);
                if (!hasModifications) return false;
            }
            
            return true;
        });
        
        this.currentPage = 1;
        this.displayData();
    }
    
    clearFilters() {
        document.getElementById('questionLangFilter').value = '';
        document.getElementById('answerLangFilter').value = '';
        document.getElementById('keywordFilter').value = '';
        document.getElementById('showModifiedOnly').checked = false;
        document.getElementById('domainTagFilter').value = '';
        document.getElementById('leakageStatusFilter').value = '';
        
        this.filteredData = [...this.currentData];
        this.currentPage = 1;
        this.displayData();
    }
    
    async detectLanguages() {
        if (!this.currentData.length) return;
        
        const detectBtn = document.getElementById('detectLanguageBtn');
        const originalText = detectBtn.textContent;
        
        try {
            detectBtn.disabled = true;
            detectBtn.innerHTML = '<span class="loading-spinner"></span> 检测中...';
            
            const response = await fetch('/api/data_management/detect_languages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: this.currentFile,
                    data: this.currentData
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 更新本地数据
                result.data.forEach((item, index) => {
                    if (this.currentData[index]) {
                        this.currentData[index].question_language = item.question_language;
                        this.currentData[index].answer_language = item.answer_language;
                    }
                });
                
                this.filteredData = [...this.currentData];
                // 语言检测不算作内容修改，只有在自动保存模式下才标记为有变化
                if (this.autoSaveMode) {
                    this.hasChanges = true;
                    this.updateSaveButton();
                }
                this.displayData();
                
                this.showNotification('快速语言检测完成', 'success');
                
                // 自动保存
                await this.autoSaveIfEnabled();
            } else {
                throw new Error(result.error || '语言检测失败');
            }
        } catch (error) {
            console.error('语言检测失败:', error);
            this.showNotification(`语言检测失败: ${error.message}`, 'error');
        } finally {
            detectBtn.disabled = false;
            detectBtn.textContent = originalText;
        }
    }
    
    async detectLanguagesLLM() {
        if (!this.currentData.length) return;
        
        const detectBtn = document.getElementById('detectLanguageLLMBtn');
        const originalText = detectBtn.textContent;
        const qpsLimit = parseInt(document.getElementById('llmQpsLimit').value) || 2;
        const intervalMs = Math.ceil(1000 / qpsLimit); // 转换为毫秒间隔
        const detectSelectedOnly = document.getElementById('detectSelectedOnly').checked;
        
        // 确定要检测的数据
        let dataToDetect;
        if (detectSelectedOnly) {
            if (this.selectedItems.size === 0) {
                this.showNotification('请先选择要检测的数据项', 'warning');
                return;
            }
            dataToDetect = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        } else {
            dataToDetect = this.currentData;
        }
        
        try {
            detectBtn.disabled = true;
            const modeText = detectSelectedOnly ? '选中的' : '全部';
            detectBtn.innerHTML = `<span class="loading-spinner"></span> LLM检测${modeText}数据中...`;
            
            let successCount = 0;
            let errorCount = 0;
            let totalProcessed = 0;
            
            // 创建批次，每个批次的字符数不超过80000
            const batches = this.createLanguageDetectionBatches(dataToDetect, 80000);
            
            for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
                try {
                    const batch = batches[batchIndex];
                    
                    const response = await fetch('/api/data_management/detect_languages_llm', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            data: batch.items
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success && result.data.length > 0) {
                        // 更新数据
                        result.data.forEach((detectedItem, i) => {
                            if (detectSelectedOnly) {
                                // 更新选中项的数据
                                const selectedIndex = Array.from(this.selectedItems)[batch.indices[i]];
                                this.filteredData[selectedIndex].question_language = detectedItem.question_language;
                                this.filteredData[selectedIndex].answer_language = detectedItem.answer_language;
                                // 也要更新currentData中对应的项
                                const currentDataIndex = this.currentData.findIndex(item => 
                                    item === this.filteredData[selectedIndex]
                                );
                                if (currentDataIndex >= 0) {
                                    this.currentData[currentDataIndex].question_language = detectedItem.question_language;
                                    this.currentData[currentDataIndex].answer_language = detectedItem.answer_language;
                                }
                            } else {
                                // 更新全部数据
                                const originalIndex = batch.indices[i];
                                this.currentData[originalIndex].question_language = detectedItem.question_language;
                                this.currentData[originalIndex].answer_language = detectedItem.answer_language;
                            }
                        });
                        successCount += result.data.length;
                    } else {
                        errorCount += batch.items.length;
                    }
                    
                    totalProcessed += batch.items.length;
                    
                    // 更新进度显示
                    detectBtn.innerHTML = `<span class="loading-spinner"></span> LLM检测${modeText}数据中... (${totalProcessed}/${dataToDetect.length}) QPS:${qpsLimit}`;
                    
                    // QPS限制延迟
                    if (batchIndex < batches.length - 1) {
                        await new Promise(resolve => setTimeout(resolve, intervalMs));
                    }
                } catch (error) {
                    console.error(`检测批次${batchIndex + 1}失败:`, error);
                    errorCount += batches[batchIndex].items.length;
                    totalProcessed += batches[batchIndex].items.length;
                }
            }
            
            if (successCount > 0) {
                this.filteredData = [...this.currentData];
                // 语言检测不算作内容修改，只有在自动保存模式下才标记为有变化
                if (this.autoSaveMode) {
                    this.hasChanges = true;
                    this.updateSaveButton();
                }
                this.autoSaveIfEnabled();
                this.displayData();
                this.updateLanguageFilters(); // 重新更新语言筛选选项
                
                const targetText = detectSelectedOnly ? `选中的${this.selectedItems.size}个对象中的` : '全部';
                this.showNotification(`LLM检测完成: ${targetText}${successCount}个成功, ${errorCount}个失败 (共${batches.length}个批次, QPS:${qpsLimit})`, 'success');
            } else {
                this.showNotification('LLM语言检测失败', 'error');
            }
            
        } catch (error) {
            console.error('LLM语言检测错误:', error);
            this.showNotification('LLM语言检测时发生错误', 'error');
        } finally {
            detectBtn.disabled = false;
            detectBtn.textContent = originalText;
        }
    }
    
    createLanguageDetectionBatches(data, maxChars) {
        const batches = [];
        let currentBatch = { items: [], indices: [], totalChars: 0 };
        
        for (let i = 0; i < data.length; i++) {
            const item = data[i];
            const itemText = (item.question || '') + (item.answer || '');
            const itemChars = itemText.length;
            
            // 如果添加这个项目会超过限制，先保存当前批次
            if (currentBatch.items.length > 0 && currentBatch.totalChars + itemChars > maxChars) {
                batches.push(currentBatch);
                currentBatch = { items: [], indices: [], totalChars: 0 };
            }
            
            // 添加项目到当前批次
            currentBatch.items.push(item);
            currentBatch.indices.push(i);
            currentBatch.totalChars += itemChars;
            
            // 如果单个项目就超过限制，单独作为一个批次
            if (itemChars > maxChars) {
                batches.push(currentBatch);
                currentBatch = { items: [], indices: [], totalChars: 0 };
            }
        }
        
        // 添加最后一个批次
        if (currentBatch.items.length > 0) {
            batches.push(currentBatch);
        }
        
        return batches;
    }
    
    editItem(index) {
        const item = this.filteredData[index];
        if (!item) return;
        
        this.editingIndex = index;
        
        // 填充编辑表单
        document.getElementById('editQuestion').value = item.question || '';
        document.getElementById('editAnswer').value = item.answer || '';
        document.getElementById('editReasoningPath').value = item.reasoning_path || '';
        document.getElementById('editMappedReasoningPath').value = item.mapped_reasoning_path || item.reasoning_path || '';
        document.getElementById('editQuestionLang').value = item.question_language || 'unknown';
        document.getElementById('editAnswerLang').value = item.answer_language || 'unknown';
        
        // 显示编辑模态框
        document.getElementById('editModal').style.display = 'flex';
    }
    
    saveEdit() {
        if (this.editingIndex === -1) return;
        
        const item = this.filteredData[this.editingIndex];
        const originalIndex = this.currentData.findIndex(d => d === item);
        
        // 更新数据
        const updatedItem = {
            ...item,
            question: document.getElementById('editQuestion').value,
            answer: document.getElementById('editAnswer').value,
            reasoning_path: document.getElementById('editReasoningPath').value,
            mapped_reasoning_path: document.getElementById('editMappedReasoningPath').value,
            question_language: document.getElementById('editQuestionLang').value,
            answer_language: document.getElementById('editAnswerLang').value
        };
        
        this.filteredData[this.editingIndex] = updatedItem;
        if (originalIndex !== -1) {
            this.currentData[originalIndex] = updatedItem;
        }
        
        item._user_modified = true;  // 标记为用户修改
        this.hasChanges = true;
        this.displayData();
        this.updateSaveButton();
        this.closeEditModal();
        
        this.showNotification('数据已更新', 'success');
        
        // 自动保存
        this.autoSaveIfEnabled();
    }
    
    closeEditModal() {
        document.getElementById('editModal').style.display = 'none';
        this.editingIndex = -1;
        
        // 重置实体映射相关状态
        this.resetEntityMapping();
    }
    
    resetEntityMapping() {
        this.extractedEntities = [];
        this.selectedEntities = [];
        this.entityMapping = {};
        
        // 隐藏相关UI元素
        document.getElementById('entitiesList').style.display = 'none';
        document.getElementById('entityMappingArea').style.display = 'none';
        document.getElementById('showEntityMappingBtn').style.display = 'none';
        document.getElementById('previewReplacementBtn').style.display = 'none';
    }
    
    async extractEntities() {
        const reasoningPath = document.getElementById('editMappedReasoningPath').value;
        
        if (!reasoningPath.trim()) {
            this.showNotification('推理路径不能为空', 'warning');
            return;
        }
        
        const extractBtn = document.getElementById('extractEntitiesBtn');
        const originalText = extractBtn.textContent;
        
        try {
            extractBtn.disabled = true;
            extractBtn.textContent = '🔍 提取中...';
            
            const response = await fetch('/api/data_management/extract_entities', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    reasoning_path: reasoningPath
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.extractedEntities = result.entities;
                this.displayEntities();
                
                if (this.extractedEntities.length > 0) {
                    document.getElementById('showEntityMappingBtn').style.display = 'inline-block';
                    this.showNotification(`提取到 ${this.extractedEntities.length} 个实体，请点击实体进行选择`, 'success');
                } else {
                    this.showNotification('未找到可提取的实体', 'info');
                }
            } else {
                throw new Error(result.error || '提取实体失败');
            }
        } catch (error) {
            console.error('提取实体失败:', error);
            this.showNotification(`提取实体失败: ${error.message}`, 'error');
        } finally {
            extractBtn.disabled = false;
            extractBtn.textContent = originalText;
        }
    }
    
    displayEntities() {
        const entitiesList = document.getElementById('entitiesList');
        const entitiesContainer = document.getElementById('entitiesContainer');
        
        if (this.extractedEntities.length === 0) {
            entitiesList.style.display = 'none';
            return;
        }
        
        entitiesContainer.innerHTML = this.extractedEntities.map((entity, index) => `
            <div class="entity-tag" data-index="${index}" onclick="window.dataManager.toggleEntitySelection(${index})">
                <span class="entity-type-badge entity-type-${entity.type}">${this.getEntityTypeLabel(entity.type)}</span>
                <span>${this.escapeHtml(entity.entity)}</span>
                <span class="entity-count">${entity.count}</span>
            </div>
        `).join('');
        
        entitiesList.style.display = 'block';
    }
    
    getEntityTypeLabel(type) {
        const labels = {
            'name': '名称',
            'proper_name': '专名',
            'year': '年份',
            'other': '其他'
        };
        return labels[type] || '未知';
    }
    
    toggleEntitySelection(index) {
        const entityTag = document.querySelector(`[data-index="${index}"]`);
        const isSelected = entityTag.classList.contains('selected');
        
        if (isSelected) {
            entityTag.classList.remove('selected');
            this.selectedEntities = this.selectedEntities.filter(i => i !== index);
        } else {
            entityTag.classList.add('selected');
            this.selectedEntities.push(index);
        }
        
        // 更新按钮状态
        if (this.selectedEntities.length > 0) {
            document.getElementById('previewReplacementBtn').style.display = 'inline-block';
        } else {
            document.getElementById('previewReplacementBtn').style.display = 'none';
        }
    }
    
    showEntityMapping() {
        if (this.selectedEntities.length === 0) {
            this.showNotification('请先点击选择要映射的实体（点击实体标签变蓝色表示选中）', 'warning');
            return;
        }
        
        const mappingContainer = document.getElementById('mappingContainer');
        
        mappingContainer.innerHTML = this.selectedEntities.map(index => {
            const entity = this.extractedEntities[index];
            return `
                <div class="mapping-item">
                    <div class="mapping-original">${this.escapeHtml(entity.entity)}</div>
                    <div class="mapping-arrow">→</div>
                    <div class="mapping-replacement">
                        <input type="text" 
                               value="${this.escapeHtml(entity.entity)}" 
                               data-original="${this.escapeHtml(entity.entity)}"
                               placeholder="输入替换文本..."
                               onchange="window.dataManager.updateEntityMapping(this)">
                    </div>
                </div>
            `;
        }).join('');
        
        document.getElementById('entityMappingArea').style.display = 'block';
    }
    
    updateEntityMapping(input) {
        const original = input.dataset.original;
        const replacement = input.value;
        
        if (replacement.trim()) {
            this.entityMapping[original] = replacement;
        } else {
            delete this.entityMapping[original];
        }
    }
    
    async previewReplacement() {
        const reasoningPath = document.getElementById('editMappedReasoningPath').value;
        
        if (Object.keys(this.entityMapping).length === 0) {
            this.showNotification('请先配置实体映射', 'warning');
            return;
        }
        
        try {
            const response = await fetch('/api/data_management/replace_entities', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    reasoning_path: reasoningPath,
                    entity_mapping: this.entityMapping
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 创建预览窗口
                this.showReplacementPreview(reasoningPath, result.new_reasoning_path, result.replacements_made);
            } else {
                throw new Error(result.error || '预览替换失败');
            }
        } catch (error) {
            console.error('预览替换失败:', error);
            this.showNotification(`预览替换失败: ${error.message}`, 'error');
        }
    }
    
    showReplacementPreview(original, replaced, replacementsCount) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        
        // 创建模态框结构
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        modalContent.style.maxWidth = '1000px';
        
        const modalHeader = document.createElement('div');
        modalHeader.className = 'modal-header';
        modalHeader.innerHTML = `
            <h3>🔍 替换预览</h3>
            <button class="modal-close">&times;</button>
        `;
        
        const modalBody = document.createElement('div');
        modalBody.className = 'modal-body';
        modalBody.innerHTML = `
            <p><strong>替换了 ${replacementsCount} 处实体</strong></p>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px;">
                <div>
                    <h4>原始内容:</h4>
                    <pre style="background: #f5f5f5; padding: 12px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${this.escapeHtml(original)}</pre>
                </div>
                <div>
                    <h4>替换后:</h4>
                    <pre style="background: #e8f5e8; padding: 12px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${this.escapeHtml(replaced)}</pre>
                </div>
            </div>
        `;
        
        const modalFooter = document.createElement('div');
        modalFooter.className = 'modal-footer';
        
        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'btn btn-primary';
        confirmBtn.textContent = '✅ 确认替换';
        confirmBtn.onclick = () => {
            this.confirmReplacement(replaced);
            modal.remove();
        };
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-secondary';
        cancelBtn.textContent = '❌ 取消';
        cancelBtn.onclick = () => modal.remove();
        
        modalFooter.appendChild(confirmBtn);
        modalFooter.appendChild(cancelBtn);
        
        // 关闭按钮事件
        modalHeader.querySelector('.modal-close').onclick = () => modal.remove();
        
        // 组装模态框
        modalContent.appendChild(modalHeader);
        modalContent.appendChild(modalBody);
        modalContent.appendChild(modalFooter);
        modal.appendChild(modalContent);
        
        document.body.appendChild(modal);
    }
    
    confirmReplacement(newReasoningPath) {
        document.getElementById('editMappedReasoningPath').value = newReasoningPath;
        this.showNotification('映射后推理路径已更新', 'success');
    }
    
    async applyReplacement() {
        try {
            await this.previewReplacement();
        } catch (error) {
            console.error('应用替换失败:', error);
            this.showNotification(`应用替换失败: ${error.message}`, 'error');
        }
    }
    
    copyFromOriginal() {
        const originalPath = document.getElementById('editReasoningPath').value;
        document.getElementById('editMappedReasoningPath').value = originalPath;
        this.showNotification('已复制原始推理路径', 'success');
    }
    
    deleteItem(index) {
        const item = this.filteredData[index];
        if (!item) return;
        
        this.editingIndex = index;
        
        // 显示删除预览
        document.getElementById('deletePreviewQuestion').textContent = 
            (item.question || '').substring(0, 100) + (item.question && item.question.length > 100 ? '...' : '');
        
        // 显示删除确认模态框
        document.getElementById('deleteModal').style.display = 'flex';
    }
    
    confirmDelete() {
        if (this.editingIndex === -1) return;
        
        const item = this.filteredData[this.editingIndex];
        const originalIndex = this.currentData.findIndex(d => d === item);
        
        // 从两个数组中删除
        this.filteredData.splice(this.editingIndex, 1);
        if (originalIndex !== -1) {
            this.currentData.splice(originalIndex, 1);
        }
        
        this.hasChanges = true;
        this.displayData();
        this.updateSaveButton();
        this.closeDeleteModal();
        
        this.showNotification('数据已删除', 'success');
        
        // 自动保存
        this.autoSaveIfEnabled();
    }
    
    closeDeleteModal() {
        document.getElementById('deleteModal').style.display = 'none';
        this.editingIndex = -1;
    }
    
    async saveChanges() {
        if (!this.hasChanges || !this.currentFile) return;
        
        const saveBtn = document.getElementById('saveChangesBtn');
        const originalText = saveBtn.textContent;
        
        try {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<span class="loading-spinner"></span> 保存中...';
            
            const response = await fetch('/api/data_management/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: this.currentFile,
                    data: this.currentData
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.hasChanges = false;
                this.updateSaveButton();
                
                // 根据保存模式显示不同的提示
                if (this.autoSaveMode) {
                    this.showNotification('自动保存成功', 'success');
                } else {
                    this.showNotification('手动保存成功', 'success');
                }
            } else {
                throw new Error(result.error || '保存失败');
            }
        } catch (error) {
            console.error('保存失败:', error);
            this.showNotification(`保存失败: ${error.message}`, 'error');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = originalText;
        }
    }
    
    onAutoSaveModeChange() {
        this.autoSaveMode = document.getElementById('autoSaveMode').checked;
        this.updateSaveButton();
        
        if (this.autoSaveMode) {
            this.showNotification('已启用自动保存模式', 'info');
        } else {
            this.showNotification('已切换到手动保存模式', 'info');
        }
    }
    
    async autoSaveIfEnabled() {
        if (this.autoSaveMode && this.hasChanges && this.currentFile) {
            try {
                await this.saveChanges();
            } catch (error) {
                console.error('自动保存失败:', error);
                // 自动保存失败时不显示错误，避免干扰用户操作
            }
        }
    }
    
    updateSaveButton() {
        const saveBtn = document.getElementById('saveChangesBtn');
        const saveAsBtn = document.getElementById('saveAsBtn');
        const saveStatus = document.getElementById('saveStatus');
        
        // 另存为按钮：只要有数据就可以使用
        if (saveAsBtn) {
            saveAsBtn.disabled = !this.currentData.length;
        }
        
        if (this.autoSaveMode) {
            saveBtn.style.display = 'none';
            if (saveStatus) {
                saveStatus.className = 'save-status auto-save';
                saveStatus.textContent = '🔄 自动保存';
            }
        } else {
            saveBtn.style.display = 'inline-block';
            saveBtn.disabled = !this.hasChanges;
            saveBtn.textContent = this.hasChanges ? '💾 保存修改' : '💾 已保存';
            
            if (saveStatus) {
                if (this.hasChanges) {
                    saveStatus.className = 'save-status has-changes';
                    saveStatus.textContent = '⚠️ 有未保存的修改';
                } else {
                    saveStatus.className = 'save-status saved';
                    saveStatus.textContent = '✅ 已保存';
                }
            }
        }
    }
    
    updateDataStats() {
        document.getElementById('displayedCount').textContent = this.filteredData.length;
        document.getElementById('totalCount').textContent = this.currentData.length;
        
        // 计算修改统计
        const modifiedCount = this.currentData.filter(item => this.checkItemModified(item)).length;
        const modifiedCountEl = document.getElementById('modifiedCount');
        if (modifiedCountEl) {
            modifiedCountEl.textContent = modifiedCount;
        }
    }
    
    updatePagination() {
        const totalPages = Math.ceil(this.filteredData.length / this.pageSize);
        const pagination = document.getElementById('pagination');
        
        if (totalPages <= 1) {
            pagination.style.display = 'none';
            return;
        }
        
        pagination.style.display = 'flex';
        pagination.innerHTML = this.createPaginationHTML(totalPages);
        
        // 添加分页事件监听器
        pagination.querySelectorAll('.page-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (e.target.disabled) return;
                
                const action = e.target.dataset.action;
                if (action === 'prev') {
                    this.currentPage = Math.max(1, this.currentPage - 1);
                } else if (action === 'next') {
                    this.currentPage = Math.min(totalPages, this.currentPage + 1);
                } else {
                    this.currentPage = parseInt(action);
                }
                
                this.displayData();
            });
        });
    }
    
    createPaginationHTML(totalPages) {
        let html = `
            <button class="page-btn" data-action="prev" ${this.currentPage === 1 ? 'disabled' : ''}>
                ◀ 上一页
            </button>
        `;
        
        // 显示页码
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, this.currentPage + 2);
        
        if (startPage > 1) {
            html += `<button class="page-btn" data-action="1">1</button>`;
            if (startPage > 2) {
                html += `<span>...</span>`;
            }
        }
        
        for (let i = startPage; i <= endPage; i++) {
            html += `
                <button class="page-btn ${i === this.currentPage ? 'active' : ''}" data-action="${i}">
                    ${i}
                </button>
            `;
        }
        
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                html += `<span>...</span>`;
            }
            html += `<button class="page-btn" data-action="${totalPages}">${totalPages}</button>`;
        }
        
        html += `
            <button class="page-btn" data-action="next" ${this.currentPage === totalPages ? 'disabled' : ''}>
                下一页 ▶
            </button>
        `;
        
        return html;
    }
    
    getEmptyStateHTML() {
        return `
            <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <p>没有找到匹配的数据</p>
            </div>
        `;
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    showNotification(message, type = 'info') {
        // 创建通知元素
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 16px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 10000;
            animation: slideIn 0.3s ease;
            max-width: 300px;
        `;
        
        const colors = {
            success: '#10b981',
            error: '#ef4444',
            warning: '#f59e0b',
            info: '#3b82f6'
        };
        
        notification.style.backgroundColor = colors[type] || colors.info;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // 自动移除
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
        
        // 添加动画样式
        if (!document.getElementById('notification-styles')) {
            const style = document.createElement('style');
            style.id = 'notification-styles';
            style.textContent = `
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    // ========== 推理路径预览替换功能 ==========
    
    toggleReasoningPreview(index) {
        const item = this.filteredData[index];
        const originalDiv = document.getElementById(`reasoning-original-${index}`);
        const replacedDiv = document.getElementById(`reasoning-replaced-${index}`);
        const button = document.querySelector(`[onclick="window.dataManager.toggleReasoningPreview(${index})"]`);
        
        if (!item.entity_mapping || Object.keys(item.entity_mapping).length === 0) {
            this.showNotification('该项目没有entity_mapping映射关系', 'warning');
            return;
        }
        
        // 切换显示状态
        if (originalDiv.style.display === 'none') {
            // 当前显示替换版本，切换回原始版本
            originalDiv.style.display = 'block';
            replacedDiv.style.display = 'none';
            button.textContent = '🔄 预览替换';
            button.classList.remove('btn-warning');
            button.classList.add('btn-secondary');
        } else {
            // 当前显示原始版本，切换到替换版本
            originalDiv.style.display = 'none';
            replacedDiv.style.display = 'block';
            button.textContent = '↩️ 显示原始';
            button.classList.remove('btn-secondary');
            button.classList.add('btn-warning');
        }
    }
    
    applyReplacementToItem(index) {
        const item = this.filteredData[index];
        
        if (!item.entity_mapping || Object.keys(item.entity_mapping).length === 0) {
            this.showNotification('该项目没有entity_mapping映射关系', 'warning');
            return;
        }
        
        const original = item.reasoning_path || '';
        const replaced = this.replaceEntitiesInText(original, item.entity_mapping);
        
        if (replaced !== original) {
            // 应用替换到mapped_reasoning_path
            this.filteredData[index].mapped_reasoning_path = replaced;
            this.filteredData[index]._user_modified = true;  // 标记为用户修改
            
            this.hasChanges = true;
            this.updateSaveButton();
            this.autoSaveIfEnabled();
            
            this.showNotification('已应用实体替换结果', 'success');
            this.displayData(); // 刷新显示
        } else {
            this.showNotification('没有需要替换的内容', 'info');
        }
    }
    
    previewAllReasoningPaths() {
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = Math.min(startIndex + this.pageSize, this.filteredData.length);
        let previewedCount = 0;
        
        for (let i = startIndex; i < endIndex; i++) {
            const item = this.filteredData[i];
            if (item.entity_mapping && Object.keys(item.entity_mapping).length > 0) {
                const originalDiv = document.getElementById(`reasoning-original-${i}`);
                const replacedDiv = document.getElementById(`reasoning-replaced-${i}`);
                const button = document.querySelector(`[onclick="window.dataManager.toggleReasoningPreview(${i})"]`);
                
                if (originalDiv && replacedDiv && button && originalDiv.style.display !== 'none') {
                    originalDiv.style.display = 'none';
                    replacedDiv.style.display = 'block';
                    button.textContent = '↩️ 显示原始';
                    button.classList.remove('btn-secondary');
                    button.classList.add('btn-warning');
                    previewedCount++;
                }
            }
        }
        
        if (previewedCount > 0) {
            document.getElementById('previewAllBtn').style.display = 'none';
            document.getElementById('hideAllPreviewBtn').style.display = 'inline-block';
            this.showNotification(`已预览 ${previewedCount} 个推理路径的替换结果`, 'success');
        } else {
            this.showNotification('当前页面没有可预览的推理路径', 'info');
        }
    }
    
    hideAllReasoningPreviews() {
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = Math.min(startIndex + this.pageSize, this.filteredData.length);
        let hiddenCount = 0;
        
        for (let i = startIndex; i < endIndex; i++) {
            const originalDiv = document.getElementById(`reasoning-original-${i}`);
            const replacedDiv = document.getElementById(`reasoning-replaced-${i}`);
            const button = document.querySelector(`[onclick="window.dataManager.toggleReasoningPreview(${i})"]`);
            
            if (originalDiv && replacedDiv && button && originalDiv.style.display === 'none') {
                originalDiv.style.display = 'block';
                replacedDiv.style.display = 'none';
                button.textContent = '🔄 预览替换';
                button.classList.remove('btn-warning');
                button.classList.add('btn-secondary');
                hiddenCount++;
            }
        }
        
        if (hiddenCount > 0) {
            document.getElementById('previewAllBtn').style.display = 'inline-block';
            document.getElementById('hideAllPreviewBtn').style.display = 'none';
            this.showNotification(`已隐藏 ${hiddenCount} 个推理路径的预览`, 'success');
        }
    }
    
    // ========== 主页面实体替换功能 ==========
    
    selectAll() {
        // 选择当前页面所有数据项
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = Math.min(startIndex + this.pageSize, this.filteredData.length);
        
        for (let i = startIndex; i < endIndex; i++) {
            this.selectedItems.add(i);
        }
        
        this.updateSelectionStatus();
        this.displayData(); // 重新渲染选中状态
    }
    
    selectAllData() {
        // 选择所有筛选后的数据
        for (let i = 0; i < this.filteredData.length; i++) {
            this.selectedItems.add(i);
        }
        
        this.updateSelectionStatus();
        this.displayData(); // 重新渲染选中状态
        
        // 显示通知
        this.showNotification(`已选择全部 ${this.filteredData.length} 条数据`, 'success');
    }
    
    clearSelection() {
        this.selectedItems.clear();
        this.updateSelectionStatus();
        this.displayData(); // 重新渲染
    }
    
    onPageSizeChange() {
        const newPageSize = parseInt(document.getElementById('pageSizeSelect').value);
        this.pageSize = newPageSize;
        this.currentPage = 1; // 重置到第一页
        this.selectedItems.clear(); // 清除选择
        this.updateSelectionStatus();
        this.displayData();
    }
    
    toggleItemSelection(index) {
        if (this.selectedItems.has(index)) {
            this.selectedItems.delete(index);
        } else {
            this.selectedItems.add(index);
        }
        
        this.updateSelectionStatus();
        this.displayData(); // 重新渲染选中状态
    }
    
    updateSelectionStatus() {
        const count = this.selectedItems.size;
        const totalCount = this.filteredData.length;
        const statusEl = document.getElementById('selectionStatus');
        const controlsEl = document.getElementById('replacementControls');
        
        if (count === 0) {
            statusEl.textContent = `已选择 0 个对象`;
        } else if (count === totalCount) {
            statusEl.textContent = `已选择全部 ${count} 个对象`;
        } else {
            statusEl.textContent = `已选择 ${count} / ${totalCount} 个对象`;
        }
        
        if (count > 0) {
            controlsEl.style.display = 'flex';
        } else {
            controlsEl.style.display = 'none';
        }
    }
    
    previewEntityReplacement() {
        if (this.selectedItems.size === 0) {
            this.showNotification('请先选择要替换的数据对象', 'warning');
            return;
        }
        
        // 为每个选中的对象显示替换预览
        const previews = [];
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        let validItemsCount = 0;
        
        selectedData.forEach((item, i) => {
            const dataIndex = Array.from(this.selectedItems)[i];
            const original = item.reasoning_path || '';
            const entityMapping = item.entity_mapping || {};
            
            // 检查是否有有效的entity_mapping
            if (Object.keys(entityMapping).length === 0) {
                return; // 跳过没有entity_mapping的项目
            }
            
            const replaced = this.replaceEntitiesInText(original, entityMapping);
            const replacements = Object.keys(entityMapping).filter(k => original.includes(k)).length;
            
            previews.push({
                index: dataIndex,
                original,
                replaced,
                replacements,
                entityMapping
            });
            validItemsCount++;
        });
        
        if (validItemsCount === 0) {
            this.showNotification('选中的对象中没有找到有效的entity_mapping字段', 'warning');
            return;
        }
        
        this.showEntityReplacementPreview(previews);
    }
    
    showEntityReplacementPreview(previews) {
        const modal = document.createElement('div');
        modal.className = 'modal';
        
        const modalContent = document.createElement('div');
        modalContent.className = 'modal-content';
        modalContent.style.maxWidth = '1200px';
        
        const modalHeader = document.createElement('div');
        modalHeader.className = 'modal-header';
        modalHeader.innerHTML = `
            <h3>🔍 实体替换预览</h3>
            <button class="modal-close">&times;</button>
        `;
        
        const modalBody = document.createElement('div');
        modalBody.className = 'modal-body';
        modalBody.innerHTML = `
            <p><strong>将对 ${previews.length} 个对象的reasoning_path进行实体替换</strong></p>
            <div class="preview-tabs">
                ${previews.map((preview, index) => `
                    <div class="preview-tab ${index === 0 ? 'active' : ''}" onclick="window.dataManager.showPreviewTab(${index})">
                        对象 #${preview.index + 1} (${preview.replacements}处替换)
                    </div>
                `).join('')}
            </div>
            <div class="preview-content">
                ${previews.map((preview, index) => `
                    <div class="preview-item ${index === 0 ? 'active' : ''}" id="preview-${index}">
                        <div class="entity-mapping-info" style="margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 8px;">
                            <h6>使用的entity_mapping:</h6>
                            <pre style="font-size: 0.9rem; margin: 8px 0;">${this.escapeHtml(JSON.stringify(preview.entityMapping, null, 2))}</pre>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                            <div>
                                <h5>原始reasoning_path:</h5>
                                <pre style="background: #f5f5f5; padding: 12px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${this.escapeHtml(preview.original)}</pre>
                            </div>
                            <div>
                                <h5>替换后的mapped_reasoning_path:</h5>
                                <pre style="background: #e8f5e8; padding: 12px; border-radius: 8px; white-space: pre-wrap; max-height: 400px; overflow-y: auto;">${this.escapeHtml(preview.replaced)}</pre>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        
        const modalFooter = document.createElement('div');
        modalFooter.className = 'modal-footer';
        
        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'btn btn-primary';
        confirmBtn.textContent = '✅ 确认应用替换';
        confirmBtn.onclick = () => {
            this.confirmEntityReplacement(previews);
            modal.remove();
        };
        
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-secondary';
        cancelBtn.textContent = '❌ 取消';
        cancelBtn.onclick = () => modal.remove();
        
        modalFooter.appendChild(confirmBtn);
        modalFooter.appendChild(cancelBtn);
        
        // 关闭按钮事件
        modalHeader.querySelector('.modal-close').onclick = () => modal.remove();
        
        // 组装模态框
        modalContent.appendChild(modalHeader);
        modalContent.appendChild(modalBody);
        modalContent.appendChild(modalFooter);
        modal.appendChild(modalContent);
        
        document.body.appendChild(modal);
    }
    
    showPreviewTab(tabIndex) {
        // 切换标签页
        document.querySelectorAll('.preview-tab').forEach((tab, index) => {
            tab.classList.toggle('active', index === tabIndex);
        });
        document.querySelectorAll('.preview-item').forEach((item, index) => {
            item.classList.toggle('active', index === tabIndex);
        });
    }
    
    confirmEntityReplacement(previews) {
        // 应用替换到选中的对象
        previews.forEach(preview => {
            const dataIndex = preview.index;
            this.filteredData[dataIndex].mapped_reasoning_path = preview.replaced;
        });
        
        this.hasChanges = true;
        this.updateSaveButton();
        this.autoSaveIfEnabled();
        
        this.showNotification(`成功替换 ${previews.length} 个对象的实体`, 'success');
        this.displayData(); // 刷新显示
    }
    
    applyEntityReplacement() {
        if (this.selectedItems.size === 0) {
            this.showNotification('请先选择要替换的数据对象', 'warning');
            return;
        }
        
        // 直接应用替换，不显示预览
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        let replacedCount = 0;
        let skippedCount = 0;
        
        selectedData.forEach((item, i) => {
            const dataIndex = Array.from(this.selectedItems)[i];
            const original = item.reasoning_path || '';
            const entityMapping = item.entity_mapping || {};
            
            // 检查是否有有效的entity_mapping
            if (Object.keys(entityMapping).length === 0) {
                skippedCount++;
                return;
            }
            
            const replaced = this.replaceEntitiesInText(original, entityMapping);
            
            if (replaced !== original) {
                this.filteredData[dataIndex].mapped_reasoning_path = replaced;
                this.filteredData[dataIndex]._user_modified = true;  // 标记为用户修改
                replacedCount++;
            }
        });
        
        if (replacedCount > 0) {
            this.hasChanges = true;
            this.updateSaveButton();
            this.autoSaveIfEnabled();
            
            let message = `成功为 ${replacedCount} 个对象应用实体替换`;
            if (skippedCount > 0) {
                message += `，跳过 ${skippedCount} 个没有entity_mapping的对象`;
            }
            this.showNotification(message, 'success');
            this.displayData();
        } else {
            if (skippedCount > 0) {
                this.showNotification(`跳过 ${skippedCount} 个没有entity_mapping的对象，没有执行替换`, 'info');
            } else {
                this.showNotification('没有需要替换的内容', 'info');
            }
        }
    }
    
    replaceEntitiesInText(text, entityMapping) {
        let result = text;
        
        // 按实体长度排序，长的先替换
        const sortedEntities = Object.keys(entityMapping).sort((a, b) => b.length - a.length);
        
        for (const entity of sortedEntities) {
            const replacement = String(entityMapping[entity]); // 确保替换值是字符串
            const entityStr = String(entity); // 确保实体名也是字符串
            
            if (entityStr !== replacement && replacement) {
                result = result.split(entityStr).join(replacement);
            }
        }
        
        return result;
    }
    
    async updateLanguageFilters() {
        if (!this.currentData.length) return;
        
        try {
            const response = await fetch('/api/data_management/get_languages', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    data: this.currentData
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.updateLanguageSelect('questionLangFilter', result.question_languages);
                this.updateLanguageSelect('answerLangFilter', result.answer_languages);
            } else {
                console.error('获取语言列表失败:', result.error);
            }
        } catch (error) {
            console.error('获取语言列表错误:', error);
        }
    }
    
    updateLanguageSelect(selectId, languages) {
        const select = document.getElementById(selectId);
        const currentValue = select.value;
        
        // 清空现有选项
        select.innerHTML = '<option value="">全部</option>';
        
        // 添加语言选项
        languages.forEach(lang => {
            const option = document.createElement('option');
            option.value = lang.code;
            option.textContent = lang.name;
            select.appendChild(option);
        });
        
        // 尝试恢复之前的选择
        if (currentValue && [...select.options].some(opt => opt.value === currentValue)) {
            select.value = currentValue;
        }
    }
    
    // ========== 另存为功能 ==========
    
    showSaveAsModal() {
        if (!this.currentData.length) {
            this.showNotification('没有数据可以保存', 'warning');
            return;
        }
        
        // 更新数据统计
        this.updateSaveAsStats();
        
        // 生成默认文件名
        const now = new Date();
        const timestamp = now.toISOString().slice(0, 19).replace(/[-:]/g, '').replace('T', '_');
        const defaultName = `export_${timestamp}`;
        document.getElementById('newFileName').value = defaultName;
        
        // 更新预览
        this.updateSaveAsPreview();
        
        // 显示模态框
        document.getElementById('saveAsModal').style.display = 'block';
    }
    
    closeSaveAsModal() {
        document.getElementById('saveAsModal').style.display = 'none';
        document.getElementById('newFileName').value = '';
    }
    
    updateSaveAsStats() {
        document.getElementById('filteredCount').textContent = this.filteredData.length;
        document.getElementById('totalCount').textContent = this.currentData.length;
        document.getElementById('selectedCount').textContent = this.selectedItems.size;
    }
    
    updateSaveAsPreview() {
        const fileName = document.getElementById('newFileName').value.trim();
        const saveScope = document.querySelector('input[name="saveScope"]:checked').value;
        
        // 更新文件名预览
        document.getElementById('previewFileName').textContent = fileName ? `${fileName}.jsonl` : '未设置';
        
        // 计算记录数
        let recordCount = 0;
        switch (saveScope) {
            case 'filtered':
                recordCount = this.filteredData.length;
                break;
            case 'all':
                recordCount = this.currentData.length;
                break;
            case 'selected':
                recordCount = this.selectedItems.size;
                break;
        }
        
        document.getElementById('previewRecordCount').textContent = recordCount;
        
        // 更新确认按钮状态
        const confirmBtn = document.getElementById('confirmSaveAsBtn');
        confirmBtn.disabled = !fileName || recordCount === 0;
    }
    
    async confirmSaveAs() {
        const fileName = document.getElementById('newFileName').value.trim();
        const saveScope = document.querySelector('input[name="saveScope"]:checked').value;
        
        if (!fileName) {
            this.showNotification('请输入文件名', 'warning');
            return;
        }
        
        // 准备要保存的数据
        let dataToSave = [];
        switch (saveScope) {
            case 'filtered':
                dataToSave = this.filteredData;
                break;
            case 'all':
                dataToSave = this.currentData;
                break;
            case 'selected':
                if (this.selectedItems.size === 0) {
                    this.showNotification('没有选中的数据', 'warning');
                    return;
                }
                dataToSave = Array.from(this.selectedItems).map(index => this.filteredData[index]);
                break;
        }
        
        if (dataToSave.length === 0) {
            this.showNotification('没有数据可以保存', 'warning');
            return;
        }
        
        const confirmBtn = document.getElementById('confirmSaveAsBtn');
        const originalText = confirmBtn.textContent;
        
        try {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<span class="loading-spinner"></span> 保存中...';
            
            const response = await fetch('/api/data_management/save_as', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: `${fileName}.jsonl`,
                    data: dataToSave,
                    scope: saveScope,
                    original_file: this.currentFile
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(`成功保存 ${dataToSave.length} 条数据到 ${fileName}.jsonl`, 'success');
                this.closeSaveAsModal();
            } else {
                throw new Error(result.error || '保存失败');
            }
            
        } catch (error) {
            console.error('另存为失败:', error);
            this.showNotification(`另存为失败: ${error.message}`, 'error');
        } finally {
            confirmBtn.disabled = false;
            confirmBtn.textContent = originalText;
        }
    }
    
    // ========== 检查数据改动 ==========
    
    checkItemModified(item) {
        // 检查是否有entity mapping替换结果
        const hasMappedReasoning = item.mapped_reasoning_path && 
                                  item.mapped_reasoning_path !== item.reasoning_path && 
                                  item.mapped_reasoning_path.trim() !== '';
        
        // 检查是否有用户修改标记
        const hasUserModifications = item._user_modified === true;
        
        return hasMappedReasoning || hasUserModifications;
    }
    

    
    // ========== 反向替换功能 ==========
    
    async reverseReplaceEntities() {
        const selectedIndices = Array.from(this.selectedItems);
        
        if (selectedIndices.length === 0) {
            this.showNotification('请先选择要反向替换的数据', 'warning');
            return;
        }
        
        const btn = document.getElementById('reverseReplaceBtn');
        const originalText = btn.textContent;
        
        try {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span> 反向替换中...';
            
            let processedCount = 0;
            let skippedCount = 0;
            
            for (const index of selectedIndices) {
                const item = this.filteredData[index];
                if (!item) continue;
                
                const result = this.performReverseReplacement(item);
                if (result.processed) {
                    processedCount++;
                    this.hasChanges = true;
                } else {
                    skippedCount++;
                }
            }
            
            if (processedCount > 0) {
                this.showNotification(
                    `成功反向替换 ${processedCount} 条数据${skippedCount > 0 ? `，跳过 ${skippedCount} 条` : ''}`, 
                    'success'
                );
                this.displayData(); // 刷新显示
                this.updateSaveButton();
                
                if (this.autoSaveMode) {
                    await this.saveData();
                }
            } else {
                this.showNotification('没有数据需要反向替换', 'warning');
            }
            
        } catch (error) {
            console.error('反向替换失败:', error);
            this.showNotification(`反向替换失败: ${error.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
    
    performReverseReplacement(item) {
        try {
            if (!item.entity_mapping || typeof item.entity_mapping !== 'object') {
                return { processed: false, reason: '无entity_mapping' };
            }
            
            const originalReasoning = item.reasoning_path || '';
            let newReasoning = originalReasoning;
            const mapping = item.entity_mapping;
            let hasChanges = false;
            
            // 反向替换：将value替换为key
            for (const [key, value] of Object.entries(mapping)) {
                try {
                    // 确保key和value都是字符串
                    const keyStr = String(key);
                    const valueStr = String(value);
                    
                    // 跳过空值或相同的key-value对
                    if (!valueStr || !keyStr || keyStr === valueStr) {
                        continue;
                    }
                    
                    if (newReasoning.includes(valueStr)) {
                        // 使用全局替换
                        const regex = new RegExp(this.escapeRegExp(valueStr), 'g');
                        newReasoning = newReasoning.replace(regex, keyStr);
                        hasChanges = true;
                    }
                } catch (error) {
                    console.warn(`反向替换处理映射 ${key}:${value} 时出错:`, error);
                    continue;
                }
            }
            
            if (hasChanges) {
                item.reasoning_path = newReasoning;
                // 清空mapped_reasoning_path，因为已经反向替换回原始形式
                item.mapped_reasoning_path = '';
                item._user_modified = true;  // 标记为用户修改
                return { processed: true };
            }
            
            return { processed: false, reason: '无需替换' };
        } catch (error) {
            console.error('执行反向替换时出错:', error);
            return { processed: false, reason: `执行失败: ${error.message}` };
        }
    }
    
    escapeRegExp(string) {
        const str = String(string); // 确保输入是字符串
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    // ========== 调试辅助功能 ==========
    
    clearAllModificationFlags() {
        // 清除所有修改标记（用于调试）
        this.currentData.forEach(item => {
            delete item._user_modified;
            item.mapped_reasoning_path = '';
        });
        
        this.displayData();
        this.showNotification('已清除所有修改标记', 'info');
    }
    
    // ========== 文本清理功能 ==========
    
    showCustomCleanModal() {
        if (this.selectedItems.size === 0) {
            alert('请先选择要清理的数据项！');
            return;
        }
        
        // 清空之前的输入
        document.getElementById('customCleanText').value = '';
        document.getElementById('customCleanPreview').innerHTML = '';
        
        // 显示模态框
        document.getElementById('customCleanModal').style.display = 'flex';
    }
    
    closeCustomCleanModal() {
        document.getElementById('customCleanModal').style.display = 'none';
    }
    
    previewCustomClean() {
        const cleanText = document.getElementById('customCleanText').value.trim();
        const targetType = document.querySelector('input[name="cleanTarget"]:checked').value;
        
        if (!cleanText) {
            alert('请输入要清理的字符串！');
            return;
        }
        
        const cleanList = cleanText.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);
        
        if (cleanList.length === 0) {
            alert('请输入有效的清理字符串！');
            return;
        }
        
        // 获取选中的数据项
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        
        // 预览前3项
        const previewData = selectedData.slice(0, 3);
        const previewContainer = document.getElementById('customCleanPreview');
        
        if (previewData.length === 0) {
            previewContainer.innerHTML = '<div class="no-changes">没有选中的数据项</div>';
            return;
        }
        
        let html = '';
        let hasAnyChanges = false;
        
        previewData.forEach((item, index) => {
            let beforeText = '';
            let afterText = '';
            let hasChanges = false;
            
            if (targetType === 'question' || targetType === 'both') {
                beforeText = item.question || '';
                afterText = this.applyTextClean(beforeText, cleanList);
                if (beforeText !== afterText) hasChanges = true;
            }
            
            if (targetType === 'answer' || targetType === 'both') {
                const answerBefore = item.answer || '';
                const answerAfter = this.applyTextClean(answerBefore, cleanList);
                if (targetType === 'both') {
                    beforeText += (beforeText ? '\n\n[答案]\n' : '[答案]\n') + answerBefore;
                    afterText += (afterText ? '\n\n[答案]\n' : '[答案]\n') + answerAfter;
                } else {
                    beforeText = answerBefore;
                    afterText = answerAfter;
                }
                if (answerBefore !== answerAfter) hasChanges = true;
            }
            
            if (hasChanges) {
                hasAnyChanges = true;
                html += `
                    <div class="preview-item">
                        <div class="preview-before">
                            <div class="preview-label">清理前:</div>
                            <div class="preview-text">${this.escapeHtml(beforeText)}</div>
                        </div>
                        <div class="preview-after">
                            <div class="preview-label">清理后:</div>
                            <div class="preview-text">${this.escapeHtml(afterText)}</div>
                        </div>
                    </div>
                `;
            } else {
                html += `
                    <div class="preview-item">
                        <div class="no-changes">第${index + 1}项无需清理</div>
                    </div>
                `;
            }
        });
        
        if (!hasAnyChanges) {
            html = '<div class="no-changes">预览的数据项都无需清理</div>';
        }
        
        previewContainer.innerHTML = html;
    }
    
    applyCustomClean() {
        const cleanText = document.getElementById('customCleanText').value.trim();
        const targetType = document.querySelector('input[name="cleanTarget"]:checked').value;
        
        if (!cleanText) {
            alert('请输入要清理的字符串！');
            return;
        }
        
        const cleanList = cleanText.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);
        
        if (cleanList.length === 0) {
            alert('请输入有效的清理字符串！');
            return;
        }
        
        // 获取选中的数据项
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        let cleanedCount = 0;
        
        selectedData.forEach(item => {
            let hasChanges = false;
            
            if (targetType === 'question' || targetType === 'both') {
                const originalQuestion = item.question || '';
                const cleanedQuestion = this.applyTextClean(originalQuestion, cleanList);
                if (originalQuestion !== cleanedQuestion) {
                    item.question = cleanedQuestion;
                    hasChanges = true;
                }
            }
            
            if (targetType === 'answer' || targetType === 'both') {
                const originalAnswer = item.answer || '';
                const cleanedAnswer = this.applyTextClean(originalAnswer, cleanList);
                if (originalAnswer !== cleanedAnswer) {
                    item.answer = cleanedAnswer;
                    hasChanges = true;
                }
            }
            
            if (hasChanges) {
                item._user_modified = true;
                cleanedCount++;
            }
        });
        
        // 关闭模态框
        this.closeCustomCleanModal();
        
        // 更新显示
        this.displayData();
        this.updateDataStats();
        this.updateSaveButton();
        
        if (this.autoSaveMode) {
            this.autoSaveIfEnabled();
        }
        
        alert(`已清理 ${cleanedCount} 个数据项！`);
    }
    
    applyTextClean(text, cleanList) {
        let result = text;
        
        cleanList.forEach(cleanStr => {
            if (cleanStr) {
                // 全局替换为空字符串
                result = result.split(cleanStr).join('');
            }
        });
        
        // 清理多余的空白字符
        return result.replace(/\s+/g, ' ').trim();
    }
    
    cleanEntityKeys() {
        if (this.selectedItems.size === 0) {
            alert('请先选择要清理的数据项！');
            return;
        }
        
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        let cleanedCount = 0;
        
        selectedData.forEach(item => {
            if (!item.entity_mapping || typeof item.entity_mapping !== 'object') {
                return; // 跳过没有entity_mapping的项
            }
            
            let hasChanges = false;
            const entityKeys = Object.keys(item.entity_mapping);
            
            if (entityKeys.length === 0) {
                return; // 跳过空的entity_mapping
            }
            
            // 清理问题中的实体键
            if (item.question) {
                const originalQuestion = item.question;
                let cleanedQuestion = originalQuestion;
                
                entityKeys.forEach(key => {
                    if (key && cleanedQuestion.includes(key)) {
                        cleanedQuestion = cleanedQuestion.split(key).join('');
                        hasChanges = true;
                    }
                });
                
                if (hasChanges) {
                    // 清理多余的空白字符
                    item.question = cleanedQuestion.replace(/\s+/g, ' ').trim();
                }
            }
            
            if (hasChanges) {
                item._user_modified = true;
                cleanedCount++;
            }
        });
        
        // 更新显示
        this.displayData();
        this.updateDataStats();
        this.updateSaveButton();
        
        if (this.autoSaveMode) {
            this.autoSaveIfEnabled();
        }
        
        alert(`已清理 ${cleanedCount} 个数据项的实体键！`);
    }
    
    // ========== 领域标签识别功能 ==========
    
    async detectDomainTags() {
        // 功能已移除
        return;
        const tagSelectedOnly = document.getElementById('tagSelectedOnly').checked;
        let targetData;
        
        if (tagSelectedOnly) {
            if (this.selectedItems.size === 0) {
                alert('请先选择要标记的数据项！');
                return;
            }
            targetData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        } else {
            targetData = this.currentData;
        }
        
        if (!targetData || targetData.length === 0) {
            alert('没有可标记的数据！');
            return;
        }
        
        // 收集现有标签
        const existingTags = new Set();
        this.currentData.forEach(item => {
            if (item.domain_tags && Array.isArray(item.domain_tags)) {
                item.domain_tags.forEach(tag => {
                    if (tag && typeof tag === 'string') {
                        existingTags.add(tag.trim());
                    }
                });
            }
        });
        
        const detectBtn = document.getElementById('detectDomainTagsBtn');
        const originalText = detectBtn.textContent;
        
        try {
            detectBtn.disabled = true;
            detectBtn.textContent = '🤖 正在识别标签...';
            
            this.showNotification('开始领域标签识别...', 'info');
            
            const response = await fetch('/api/data_management/detect_domain_tags', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    data: targetData,
                    existing_tags: Array.from(existingTags)
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                const results = data.results;
                const allTags = data.all_tags || [];
                let taggedCount = 0;
                
                // 更新数据项的标签
                results.forEach(result => {
                    const index = result.index;
                    const domainTags = result.domain_tags || [];
                    
                    let targetItem;
                    if (tagSelectedOnly) {
                        // 找到在选中项中的对应项
                        const selectedArray = Array.from(this.selectedItems);
                        if (index < selectedArray.length) {
                            const filteredIndex = selectedArray[index];
                            targetItem = this.filteredData[filteredIndex];
                        }
                    } else {
                        // 直接使用全局索引
                        if (index < this.currentData.length) {
                            targetItem = this.currentData[index];
                        }
                    }
                    
                    if (targetItem && domainTags.length > 0) {
                        targetItem.domain_tags = domainTags;
                        targetItem._user_modified = true;
                        taggedCount++;
                    }
                });
                
                // 更新标签过滤器
                this.updateDomainTagFilter(allTags);
                
                // 更新显示
                this.displayData();
                this.updateDataStats();
                this.updateSaveButton();
                
                if (this.autoSaveMode) {
                    this.autoSaveIfEnabled();
                }
                
                this.showNotification(`领域标签识别完成！已标记 ${taggedCount} 个数据项，发现 ${allTags.length} 个标签`, 'success');
            } else {
                this.showNotification(`领域标签识别失败: ${data.error}`, 'error');
            }
            
        } catch (error) {
            console.error('领域标签识别失败:', error);
            this.showNotification(`领域标签识别失败: ${error.message}`, 'error');
        } finally {
            detectBtn.disabled = false;
            detectBtn.textContent = originalText;
        }
    }
    
    updateDomainTagFilter(allTags) {
        const filterSelect = document.getElementById('domainTagFilter');
        
        // 保存当前选中的值
        const currentValue = filterSelect.value;
        
        // 清空并重新填充选项
        filterSelect.innerHTML = '<option value="">全部标签</option>';
        
        allTags.forEach(tag => {
            const option = document.createElement('option');
            option.value = tag;
            option.textContent = tag;
            filterSelect.appendChild(option);
        });
        
        // 恢复之前选中的值（如果还存在）
        if (currentValue && allTags.includes(currentValue)) {
            filterSelect.value = currentValue;
        }
    }
    
    initializeDomainTagFilter() {
        // 收集现有的所有标签
        const allTags = new Set();
        this.currentData.forEach(item => {
            if (item.domain_tags && Array.isArray(item.domain_tags)) {
                item.domain_tags.forEach(tag => {
                    if (tag && typeof tag === 'string') {
                        allTags.add(tag.trim());
                    }
                });
            }
        });
        
        this.updateDomainTagFilter(Array.from(allTags).sort());
    }
    
    renderDomainTags(tags) {
        if (!tags || !Array.isArray(tags) || tags.length === 0) {
            return '';
        }
        
        return tags.map(tag => 
            `<span class="domain-tag">${this.escapeHtml(tag)}</span>`
        ).join('');
    }
    
    // ========== JSON转JSONL功能 ==========
    
    showConvertJsonModal() {
        // 重置表单
        document.getElementById('jsonFileInput').value = '';
        document.getElementById('outputFileName').value = '';
        document.getElementById('jsonPreviewSection').style.display = 'none';
        document.getElementById('convertOptionsSection').style.display = 'none';
        document.getElementById('previewJsonBtn').disabled = true;
        document.getElementById('executeConvertBtn').disabled = true;
        
        // 显示模态框
        document.getElementById('convertJsonModal').style.display = 'flex';
    }
    
    closeConvertJsonModal() {
        document.getElementById('convertJsonModal').style.display = 'none';
        this.selectedJsonData = null;
    }
    
    onJsonFileSelect(event) {
        const file = event.target.files[0];
        if (!file) {
            document.getElementById('jsonPreviewSection').style.display = 'none';
            document.getElementById('convertOptionsSection').style.display = 'none';
            document.getElementById('previewJsonBtn').disabled = true;
            document.getElementById('executeConvertBtn').disabled = true;
            return;
        }
        
        // 验证文件类型
        if (!file.name.toLowerCase().endsWith('.json')) {
            alert('请选择.json文件！');
            event.target.value = '';
            return;
        }
        
        // 显示文件基本信息
        document.getElementById('jsonFileName').textContent = file.name;
        document.getElementById('jsonFileSize').textContent = this.formatFileSize(file.size);
        
        // 默认输出文件名
        const baseName = file.name.replace(/\.json$/i, '');
        document.getElementById('outputFileName').value = `${baseName}_converted`;
        
        // 读取文件内容
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const content = e.target.result;
                this.parseJsonFile(content);
            } catch (error) {
                alert(`读取文件失败: ${error.message}`);
                event.target.value = '';
            }
        };
        reader.readAsText(file);
    }
    
    parseJsonFile(content) {
        try {
            let jsonObjects = [];
            
            // 尝试解析为JSON数组
            try {
                const parsed = JSON.parse(content);
                if (Array.isArray(parsed)) {
                    jsonObjects = parsed;
                } else if (typeof parsed === 'object' && parsed !== null) {
                    jsonObjects = [parsed];
                } else {
                    throw new Error('JSON文件必须包含对象或对象数组');
                }
            } catch (e) {
                // 如果不是有效的JSON数组，尝试按行解析（每行一个JSON对象）
                const lines = content.split('\n').filter(line => line.trim());
                for (const line of lines) {
                    try {
                        const obj = JSON.parse(line.trim());
                        if (typeof obj === 'object' && obj !== null) {
                            jsonObjects.push(obj);
                        }
                    } catch (lineError) {
                        // 跳过无效行
                        console.warn('跳过无效JSON行:', line);
                    }
                }
                
                if (jsonObjects.length === 0) {
                    throw new Error('文件中没有找到有效的JSON对象');
                }
            }
            
            this.selectedJsonData = jsonObjects;
            
            // 更新UI
            document.getElementById('jsonObjectCount').textContent = jsonObjects.length;
            
            // 显示预览（前3个对象）
            const preview = jsonObjects.slice(0, 3)
                .map(obj => JSON.stringify(obj, null, 2))
                .join('\n\n---\n\n');
            document.getElementById('jsonContentPreview').textContent = preview;
            
            // 显示预览和选项区域
            document.getElementById('jsonPreviewSection').style.display = 'block';
            document.getElementById('convertOptionsSection').style.display = 'block';
            document.getElementById('previewJsonBtn').disabled = false;
            document.getElementById('executeConvertBtn').disabled = false;
            
        } catch (error) {
            alert(`解析JSON文件失败: ${error.message}`);
            document.getElementById('jsonFileInput').value = '';
            document.getElementById('jsonPreviewSection').style.display = 'none';
            document.getElementById('convertOptionsSection').style.display = 'none';
        }
    }
    
    previewJsonConversion() {
        if (!this.selectedJsonData || !Array.isArray(this.selectedJsonData)) {
            alert('没有有效的JSON数据！');
            return;
        }
        
        // 生成JSONL预览（前5行）
        const jsonlPreview = this.selectedJsonData.slice(0, 5)
            .map(obj => JSON.stringify(obj))
            .join('\n');
        
        const previewContent = `JSONL格式预览 (前5行):\n\n${jsonlPreview}`;
        
        if (this.selectedJsonData.length > 5) {
            previewContent += `\n\n... 还有 ${this.selectedJsonData.length - 5} 行`;
        }
        
        // 创建临时预览窗口
        const previewWindow = window.open('', '_blank', 'width=800,height=600');
        previewWindow.document.write(`
            <html>
            <head><title>JSONL预览</title></head>
            <body style="font-family: monospace; padding: 20px; white-space: pre-wrap;">
                ${this.escapeHtml(previewContent)}
            </body>
            </html>
        `);
    }
    
    async executeJsonConversion() {
        if (!this.selectedJsonData || !Array.isArray(this.selectedJsonData)) {
            alert('没有有效的JSON数据！');
            return;
        }
        
        const outputFileName = document.getElementById('outputFileName').value.trim();
        if (!outputFileName) {
            alert('请输入输出文件名！');
            return;
        }
        
        const executeBtn = document.getElementById('executeConvertBtn');
        const originalText = executeBtn.textContent;
        
        try {
            executeBtn.disabled = true;
            executeBtn.textContent = '🔄 转换中...';
            
            // 生成JSONL内容
            const jsonlContent = this.selectedJsonData
                .map(obj => JSON.stringify(obj))
                .join('\n');
            
            // 发送到后端保存
            const response = await fetch('/api/data_management/convert_json_to_jsonl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filename: outputFileName,
                    content: jsonlContent,
                    count: this.selectedJsonData.length
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showNotification(`转换成功！已保存为 ${data.filename}，包含 ${data.count} 个对象`, 'success');
                this.closeConvertJsonModal();
                
                // 刷新目录列表
                await this.loadDirectoryList();
            } else {
                throw new Error(data.error || '转换失败');
            }
            
        } catch (error) {
            console.error('JSON转换失败:', error);
            this.showNotification(`转换失败: ${error.message}`, 'error');
        } finally {
            executeBtn.disabled = false;
            executeBtn.textContent = originalText;
        }
    }

    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // ========== 信息泄漏检测功能 ==========
    
    async detectInformationLeakage() {
        if (this.selectedItems.size === 0) {
            this.showNotification('请先选择要检测的数据项', 'warning');
            return;
        }
        
        const detectBtn = document.getElementById('detectLeakageBtn');
        const originalText = detectBtn.textContent;
        const autoFixLeakage = document.getElementById('autoFixLeakage').checked;
        const qpsLimit = parseInt(document.getElementById('leakageQpsLimit').value) || 1;
        
        // 获取选中的数据项
        const selectedData = Array.from(this.selectedItems).map(index => this.filteredData[index]);
        
        // 过滤出有reasoning_map的数据项
        const validItems = selectedData.filter(item => 
            item.question && 
            (item.reasoning_path || item.reasoning_map)
        );
        
        if (validItems.length === 0) {
            this.showNotification('选中的数据项中没有包含question和reasoning_path的数据', 'warning');
            return;
        }
        
        try {
            detectBtn.disabled = true;
            detectBtn.innerHTML = `<span class="loading-spinner"></span> 检测中...`;
            
            let processedCount = 0;
            let leakageCount = 0;
            let fixedCount = 0;
            let errorCount = 0;
            let unknownCount = 0;
            
            this.showNotification(`开始检测 ${validItems.length} 个数据项的信息泄漏...`, 'info');
            
            // 使用新的批量检测接口（后端并发处理，突破浏览器限制）
            try {
                detectBtn.innerHTML = `<span class="loading-spinner"></span> 检测中... (${validItems.length}项，并发${qpsLimit}个)`;
                
                const response = await fetch('/api/data_management/detect_leakage_batch', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        items: validItems,
                        auto_fix: autoFixLeakage,
                        qps_limit: qpsLimit
                    })
                });
                
                const result = await response.json();
                
                if (!result.success) {
                    throw new Error(result.error);
                }
                
                const { results, stats } = result.data;
                
                // 应用检测结果到原始数据
                for (const [originalIndex, resultData] of Object.entries(results)) {
                    const index = parseInt(originalIndex);
                    const item = validItems[index];
                    
                    if (resultData.processed) {
                        // 保存检测结果详情
                        item._leakage_detection_result = {
                            has_leakage: resultData.has_leakage,
                            leaked_info: resultData.leaked_info || [],
                            detection_time: new Date(resultData.detection_time * 1000).toISOString(),
                            fixed_reasoning_map: resultData.fixed_reasoning_map,
                            fixed_entity_mapping: resultData.fixed_entity_mapping
                        };
                        
                        // 应用自动修复
                        if (resultData.fixed && resultData.fixed_reasoning_map) {
                            // 创建备份字段
                            if (!item.original_reasoning_path) {
                                item.original_reasoning_path = item.reasoning_path || item.reasoning_map;
                            }
                            if (!item.original_entity_mapping) {
                                item.original_entity_mapping = {...(item.entity_mapping || {})};
                            }
                            
                            // 更新修正后的数据
                            item.reasoning_path = resultData.fixed_reasoning_map;
                            if (resultData.fixed_entity_mapping) {
                                item.entity_mapping = resultData.fixed_entity_mapping;
                            }
                            
                            // 标记为修改
                            item._user_modified = true;
                            item._leakage_fixed = true;
                        }
                    }
                }
                
                // 使用后端统计结果
                processedCount = stats.processed;
                leakageCount = stats.leakage_count;
                fixedCount = stats.fixed_count;
                errorCount = stats.error_count;
                unknownCount = stats.unknown_count;
                
            } catch (error) {
                console.error('批量检测失败:', error);
                errorCount = validItems.length;
                this.showNotification(`检测失败: ${error.message}`, 'error');
            }
            
            // 更新显示
            if (fixedCount > 0) {
                this.hasChanges = true;
                this.updateSaveButton();
                this.displayData();
                this.autoSaveIfEnabled();
            }
            
            // 显示结果
            let message = `检测完成：处理 ${processedCount} 项`;
            if (leakageCount > 0) {
                const unfixedCount = leakageCount - fixedCount;
                message += `，发现 ${leakageCount} 项有泄漏`;
                if (fixedCount > 0 && unfixedCount > 0) {
                    message += `：${fixedCount} 项已修复，${unfixedCount} 项未修复`;
                } else if (fixedCount > 0) {
                    message += `：全部 ${fixedCount} 项已修复`;
                } else {
                    message += `：全部 ${unfixedCount} 项未修复`;
                }
            } else {
                message += `，未发现信息泄漏`;
            }
            if (unknownCount > 0) {
                message += `，${unknownCount} 项未识别`;
            }
            if (errorCount > 0) {
                message += `，${errorCount} 项出错`;
            }
            
            message += ` (后端并发处理：${qpsLimit}个/秒)`;
            
            this.showNotification(message, leakageCount > 0 ? 'warning' : 'success');
            
        } catch (error) {
            console.error('信息泄漏检测失败:', error);
            this.showNotification(`检测失败: ${error.message}`, 'error');
        } finally {
            detectBtn.disabled = false;
            detectBtn.textContent = originalText;
        }
    }
    
    async detectSingleItemLeakage(item, autoFix = true, qpsLimit = 2.0) {
        try {
            const question = item.question || '';
            const reasoningMap = item.reasoning_path || item.reasoning_map || '';
            const entityMapping = item.entity_mapping || {};
            
            if (!question || !reasoningMap) {
                return { processed: false, reason: '缺少必要字段' };
            }
            
            const response = await fetch('/api/data_management/detect_leakage', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: question,
                    reasoning_map: reasoningMap,
                    entity_mapping: entityMapping,
                    qps_limit: qpsLimit
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                return { processed: false, reason: result.error };
            }
            
            const hasLeakage = result.data.has_leakage;
            let fixed = false;
            
            // 保存检测结果详情
            item._leakage_detection_result = {
                has_leakage: hasLeakage,
                leaked_info: result.data.leaked_info || [],
                detection_time: new Date().toISOString(),
                fixed_reasoning_map: result.data.fixed_reasoning_map,
                fixed_entity_mapping: result.data.fixed_entity_mapping,
                error: result.data.error // 保存错误信息（如果有）
            };
            
            if (hasLeakage === true && autoFix && result.data.fixed_reasoning_map) {
                // 创建备份字段
                if (!item.original_reasoning_path) {
                    item.original_reasoning_path = reasoningMap;
                }
                if (!item.original_entity_mapping) {
                    item.original_entity_mapping = {...entityMapping};
                }
                
                // 更新修正后的数据
                item.reasoning_path = result.data.fixed_reasoning_map;
                if (result.data.fixed_entity_mapping) {
                    item.entity_mapping = result.data.fixed_entity_mapping;
                }
                
                // 标记为修改
                item._user_modified = true;
                item._leakage_fixed = true;
                fixed = true;
            }
            
            return {
                processed: true,
                hasLeakage: hasLeakage,
                fixed: fixed,
                leakedInfo: result.data.leaked_info || []
            };
            
        } catch (error) {
            console.error('单项检测失败:', error);
            return { processed: false, reason: error.message };
        }
    }
    
    renderLeakageDetectionResult(item, index) {
        const leakageResult = item._leakage_detection_result;
        
        if (!leakageResult) {
            return ''; // 没有检测结果，不显示
        }
        
        const hasLeakage = leakageResult.has_leakage;
        const isFixed = item._leakage_fixed === true;
        const hasOriginalData = item.original_reasoning_path || item.original_entity_mapping;
        
        // 确定状态显示
        let statusClass, statusText;
        if (hasLeakage === 'unknown') {
            statusClass = 'unknown-status';
            statusText = '未识别';
        } else if (hasLeakage === true) {
            if (isFixed) {
                statusClass = 'has-leakage-fixed';
                statusText = '有泄漏(已修复)';
            } else {
                statusClass = 'has-leakage-unfixed';
                statusText = '有泄漏(未修复)';
            }
        } else {
            statusClass = 'no-leakage';
            statusText = '无泄漏';
        }
        
        return `
            <div class="content-section leakage-detection-section">
                <div class="content-label">
                    🛡️ 信息泄漏检测结果
                    <span class="leakage-status-badge ${statusClass}">
                        ${statusText}
                    </span>
                    <button class="btn btn-xs btn-secondary toggle-leakage-detail-btn" 
                            data-index="${index}" 
                            onclick="window.dataManager.toggleLeakageDetail(${index})"
                            title="展开/收起详情">
                        👁️ 详情
                    </button>
                </div>
                
                ${hasLeakage === true ? `
                    <div class="leakage-summary">
                        <div class="leaked-info-preview">
                            <strong>泄漏信息:</strong> 
                            ${leakageResult.leaked_info.map(info => `<span class="leaked-item">${this.escapeHtml(info)}</span>`).join(', ')}
                        </div>
                    </div>
                ` : hasLeakage === 'unknown' ? `
                    <div class="leakage-summary unknown-summary">
                        <div class="error-info-preview">
                            <strong>检测失败:</strong> 
                            <span class="error-message">${this.escapeHtml(leakageResult.error || '未知错误')}</span>
                        </div>
                    </div>
                ` : ''}
                
                <div class="leakage-detail" id="leakage-detail-${index}" style="display: none;">
                    ${hasLeakage && hasOriginalData ? `
                        <div class="comparison-container">
                            <div class="comparison-section">
                                <h6>🔍 修正前后对比</h6>
                                <div class="comparison-grid">
                                    ${item.original_reasoning_path ? `
                                        <div class="comparison-item">
                                            <div class="comparison-label before">修正前推理路径:</div>
                                            <div class="comparison-content before">
                                                ${this.escapeHtml(item.original_reasoning_path)}
                                            </div>
                                        </div>
                                        <div class="comparison-item">
                                            <div class="comparison-label after">修正后推理路径:</div>
                                            <div class="comparison-content after">
                                                ${this.escapeHtml(item.reasoning_path || '')}
                                            </div>
                                        </div>
                                    ` : ''}
                                    
                                    ${item.original_entity_mapping ? `
                                        <div class="comparison-item">
                                            <div class="comparison-label before">修正前实体映射:</div>
                                            <div class="comparison-content before">
                                                <pre>${this.escapeHtml(JSON.stringify(item.original_entity_mapping, null, 2))}</pre>
                                            </div>
                                        </div>
                                        <div class="comparison-item">
                                            <div class="comparison-label after">修正后实体映射:</div>
                                            <div class="comparison-content after">
                                                <pre>${this.escapeHtml(JSON.stringify(item.entity_mapping || {}, null, 2))}</pre>
                                            </div>
                                        </div>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="detection-metadata">
                        <small class="text-muted">
                            检测时间: ${leakageResult.detection_time ? new Date(leakageResult.detection_time).toLocaleString('zh-CN') : '未知'}
                        </small>
                    </div>
                </div>
            </div>
        `;
    }
    
    toggleLeakageDetail(index) {
        const detailElement = document.getElementById(`leakage-detail-${index}`);
        const button = document.querySelector(`[onclick="window.dataManager.toggleLeakageDetail(${index})"]`);
        
        if (detailElement.style.display === 'none') {
            detailElement.style.display = 'block';
            button.textContent = '🙈 收起';
        } else {
            detailElement.style.display = 'none';
            button.textContent = '👁️ 详情';
        }
    }
}

// 初始化数据管理器
document.addEventListener('DOMContentLoaded', () => {
    window.dataManager = new DataManager();
}); 