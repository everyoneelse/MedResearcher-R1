// 领域标签管理页面JavaScript功能

class DomainTagsManager {
    constructor() {
        this.currentFolderPath = '';
        this.currentTagsInfo = null;
        this.currentFilesStatus = null;
        this.singleFileResults = null;
        this.selectedFolderPath = '';
        this.selectedTags = new Set(); // 选中的标签
        this.allTagsInfo = {}; // 所有标签信息
        this.allDataItems = []; // 所有数据项
        this.filteredDataItems = []; // 筛选后的数据项
        this.currentPage = 1; // 当前页码
        this.pageSize = 20; // 每页条数
        this.totalPages = 0; // 总页数
        
        this.init();
    }
    
    init() {
        this.verifyDOMElements();
        this.setupEventListeners();
        this.loadLastFolderPath();
    }
    
    // 验证必需的DOM元素是否存在
    verifyDOMElements() {
        const requiredElements = [
            'folderPath',
            'browseFolderBtn', 
            'detectFolderBtn',
            'getFolderInfoBtn',
            'clearResultsBtn',
            'tagsInfoCard',
            'tagsInfoContainer',
            'tagFilterCard',
            'tagFilterContainer',
            'filterSummary',
            'selectedTagCount',
            'filteredFileCount',
            'filterDescription',
            'clearFilterBtn',
            'selectAllTagsBtn',
            'dataDisplayCard',
            'dataContainer',
            'dataStats',
            'paginationContainer',
            'paginationInfo',
            'currentPageInput',
            'totalPages',
            'firstPageBtn',
            'prevPageBtn',
            'nextPageBtn',
            'lastPageBtn',
            'pageSizeSelect',
            'filesStatusCard', 
            'filesStatusContainer',
            'progressCard',
            'progressText',
            'progressFill',
            'downloadResultBtn'
        ];
        
        const missingElements = [];
        
        for (const elementId of requiredElements) {
            const element = document.getElementById(elementId);
            if (!element) {
                missingElements.push(elementId);
                console.error(`缺少必需的DOM元素: ${elementId}`);
            }
        }
        
        if (missingElements.length > 0) {
            console.error('页面缺少以下必需元素:', missingElements);
            this.showNotification(`页面加载不完整，缺少以下元素: ${missingElements.join(', ')}`, 'error');
        } else {
            console.log('所有必需的DOM元素都已找到');
        }
    }
    
    // 安全获取DOM元素
    safeGetElement(elementId) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`DOM元素未找到: ${elementId}`);
            return null;
        }
        return element;
    }
    
    setupEventListeners() {
        // 文件夹批量处理
        const detectFolderBtn = this.safeGetElement('detectFolderBtn');
        const getFolderInfoBtn = this.safeGetElement('getFolderInfoBtn');
        const clearResultsBtn = this.safeGetElement('clearResultsBtn');
        
        if (detectFolderBtn) detectFolderBtn.addEventListener('click', this.detectFolderDomainTags.bind(this));
        if (getFolderInfoBtn) getFolderInfoBtn.addEventListener('click', this.getFolderTagsInfo.bind(this));
        if (clearResultsBtn) clearResultsBtn.addEventListener('click', this.clearResults.bind(this));
        
        // 标签信息操作
        const exportTagsBtn = this.safeGetElement('exportTagsBtn');
        const refreshTagsBtn = this.safeGetElement('refreshTagsBtn');
        
        if (exportTagsBtn) exportTagsBtn.addEventListener('click', this.exportTagsInfo.bind(this));
        if (refreshTagsBtn) refreshTagsBtn.addEventListener('click', this.getFolderTagsInfo.bind(this));
        
        // 文件状态操作
        const showAllFilesBtn = this.safeGetElement('showAllFilesBtn');
        const showProcessedOnlyBtn = this.safeGetElement('showProcessedOnlyBtn');
        
        if (showAllFilesBtn) showAllFilesBtn.addEventListener('click', () => this.showFilesStatus('all'));
        if (showProcessedOnlyBtn) showProcessedOnlyBtn.addEventListener('click', () => this.showFilesStatus('processed'));
        
        // 标签筛选操作
        const clearFilterBtn = this.safeGetElement('clearFilterBtn');
        const selectAllTagsBtn = this.safeGetElement('selectAllTagsBtn');
        
        if (clearFilterBtn) clearFilterBtn.addEventListener('click', this.clearTagFilter.bind(this));
        if (selectAllTagsBtn) selectAllTagsBtn.addEventListener('click', this.selectAllTags.bind(this));
        
        // 单文件处理
        const detectSingleBtn = this.safeGetElement('detectSingleBtn');
        const downloadResultBtn = this.safeGetElement('downloadResultBtn');
        
        if (detectSingleBtn) detectSingleBtn.addEventListener('click', this.detectSingleFiles.bind(this));
        if (downloadResultBtn) downloadResultBtn.addEventListener('click', this.downloadSingleResult.bind(this));
        
        // 文件夹选择器
        const browseFolderBtn = this.safeGetElement('browseFolderBtn');
        const folderSelector = this.safeGetElement('folderSelector');
        
        if (browseFolderBtn) browseFolderBtn.addEventListener('click', this.openFolderSelector.bind(this));
        if (folderSelector) folderSelector.addEventListener('change', this.onFolderSelected.bind(this));
        
        // 文件夹路径保存
        const folderPath = this.safeGetElement('folderPath');
        if (folderPath) folderPath.addEventListener('change', this.saveLastFolderPath.bind(this));
        
        // 分页相关事件
        this.setupPaginationEvents();
    }
    
    // 文件夹批量检测
    async detectFolderDomainTags() {
        const folderPathElement = this.safeGetElement('folderPath');
        const forceReprocessElement = this.safeGetElement('forceReprocess');
        const detectBtn = this.safeGetElement('detectFolderBtn');
        
        if (!folderPathElement || !forceReprocessElement || !detectBtn) {
            this.showNotification('页面元素缺失，无法执行操作', 'error');
            return;
        }
        
        const folderPath = folderPathElement.value.trim();
        const forceReprocess = forceReprocessElement.checked;
        
        if (!folderPath) {
            this.showNotification('请输入文件夹路径', 'error');
            return;
        }
        
        try {
            this.setButtonLoading(detectBtn, true, '🤖 检测中...');
            this.showProgress('开始检测文件夹领域标签...', 0);
            
            const response = await fetch('/api/data_management/detect_folder_domain_tags', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    folder_path: folderPath,
                    force_reprocess: forceReprocess
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                const result = data.result;
                this.showProgress('检测完成！', 100);
                this.showNotification(
                    `检测完成！处理了 ${result.processed_files}/${result.total_files} 个文件，` +
                    `共 ${result.total_items} 条数据，发现 ${result.tags_count} 个领域标签`, 
                    'success'
                );
                
                this.currentFolderPath = folderPath;
                
                // 自动获取并显示结果
                setTimeout(() => {
                    this.getFolderTagsInfo();
                    this.hideProgress();
                }, 1500);
            } else {
                this.hideProgress();
                this.showNotification(`检测失败: ${data.error}`, 'error');
            }
            
        } catch (error) {
            console.error('文件夹领域标签检测错误:', error);
            this.hideProgress();
            this.showNotification('检测失败，请检查网络连接', 'error');
        } finally {
            this.setButtonLoading(detectBtn, false, '🤖 开始批量检测');
        }
    }
    
    // 获取文件夹标签信息
    async getFolderTagsInfo() {
        const folderPathElement = this.safeGetElement('folderPath');
        const infoBtn = this.safeGetElement('getFolderInfoBtn');
        
        if (!folderPathElement || !infoBtn) {
            this.showNotification('页面元素缺失，无法执行操作', 'error');
            return;
        }
        
        const folderPath = folderPathElement.value.trim() || this.currentFolderPath;
        
        if (!folderPath) {
            this.showNotification('请输入文件夹路径', 'error');
            return;
        }
        
        // 基本路径格式检查
        if (folderPath.length < 2) {
            this.showNotification('文件夹路径格式不正确', 'error');
            return;
        }
        
        try {
            this.setButtonLoading(infoBtn, true, '📊 获取中...');
            
            console.log('正在获取标签信息，文件夹路径:', folderPath);
            
            const response = await fetch(`/api/data_management/get_domain_tags_info?folder_path=${encodeURIComponent(folderPath)}`);
            
            console.log('API响应状态:', response.status, response.statusText);
            
            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log('API响应数据:', data);
            
            if (data.success) {
                this.currentTagsInfo = data.info;
                this.displayTagsInfo(data.info);
                this.displayFilesStatus(data.info.file_processing_status || {});
                this.showNotification('标签信息获取成功', 'success');
            } else {
                this.showNotification(`获取失败: ${data.error}`, 'error');
                console.error('API返回错误:', data.error);
            }
            
        } catch (error) {
            console.error('获取标签信息错误:', error);
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                this.showNotification('网络连接失败，请检查服务器是否正常运行', 'error');
            } else if (error.message.includes('HTTP错误')) {
                this.showNotification(`服务器错误: ${error.message}`, 'error');
            } else {
                this.showNotification(`获取失败: ${error.message}`, 'error');
            }
            
            // 如果是文件夹相关错误，提供帮助信息
            if (error.message.includes('文件夹') || error.message.includes('路径')) {
                setTimeout(() => {
                    this.showNotification(
                        '提示: 请确保文件夹路径正确，例如: /Users/username/Documents/data 或 C:\\Users\\username\\Documents\\data', 
                        'info'
                    );
                }, 2000);
            }
        } finally {
            this.setButtonLoading(infoBtn, false, '📊 查看标签信息');
        }
    }
    
    // 显示标签信息
    displayTagsInfo(info) {
        const container = this.safeGetElement('tagsInfoContainer');
        const tagsInfoCard = this.safeGetElement('tagsInfoCard');
        
        if (!container || !tagsInfoCard) {
            return;
        }
        
        const tagsArray = Object.entries(info.tags || {});
        const totalProcessed = info.total_processed || 0;
        
        if (tagsArray.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🏷️</div>
                    <div class="empty-state-text">暂无标签信息</div>
                    <div class="empty-state-hint">请先运行文件夹检测</div>
                </div>
            `;
            tagsInfoCard.style.display = 'block';
            this.hideTagFilter();
            return;
        }
        
        // 按数量排序
        tagsArray.sort((a, b) => (b[1].count || 0) - (a[1].count || 0));
        
        let html = `
            <div class="info-summary">
                <div class="summary-item">
                    <div class="summary-value">${totalProcessed}</div>
                    <div class="summary-label">总处理数据</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${tagsArray.length}</div>
                    <div class="summary-label">标签数量</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${info.last_updated ? new Date(info.last_updated).toLocaleDateString() : '暂无'}</div>
                    <div class="summary-label">最后更新</div>
                </div>
            </div>
            
            <div class="tags-grid">
        `;
        
        for (const [tagName, tagInfo] of tagsArray) {
            const count = tagInfo.count || 0;
            const percentage = totalProcessed > 0 ? ((count / totalProcessed) * 100).toFixed(1) : '0';
            
            html += `
                <div class="tag-item clickable" data-tag="${this.escapeHtml(tagName)}">
                    <div class="tag-name">${this.escapeHtml(tagName)}</div>
                    <div class="tag-count">${count} 条数据</div>
                    <div class="tag-percentage">${percentage}% 占比</div>
                    <div class="tag-description">${tagInfo.description || '暂无描述'}</div>
                </div>
            `;
        }
        
        html += '</div>';
        
        container.innerHTML = html;
        tagsInfoCard.style.display = 'block';
        
        // 保存标签信息并显示筛选器
        this.allTagsInfo = info.tags || {};
        this.displayTagFilter();
        
        // 加载数据
        this.loadFolderData();
        
        // 添加标签点击事件
        container.addEventListener('click', (e) => {
            const tagItem = e.target.closest('.tag-item');
            if (tagItem) {
                const tagName = tagItem.getAttribute('data-tag');
                if (tagName) {
                    this.selectTagFilter(tagName);
                }
            }
        });
    }
    
    // 显示文件状态
    displayFilesStatus(fileStatus, filter = 'all') {
        const container = this.safeGetElement('filesStatusContainer');
        const filesStatusCard = this.safeGetElement('filesStatusCard');
        
        if (!container || !filesStatusCard) {
            return;
        }
        
        const fileStatusArray = Object.entries(fileStatus);
        
        if (fileStatusArray.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📁</div>
                    <div class="empty-state-text">暂无文件信息</div>
                    <div class="empty-state-hint">请先运行文件夹检测</div>
                </div>
            `;
            filesStatusCard.style.display = 'block';
            return;
        }
        
        // 过滤文件
        const filteredFiles = fileStatusArray.filter(([filename, status]) => {
            if (filter === 'processed') {
                return status.processed === true;
            }
            return true; // 'all'
        });
        
        if (filteredFiles.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">🔍</div>
                    <div class="empty-state-text">没有找到匹配的文件</div>
                </div>
            `;
        } else {
            let html = '<div class="files-grid">';
            
            for (const [filename, status] of filteredFiles) {
                const statusIcon = status.processed ? '✅' : '❌';
                const lastProcessed = status.last_processed ? 
                    new Date(status.last_processed).toLocaleString() : '未处理';
                const fileModified = status.file_modified ?
                    new Date(status.file_modified).toLocaleString() : '未知';
                
                html += `
                    <div class="file-status-item">
                        <div class="file-name">
                            <span class="file-status-icon">${statusIcon}</span>
                            ${filename}
                        </div>
                        <div class="file-details">
                            <div class="file-detail-item">
                                <div class="detail-label">处理数量</div>
                                <div class="detail-value">${status.processed_count || 0} 条</div>
                            </div>
                            <div class="file-detail-item">
                                <div class="detail-label">处理时间</div>
                                <div class="detail-value">${lastProcessed}</div>
                            </div>
                            <div class="file-detail-item">
                                <div class="detail-label">文件修改</div>
                                <div class="detail-value">${fileModified}</div>
                            </div>
                            <div class="file-detail-item">
                                <div class="detail-label">状态</div>
                                <div class="detail-value">${status.processed ? '已处理' : '未处理'}</div>
                            </div>
                        </div>
                    </div>
                `;
            }
            
            html += '</div>';
            container.innerHTML = html;
        }
        
        filesStatusCard.style.display = 'block';
    }
    
    // 单文件检测
    async detectSingleFiles() {
        const fileInput = document.getElementById('singleFileInput');
        const existingTagsText = document.getElementById('existingTags').value.trim();
        const detectBtn = document.getElementById('detectSingleBtn');
        
        if (!fileInput.files || fileInput.files.length === 0) {
            this.showNotification('请选择至少一个JSONL文件', 'error');
            return;
        }
        
        const existingTags = existingTagsText ? 
            existingTagsText.split(',').map(tag => tag.trim()).filter(tag => tag) : [];
        
        try {
            this.setButtonLoading(detectBtn, true, '🔍 检测中...');
            
            // 处理每个文件
            const allResults = [];
            
            for (let i = 0; i < fileInput.files.length; i++) {
                const file = fileInput.files[i];
                this.showNotification(`正在处理文件 ${i + 1}/${fileInput.files.length}: ${file.name}`, 'info');
                
                // 读取文件内容
                const fileContent = await this.readFileContent(file);
                const items = fileContent.split('\n')
                    .filter(line => line.trim())
                    .map(line => JSON.parse(line));
                
                // 调用检测API
                const response = await fetch('/api/data_management/detect_domain_tags', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        data: items,
                        existing_tags: existingTags
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // 合并结果
                    const enhancedItems = items.map((item, index) => {
                        const result = data.results.find(r => r.index === index);
                        return {
                            ...item,
                            domain_tags: result ? result.domain_tags : []
                        };
                    });
                    
                    allResults.push({
                        filename: file.name,
                        items: enhancedItems,
                        tags: data.all_tags
                    });
                } else {
                    this.showNotification(`文件 ${file.name} 处理失败: ${data.error}`, 'error');
                }
            }
            
            if (allResults.length > 0) {
                this.singleFileResults = allResults;
                this.showNotification(`成功处理 ${allResults.length} 个文件`, 'success');
                const downloadResultBtn = this.safeGetElement('downloadResultBtn');
                if (downloadResultBtn) downloadResultBtn.style.display = 'inline-block';
            }
            
        } catch (error) {
            console.error('单文件检测错误:', error);
            this.showNotification('检测失败，请检查文件格式', 'error');
        } finally {
            this.setButtonLoading(detectBtn, false, '🔍 检测标签');
        }
    }
    
    // 读取文件内容
    readFileContent(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = e => reject(e);
            reader.readAsText(file);
        });
    }
    
    // 下载单文件处理结果
    downloadSingleResult() {
        if (!this.singleFileResults) {
            this.showNotification('没有可下载的结果', 'error');
            return;
        }
        
        for (const result of this.singleFileResults) {
            const content = result.items.map(item => JSON.stringify(item)).join('\n');
            const blob = new Blob([content], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = result.filename.replace('.jsonl', '_with_tags.jsonl');
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }
        
        this.showNotification('文件下载已开始', 'success');
    }
    
    // 导出标签信息
    exportTagsInfo() {
        if (!this.currentTagsInfo) {
            this.showNotification('没有可导出的标签信息', 'error');
            return;
        }
        
        const exportData = {
            export_time: new Date().toISOString(),
            folder_path: this.currentFolderPath,
            ...this.currentTagsInfo
        };
        
        const content = JSON.stringify(exportData, null, 2);
        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = `domain_tags_export_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showNotification('标签信息导出成功', 'success');
    }
    
    // 显示文件状态（带过滤）
    showFilesStatus(filter) {
        if (this.currentTagsInfo) {
            this.displayFilesStatus(this.currentTagsInfo.file_processing_status || {}, filter);
        }
    }
    
    // 清空结果
    clearResults() {
        const tagsInfoCard = this.safeGetElement('tagsInfoCard');
        const filesStatusCard = this.safeGetElement('filesStatusCard');
        const progressCard = this.safeGetElement('progressCard');
        const downloadResultBtn = this.safeGetElement('downloadResultBtn');
        
        if (tagsInfoCard) tagsInfoCard.style.display = 'none';
        if (filesStatusCard) filesStatusCard.style.display = 'none';
        if (progressCard) progressCard.style.display = 'none';
        if (downloadResultBtn) downloadResultBtn.style.display = 'none';
        
        this.hideTagFilter();
        this.hideDataDisplay();
        
        this.currentTagsInfo = null;
        this.currentFilesStatus = null;
        this.selectedTags.clear();
        this.allTagsInfo = {};
        this.allDataItems = [];
        this.filteredDataItems = [];
        this.currentPage = 1;
        this.singleFileResults = null;
        
        this.showNotification('结果已清空', 'info');
    }
    
    // 显示进度
    showProgress(text, percentage) {
        const progressCard = this.safeGetElement('progressCard');
        const progressText = this.safeGetElement('progressText');
        const progressFill = this.safeGetElement('progressFill');
        
        if (!progressCard || !progressText || !progressFill) {
            return;
        }
        
        progressCard.style.display = 'block';
        progressText.textContent = text;
        progressFill.style.width = `${percentage}%`;
    }
    
    // 隐藏进度
    hideProgress() {
        const progressCard = this.safeGetElement('progressCard');
        if (progressCard) progressCard.style.display = 'none';
    }
    
    // 设置按钮加载状态
    setButtonLoading(button, loading, text) {
        if (!button) {
            console.error('按钮元素未找到');
            return;
        }
        
        if (loading) {
            button.disabled = true;
            button.innerHTML = `<span class="loading-spinner"></span> ${text}`;
        } else {
            button.disabled = false;
            button.innerHTML = text;
        }
    }
    
    // 显示通知
    showNotification(message, type = 'info') {
        const notification = document.getElementById('notification');
        notification.textContent = message;
        notification.className = `notification ${type} show`;
        
        setTimeout(() => {
            notification.classList.remove('show');
        }, 5000);
    }
    
    // 保存上次使用的文件夹路径
    saveLastFolderPath() {
        const folderPathElement = this.safeGetElement('folderPath');
        if (folderPathElement) {
            const folderPath = folderPathElement.value.trim();
            if (folderPath) {
                try {
                    localStorage.setItem('lastFolderPath', folderPath);
                } catch (error) {
                    console.warn('无法保存文件夹路径到localStorage:', error);
                }
            }
        }
    }
    
    // 加载上次使用的文件夹路径
    loadLastFolderPath() {
        try {
            const lastPath = localStorage.getItem('lastFolderPath');
            if (lastPath) {
                const folderPathElement = this.safeGetElement('folderPath');
                if (folderPathElement) {
                    folderPathElement.value = lastPath;
                    this.currentFolderPath = lastPath;
                }
            }
        } catch (error) {
            console.warn('无法从localStorage加载文件夹路径:', error);
        }
    }
    
    // 打开文件夹选择器
    openFolderSelector() {
        const folderSelector = this.safeGetElement('folderSelector');
        if (folderSelector) folderSelector.click();
    }
    
    // 文件夹选择事件处理
    onFolderSelected(event) {
        const files = event.target.files;
        if (files.length > 0) {
            // 获取第一个文件的路径，然后提取文件夹路径
            const firstFile = files[0];
            const relativePath = firstFile.webkitRelativePath;
            
            if (relativePath) {
                // 提取文件夹路径（去掉文件名部分）
                const pathParts = relativePath.split('/');
                pathParts.pop(); // 移除文件名
                const folderPath = pathParts.join('/');
                
                // 如果是绝对路径，需要获取完整路径
                // 但由于浏览器安全限制，我们只能获得相对路径
                // 所以我们需要让用户手动输入或者提供一个基础路径
                
                // 检查是否有JSONL文件
                const jsonlFiles = Array.from(files).filter(file => 
                    file.name.endsWith('.jsonl')
                );
                
                if (jsonlFiles.length > 0) {
                    // 尝试从文件对象获取更完整的路径信息
                    this.handleFolderSelection(firstFile, folderPath, jsonlFiles.length);
                } else {
                    this.showNotification('选择的文件夹中没有找到JSONL文件', 'warning');
                }
            }
        }
    }
    
    // 处理文件夹选择结果
    async handleFolderSelection(firstFile, relativePath, jsonlCount) {
        try {
            const folderPathInput = this.safeGetElement('folderPath');
            
            if (!folderPathInput) {
                this.showNotification('文件夹路径输入框未找到', 'error');
                return;
            }
            
            // 检查是否能够通过某种方式获取到绝对路径
            let absolutePath = null;
            
            // 尝试通过不同方法获取路径信息
            if (firstFile.path) {
                // 某些环境下可能可以获取到path属性
                const filePath = firstFile.path;
                absolutePath = filePath.substring(0, filePath.lastIndexOf('/'));
            } else if (firstFile.webkitRelativePath) {
                // 提取文件夹名称，用户可能需要手动补充完整路径
                const pathParts = firstFile.webkitRelativePath.split('/');
                const folderName = pathParts[0];
                
                // 提示用户输入完整路径
                const userPath = prompt(
                    `检测到文件夹 "${folderName}" 包含 ${jsonlCount} 个JSONL文件。\n` +
                    `由于浏览器安全限制，请输入该文件夹的完整绝对路径：\n` +
                    `(例如：/Users/username/Documents/${folderName} 或 C:\\Users\\username\\Documents\\${folderName})`,
                    folderName
                );
                
                if (userPath && userPath.trim()) {
                    absolutePath = userPath.trim();
                }
            }
            
            if (absolutePath) {
                folderPathInput.value = absolutePath;
                folderPathInput.readOnly = false;
                this.currentFolderPath = absolutePath;
                this.saveLastFolderPath();
                this.showNotification(
                    `文件夹路径已设置：${absolutePath}（包含 ${jsonlCount} 个JSONL文件）`, 
                    'success'
                );
            } else {
                folderPathInput.value = relativePath || '';
                folderPathInput.readOnly = false;
                folderPathInput.placeholder = '请输入完整的文件夹路径...';
                folderPathInput.focus();
                this.showNotification(
                    `已选择包含 ${jsonlCount} 个JSONL文件的文件夹，请输入完整路径`, 
                    'warning'
                );
            }
            
        } catch (error) {
            console.error('处理文件夹选择失败:', error);
            this.showNotification('处理文件夹选择时出错', 'error');
        }
    }
    
    // 显示标签筛选器
    displayTagFilter() {
        const tagFilterCard = this.safeGetElement('tagFilterCard');
        const container = this.safeGetElement('tagFilterContainer');
        
        if (!tagFilterCard || !container) return;
        
        const tagsArray = Object.entries(this.allTagsInfo);
        
        if (tagsArray.length === 0) {
            this.hideTagFilter();
            return;
        }
        
        // 按数量排序
        tagsArray.sort((a, b) => (b[1].count || 0) - (a[1].count || 0));
        
        let html = '';
        for (const [tagName, tagInfo] of tagsArray) {
            const count = tagInfo.count || 0;
            const isSelected = this.selectedTags.has(tagName);
            
            html += `
                <div class="tag-filter-item ${isSelected ? 'selected' : ''}" data-tag="${this.escapeHtml(tagName)}">
                    <input type="checkbox" class="tag-filter-checkbox" ${isSelected ? 'checked' : ''}>
                    <label class="tag-filter-label">
                        <span>${this.escapeHtml(tagName)}</span>
                        <span class="tag-filter-count">${count}</span>
                    </label>
                </div>
            `;
        }
        
        container.innerHTML = html;
        tagFilterCard.style.display = 'block';
        
        // 添加点击事件
        container.addEventListener('click', (e) => {
            const filterItem = e.target.closest('.tag-filter-item');
            if (filterItem) {
                const tagName = filterItem.getAttribute('data-tag');
                const checkbox = filterItem.querySelector('.tag-filter-checkbox');
                
                if (e.target === checkbox) {
                    // 直接点击checkbox
                    this.toggleTagSelection(tagName, checkbox.checked);
                } else {
                    // 点击其他区域，切换选择状态
                    checkbox.checked = !checkbox.checked;
                    this.toggleTagSelection(tagName, checkbox.checked);
                }
            }
        });
        
        this.updateFilterSummary();
    }
    
    // 隐藏标签筛选器
    hideTagFilter() {
        const tagFilterCard = this.safeGetElement('tagFilterCard');
        if (tagFilterCard) tagFilterCard.style.display = 'none';
    }
    
    // 切换标签选择状态
    toggleTagSelection(tagName, selected) {
        if (selected) {
            this.selectedTags.add(tagName);
        } else {
            this.selectedTags.delete(tagName);
        }
        
        this.updateFilterUI();
        this.updateFilterSummary();
        this.applyTagFilter();
    }
    
    // 更新筛选器UI
    updateFilterUI() {
        const container = this.safeGetElement('tagFilterContainer');
        if (!container) return;
        
        const filterItems = container.querySelectorAll('.tag-filter-item');
        filterItems.forEach(item => {
            const tagName = item.getAttribute('data-tag');
            const checkbox = item.querySelector('.tag-filter-checkbox');
            const isSelected = this.selectedTags.has(tagName);
            
            checkbox.checked = isSelected;
            item.classList.toggle('selected', isSelected);
        });
    }
    
    // 更新筛选汇总信息
    updateFilterSummary() {
        const summary = this.safeGetElement('filterSummary');
        const selectedCount = this.safeGetElement('selectedTagCount');
        const filteredCount = this.safeGetElement('filteredFileCount');
        
        if (!summary || !selectedCount || !filteredCount) return;
        
        selectedCount.textContent = this.selectedTags.size;
        
        if (this.selectedTags.size > 0) {
            // 显示匹配的数据条数，而不是文件数
            filteredCount.textContent = this.filteredDataItems.length;
            summary.style.display = 'flex';
            
            // 如果选择了多个标签，更新说明文本以强调与关系
            const filterDescription = this.safeGetElement('filterDescription');
            if (filterDescription) {
                if (this.selectedTags.size > 1) {
                    filterDescription.textContent = `（已选择 ${this.selectedTags.size} 个标签，显示同时包含所有标签的数据）`;
                    filterDescription.style.color = 'var(--primary-color)';
                    filterDescription.style.fontWeight = '500';
                } else {
                    filterDescription.textContent = '（多选标签时显示同时包含所有标签的数据）';
                    filterDescription.style.color = 'var(--gray-500)';
                    filterDescription.style.fontWeight = 'normal';
                }
            }
        } else {
            summary.style.display = 'none';
            
            // 重置说明文本
            const filterDescription = this.safeGetElement('filterDescription');
            if (filterDescription) {
                filterDescription.textContent = '（多选标签时显示同时包含所有标签的数据）';
                filterDescription.style.color = 'var(--gray-500)';
                filterDescription.style.fontWeight = 'normal';
            }
        }
    }
    
    // 获取筛选后的文件
    getFilteredFiles() {
        if (!this.currentFilesStatus || this.selectedTags.size === 0) {
            return Object.entries(this.currentFilesStatus || {});
        }
        
        return Object.entries(this.currentFilesStatus).filter(([filename, status]) => {
            const fileTags = status.tags || [];
            // 检查文件是否包含任何选中的标签
            return Array.from(this.selectedTags).some(selectedTag => 
                fileTags.includes(selectedTag)
            );
        });
    }
    
    // 应用标签筛选
    applyTagFilter() {
        if (this.selectedTags.size === 0) {
            // 没有选中标签，显示所有文件
            this.displayFilesStatus(this.currentFilesStatus || {}, 'all');
        } else {
            // 有选中标签，显示筛选后的文件
            const filteredFiles = this.getFilteredFiles();
            const filteredStatus = {};
            filteredFiles.forEach(([filename, status]) => {
                filteredStatus[filename] = status;
            });
            this.displayFilesStatus(filteredStatus, 'all');
        }
    }
    
    // 选择特定标签（点击统计信息中的标签时调用）
    selectTagFilter(tagName) {
        this.selectedTags.clear();
        this.selectedTags.add(tagName);
        this.updateFilterUI();
        this.updateFilterSummary();
        this.applyTagFilter();
        if (this.selectedTags.size > 1) {
            this.showNotification(`已筛选标签: ${Array.from(this.selectedTags).join(', ')}（显示同时包含所有标签的数据）`, 'info');
        } else {
            this.showNotification(`已筛选标签: ${tagName}`, 'info');
        }
        
        // 滚动到标签筛选区域
        this.scrollToTagFilter();
    }
    
    // 清空标签筛选
    clearTagFilter() {
        this.selectedTags.clear();
        this.updateFilterUI();
        this.updateFilterSummary();
        this.applyTagFilter();
        this.showNotification('已清空标签筛选', 'info');
    }
    
    // 全选标签
    selectAllTags() {
        Object.keys(this.allTagsInfo).forEach(tagName => {
            this.selectedTags.add(tagName);
        });
        this.updateFilterUI();
        this.updateFilterSummary();
        this.applyTagFilter();
        this.showNotification(`已选择所有 ${this.selectedTags.size} 个标签（将显示同时包含所有标签的数据）`, 'info');
    }
    
    // HTML转义函数
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }
    
    // 设置分页事件监听器
    setupPaginationEvents() {
        const pageSizeSelect = this.safeGetElement('pageSizeSelect');
        const currentPageInput = this.safeGetElement('currentPageInput');
        const firstPageBtn = this.safeGetElement('firstPageBtn');
        const prevPageBtn = this.safeGetElement('prevPageBtn');
        const nextPageBtn = this.safeGetElement('nextPageBtn');
        const lastPageBtn = this.safeGetElement('lastPageBtn');
        
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                this.pageSize = parseInt(e.target.value);
                this.currentPage = 1;
                this.displayData();
            });
        }
        
        if (currentPageInput) {
            currentPageInput.addEventListener('change', (e) => {
                const page = parseInt(e.target.value);
                if (page >= 1 && page <= this.totalPages) {
                    this.currentPage = page;
                    this.displayData();
                } else {
                    e.target.value = this.currentPage;
                }
            });
        }
        
        if (firstPageBtn) firstPageBtn.addEventListener('click', () => this.goToPage(1));
        if (prevPageBtn) prevPageBtn.addEventListener('click', () => this.goToPage(this.currentPage - 1));
        if (nextPageBtn) nextPageBtn.addEventListener('click', () => this.goToPage(this.currentPage + 1));
        if (lastPageBtn) lastPageBtn.addEventListener('click', () => this.goToPage(this.totalPages));
    }
    
    // 加载文件夹数据
    async loadFolderData() {
        const folderPathElement = this.safeGetElement('folderPath');
        
        if (!folderPathElement) return;
        
        const folderPath = folderPathElement.value.trim() || this.currentFolderPath;
        
        if (!folderPath) return;
        
        try {
            this.showDataLoading();
            
            console.log('正在加载文件夹数据，路径:', folderPath);
            
            const response = await fetch(`/api/data_management/get_folder_data?folder_path=${encodeURIComponent(folderPath)}`);
            
            if (!response.ok) {
                throw new Error(`HTTP错误: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.allDataItems = data.data || [];
                this.currentPage = 1;
                this.applyTagFilter(); // 这会调用displayData
                this.showDataDisplay();
                console.log(`成功加载 ${this.allDataItems.length} 条数据`);
            } else {
                console.error('API返回错误:', data.error);
                this.showDataEmpty('加载数据失败: ' + data.error);
            }
            
        } catch (error) {
            console.error('加载文件夹数据错误:', error);
            this.showDataEmpty('加载数据失败: ' + error.message);
        }
    }
    
    // 显示数据加载状态
    showDataLoading() {
        const container = this.safeGetElement('dataContainer');
        if (container) {
            container.innerHTML = `
                <div class="data-loading">
                    <div class="loading-spinner"></div>
                    <div>正在加载数据...</div>
                </div>
            `;
        }
    }
    
    // 显示数据为空状态
    showDataEmpty(message = '暂无数据') {
        const container = this.safeGetElement('dataContainer');
        if (container) {
            container.innerHTML = `
                <div class="data-empty">
                    <div class="data-empty-icon">📄</div>
                    <div>${message}</div>
                </div>
            `;
        }
        this.hidePagination();
    }
    
    // 显示数据展示区域
    showDataDisplay() {
        const dataDisplayCard = this.safeGetElement('dataDisplayCard');
        if (dataDisplayCard) dataDisplayCard.style.display = 'block';
    }
    
    // 隐藏数据展示区域
    hideDataDisplay() {
        const dataDisplayCard = this.safeGetElement('dataDisplayCard');
        if (dataDisplayCard) dataDisplayCard.style.display = 'none';
    }
    
    // 应用标签筛选 (重写以支持数据筛选)
    applyTagFilter() {
        if (this.selectedTags.size === 0) {
            // 没有选中标签，显示所有数据
            this.filteredDataItems = [...this.allDataItems];
        } else {
            // 有选中标签，筛选数据（与关系：必须包含所有选中的标签）
            this.filteredDataItems = this.allDataItems.filter(item => {
                const itemTags = item.domain_tags || [];
                return Array.from(this.selectedTags).every(selectedTag => 
                    itemTags.includes(selectedTag)
                );
            });
        }
        
        this.currentPage = 1; // 重置到第一页
        this.displayData();
        this.updateFilterSummary(); // 更新筛选摘要
        
        // 同时更新文件状态显示
        if (this.selectedTags.size === 0) {
            this.displayFilesStatus(this.currentFilesStatus || {}, 'all');
        } else {
            const filteredFiles = this.getFilteredFiles();
            const filteredStatus = {};
            filteredFiles.forEach(([filename, status]) => {
                filteredStatus[filename] = status;
            });
            this.displayFilesStatus(filteredStatus, 'all');
        }
    }
    
    // 显示数据
    displayData() {
        const container = this.safeGetElement('dataContainer');
        const dataStats = this.safeGetElement('dataStats');
        
        if (!container || !dataStats) return;
        
        const totalItems = this.filteredDataItems.length;
        
        // 更新统计信息
        dataStats.textContent = `共 ${totalItems} 条数据`;
        
        if (totalItems === 0) {
            this.showDataEmpty('暂无符合条件的数据');
            return;
        }
        
        // 计算分页
        this.totalPages = Math.ceil(totalItems / this.pageSize);
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = Math.min(startIndex + this.pageSize, totalItems);
        const currentPageData = this.filteredDataItems.slice(startIndex, endIndex);
        
        // 渲染数据项
        let html = '';
        currentPageData.forEach((item, index) => {
            const globalIndex = startIndex + index + 1;
            const tags = item.domain_tags || [];
            
            html += `
                <div class="data-item">
                    <div class="data-item-header">
                        <div class="data-item-index">#${globalIndex}</div>
                        <div class="data-item-tags">
                            ${tags.map(tag => `<span class="data-tag">${this.escapeHtml(tag)}</span>`).join('')}
                        </div>
                    </div>
                    <div class="data-item-content">
                        <div class="data-field">
                            <div class="data-field-label">问题 (Question)</div>
                            <div class="data-field-content">${this.escapeHtml(item.question || '暂无')}</div>
                        </div>
                        <div class="data-field">
                            <div class="data-field-label">答案 (Answer)</div>
                            <div class="data-field-content">${this.escapeHtml(item.answer || '暂无')}</div>
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
        this.updatePagination(totalItems, startIndex + 1, endIndex);
    }
    
    // 更新分页控件
    updatePagination(totalItems, startIndex, endIndex) {
        const paginationContainer = this.safeGetElement('paginationContainer');
        const paginationInfo = this.safeGetElement('paginationInfo');
        const currentPageInput = this.safeGetElement('currentPageInput');
        const totalPagesSpan = this.safeGetElement('totalPages');
        const firstPageBtn = this.safeGetElement('firstPageBtn');
        const prevPageBtn = this.safeGetElement('prevPageBtn');
        const nextPageBtn = this.safeGetElement('nextPageBtn');
        const lastPageBtn = this.safeGetElement('lastPageBtn');
        
        if (this.totalPages <= 1) {
            this.hidePagination();
            return;
        }
        
        if (paginationContainer) paginationContainer.style.display = 'flex';
        if (paginationInfo) paginationInfo.textContent = `显示第 ${startIndex}-${endIndex} 条，共 ${totalItems} 条数据`;
        if (currentPageInput) currentPageInput.value = this.currentPage;
        if (totalPagesSpan) totalPagesSpan.textContent = this.totalPages;
        
        // 更新按钮状态
        if (firstPageBtn) firstPageBtn.disabled = this.currentPage === 1;
        if (prevPageBtn) prevPageBtn.disabled = this.currentPage === 1;
        if (nextPageBtn) nextPageBtn.disabled = this.currentPage === this.totalPages;
        if (lastPageBtn) lastPageBtn.disabled = this.currentPage === this.totalPages;
    }
    
    // 隐藏分页控件
    hidePagination() {
        const paginationContainer = this.safeGetElement('paginationContainer');
        if (paginationContainer) paginationContainer.style.display = 'none';
    }
    
    // 跳转到指定页面
    goToPage(page) {
        if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
            this.currentPage = page;
            this.displayData();
        }
    }
    
    // 滚动到标签筛选区域
    scrollToTagFilter() {
        const tagFilterCard = this.safeGetElement('tagFilterCard');
        if (tagFilterCard && tagFilterCard.style.display !== 'none') {
            // 先等待一小段时间确保DOM更新完成
            setTimeout(() => {
                // 平滑滚动到标签筛选区域，预留一些顶部空间
                const elementTop = tagFilterCard.getBoundingClientRect().top + window.pageYOffset;
                const offsetTop = elementTop - 80; // 预留80px的顶部空间
                
                window.scrollTo({
                    top: offsetTop,
                    behavior: 'smooth'
                });
                
                // 添加高亮效果来吸引注意力
                tagFilterCard.classList.add('highlight');
                tagFilterCard.style.boxShadow = '0 0 20px rgba(74, 144, 226, 0.3)';
                
                // 3秒后移除高亮效果
                setTimeout(() => {
                    tagFilterCard.classList.remove('highlight');
                    tagFilterCard.style.boxShadow = '';
                }, 3000);
                
            }, 100);
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.domainTagsManager = new DomainTagsManager();
}); 