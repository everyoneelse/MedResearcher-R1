// 最终数据管理页面JavaScript

class FinalDataManager {
    constructor() {
        this.allData = [];
        this.filteredData = [];
        this.currentView = 'card'; // 'card' or 'table'
        this.currentPage = 1;
        this.pageSize = 20;
        this.filters = {
            question: '',
            answer: '',
            reasoning: '',
            language: [],
            domainTags: [],
            domainTagsLogic: 'or',
            entities: [],
            entitiesLogic: 'or',
            source: []
        };
        this.visibleFields = {
            unique_id: true,
            question: true,
            answer: true,
            language: true,
            domain_tags: true,
            entities: false,
            entity_mapping: false,
            reasoning_path: false,
            mapped_reasoning_path: false,
            source: false
        };
        this.fieldLabels = {
            unique_id: '唯一ID',
            question: '问题',
            answer: '答案',
            language: '语言',
            domain_tags: '领域标签',
            entities: '实体列表',
            entity_mapping: '实体映射',
            reasoning_path: '推理路径',
            mapped_reasoning_path: '映射推理路径',
            source: '数据源'
        };

        this.init();
    }

    async init() {
        this.loadUserPreferences();
        this.bindEvents();
        this.setupFieldControls();
        await this.loadData();
        this.applyFilters();
        this.renderData();
    }

    bindEvents() {
        // 视图切换
        document.getElementById('tableViewBtn').addEventListener('click', () => this.switchView('table'));
        document.getElementById('cardViewBtn').addEventListener('click', () => this.switchView('card'));

        // 筛选事件
        document.getElementById('questionFilter').addEventListener('input', debounce(() => this.updateFilter(), 300));
        document.getElementById('answerFilter').addEventListener('input', debounce(() => this.updateFilter(), 300));
        document.getElementById('reasoningFilter').addEventListener('input', debounce(() => this.updateFilter(), 300));

        // 多选筛选
        document.getElementById('languageFilter').addEventListener('change', () => this.updateFilter());
        document.getElementById('domainTagsFilter').addEventListener('change', () => this.updateFilter());
        document.getElementById('entitiesFilter').addEventListener('change', () => this.updateFilter());
        document.getElementById('sourceFilter').addEventListener('change', () => this.updateFilter());

        // 逻辑关系切换
        document.querySelectorAll('input[name="domainTagsLogic"]').forEach(radio => {
            radio.addEventListener('change', () => this.updateFilter());
        });
        document.querySelectorAll('input[name="entitiesLogic"]').forEach(radio => {
            radio.addEventListener('change', () => this.updateFilter());
        });

        // 字段控制
        document.getElementById('fieldControlBtn').addEventListener('click', () => this.toggleFieldControl());
        document.getElementById('selectAllFields').addEventListener('click', () => this.selectAllFields());
        document.getElementById('selectNoneFields').addEventListener('click', () => this.selectNoneFields());
        document.getElementById('resetDefaultFields').addEventListener('click', () => this.resetDefaultFields());

        // 其他操作
        document.getElementById('clearFiltersBtn').addEventListener('click', () => this.clearFilters());
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadData());
        document.getElementById('exportBtn').addEventListener('click', () => this.exportData());
        document.getElementById('generateIdsBtn').addEventListener('click', () => this.generateMissingIds());
        document.getElementById('checkDuplicatesBtn').addEventListener('click', () => this.checkDuplicateIds());
        document.getElementById('cleanDirtyBtn').addEventListener('click', () => this.cleanDirtyIds());
        
        // 页面大小控制
        document.getElementById('pageSizeSelect').addEventListener('change', (e) => this.changePageSize(parseInt(e.target.value)));

        // 事件委托 - 处理动态生成的按钮
        const self = this; // 保存this引用
        document.addEventListener('click', (e) => {
            // 详情按钮
            if (e.target.classList.contains('detail-btn')) {
                const uniqueId = e.target.getAttribute('data-unique-id');
                if (uniqueId) {
                    console.log('Detail button clicked, uniqueId:', uniqueId);
                    self.showDetail(uniqueId);
                }
            }
            
            // 展开按钮
            if (e.target.classList.contains('expand-btn') || e.target.classList.contains('table-expand-btn')) {
                const targetId = e.target.getAttribute('data-target');
                if (targetId) {
                    console.log('Expand button clicked, targetId:', targetId);
                    self.toggleExpand(targetId);
                }
            }
            
            // 分页按钮
            if (e.target.classList.contains('page-btn')) {
                e.preventDefault();
                const page = parseInt(e.target.getAttribute('data-page'));
                if (page && !isNaN(page)) {
                    console.log('Page button clicked, page:', page);
                    self.goToPage(page);
                }
            }
        });
    }

    setupFieldControls() {
        const checkboxContainer = document.getElementById('fieldCheckboxes');
        checkboxContainer.innerHTML = '';

        Object.keys(this.fieldLabels).forEach(fieldKey => {
            const colDiv = document.createElement('div');
            colDiv.className = 'col-md-3';
            
            const checkboxDiv = document.createElement('div');
            checkboxDiv.className = 'field-checkbox';
            
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `field_${fieldKey}`;
            checkbox.checked = this.visibleFields[fieldKey];
            checkbox.addEventListener('change', () => {
                this.visibleFields[fieldKey] = checkbox.checked;
                this.saveFieldPreferences();
                this.renderData();
            });
            
            const label = document.createElement('label');
            label.htmlFor = `field_${fieldKey}`;
            label.textContent = this.fieldLabels[fieldKey];
            
            checkboxDiv.appendChild(checkbox);
            checkboxDiv.appendChild(label);
            colDiv.appendChild(checkboxDiv);
            checkboxContainer.appendChild(colDiv);
        });
    }

    async loadData() {
        try {
            this.showLoading(true);
            
            const response = await fetch('/api/final_datasets/load');
            const result = await response.json();
            
            if (result.success) {
                // 直接使用后端返回的数据，不在前端自动生成ID
                this.allData = result.data;
                
                this.updateStats();
                this.populateFilterOptions();
                this.applyFilters();
                this.renderData();
            } else {
                throw new Error(result.error || '加载数据失败');
            }
        } catch (error) {
            console.error('加载数据错误:', error);
            this.showError('加载数据失败: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }



    populateFilterOptions() {
        // 填充语言选项
        const languages = [...new Set(this.allData.map(item => item.question_language || item.answer_language).filter(Boolean))];
        this.populateSelect('languageFilter', languages);

        // 填充领域标签选项
        const domainTags = [...new Set(this.allData.flatMap(item => item.domain_tags || []))];
        this.populateSelect('domainTagsFilter', domainTags);

        // 填充实体选项（从entity_mapping中提取）
        const entities = [...new Set(this.allData.flatMap(item => {
            if (item.entity_mapping && typeof item.entity_mapping === 'object') {
                return Object.values(item.entity_mapping);
            }
            return [];
        }))];
        this.populateSelect('entitiesFilter', entities.slice(0, 100)); // 限制选项数量

        // 填充数据源选项（从文件名推断）
        const sources = [...new Set(this.allData.map(item => item.source).filter(Boolean))];
        this.populateSelect('sourceFilter', sources);
    }

    populateSelect(selectId, options) {
        const select = document.getElementById(selectId);
        select.innerHTML = '';
        
        options.sort().forEach(option => {
            const optionElement = document.createElement('option');
            optionElement.value = option;
            optionElement.textContent = option;
            select.appendChild(optionElement);
        });
    }

    updateFilter() {
        // 更新筛选条件
        this.filters.question = document.getElementById('questionFilter').value.trim();
        this.filters.answer = document.getElementById('answerFilter').value.trim();
        this.filters.reasoning = document.getElementById('reasoningFilter').value.trim();
        
        this.filters.language = Array.from(document.getElementById('languageFilter').selectedOptions).map(opt => opt.value);
        this.filters.domainTags = Array.from(document.getElementById('domainTagsFilter').selectedOptions).map(opt => opt.value);
        this.filters.entities = Array.from(document.getElementById('entitiesFilter').selectedOptions).map(opt => opt.value);
        this.filters.source = Array.from(document.getElementById('sourceFilter').selectedOptions).map(opt => opt.value);
        
        this.filters.domainTagsLogic = document.querySelector('input[name="domainTagsLogic"]:checked').value;
        this.filters.entitiesLogic = document.querySelector('input[name="entitiesLogic"]:checked').value;

        this.applyFilters();
        this.renderData();
    }

    applyFilters() {
        this.filteredData = this.allData.filter(item => {
            // 文本搜索筛选
            if (this.filters.question && !this.containsText(item.question, this.filters.question)) return false;
            if (this.filters.answer && !this.containsText(item.answer, this.filters.answer)) return false;
            if (this.filters.reasoning && !this.containsText(item.reasoning_path || item.mapped_reasoning_path, this.filters.reasoning)) return false;

            // 语言筛选
            if (this.filters.language.length > 0) {
                const itemLanguage = item.question_language || item.answer_language;
                if (!this.filters.language.includes(itemLanguage)) return false;
            }

            // 领域标签筛选
            if (this.filters.domainTags.length > 0) {
                const itemTags = item.domain_tags || [];
                if (this.filters.domainTagsLogic === 'or') {
                    if (!this.filters.domainTags.some(tag => itemTags.includes(tag))) return false;
                } else {
                    if (!this.filters.domainTags.every(tag => itemTags.includes(tag))) return false;
                }
            }

            // 实体筛选
            if (this.filters.entities.length > 0) {
                const itemEntities = item.entity_mapping ? Object.values(item.entity_mapping) : [];
                if (this.filters.entitiesLogic === 'or') {
                    if (!this.filters.entities.some(entity => itemEntities.includes(entity))) return false;
                } else {
                    if (!this.filters.entities.every(entity => itemEntities.includes(entity))) return false;
                }
            }

            // 数据源筛选
            if (this.filters.source.length > 0) {
                if (!this.filters.source.includes(item.source)) return false;
            }

            return true;
        });

        this.updateStats();
        this.currentPage = 1; // 重置到第一页
    }

    containsText(text, searchTerm) {
        if (!text || !searchTerm) return true;
        return text.toLowerCase().includes(searchTerm.toLowerCase());
    }

    switchView(viewType) {
        this.currentView = viewType;
        
        // 更新按钮状态
        document.getElementById('tableViewBtn').classList.toggle('active', viewType === 'table');
        document.getElementById('cardViewBtn').classList.toggle('active', viewType === 'card');
        
        // 切换视图显示
        document.getElementById('tableView').classList.toggle('d-none', viewType !== 'table');
        document.getElementById('cardView').classList.toggle('d-none', viewType !== 'card');
        
        this.renderData();
    }

    renderData() {
        const startIndex = (this.currentPage - 1) * this.pageSize;
        const endIndex = startIndex + this.pageSize;
        const pageData = this.filteredData.slice(startIndex, endIndex);

        if (this.currentView === 'card') {
            this.renderCardView(pageData);
        } else {
            this.renderTableView(pageData);
        }

        this.renderPagination();
    }

    renderCardView(data) {
        const container = document.getElementById('cardContainer');
        
        if (data.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="empty-state">
                        <i class="fas fa-search"></i>
                        <h5>没有找到匹配的数据</h5>
                        <p>请调整筛选条件或清空筛选重新搜索</p>
                    </div>
                </div>
            `;
            return;
        }

        container.innerHTML = data.map(item => {
            const visibleFieldsHtml = Object.keys(this.visibleFields)
                .filter(field => this.visibleFields[field] && field !== 'unique_id')
                .map(field => this.renderCardField(field, item[field]))
                .join('');

            return `
                <div class="col-lg-6 col-xl-4">
                    <div class="data-card">
                        <div class="data-card-header">
                            <div class="data-card-id">${item.unique_id}</div>
                            <div class="data-card-language">${item.question_language || item.answer_language || 'unknown'}</div>
                        </div>
                        ${visibleFieldsHtml}
                    </div>
                </div>
            `;
        }).join('');
    }

    renderCardField(fieldKey, value) {
        if (!value) return '';

        let displayValue = '';
        const label = this.fieldLabels[fieldKey];

        if (fieldKey === 'domain_tags' && Array.isArray(value)) {
            displayValue = value.map(tag => `<span class="tag domain-tag">${tag}</span>`).join('');
        } else if (fieldKey === 'entity_mapping' && typeof value === 'object') {
            const entities = Object.values(value).slice(0, 5);
            displayValue = entities.map(entity => `<span class="tag entity-tag">${entity}</span>`).join('');
            if (Object.values(value).length > 5) {
                displayValue += `<span class="tag">+${Object.values(value).length - 5} more</span>`;
            }
        } else if (typeof value === 'string') {
            const truncated = value.length > 150;
            const fieldId = `field_${fieldKey}_${Math.random().toString(36).substr(2, 9)}`;
            displayValue = `
                <div class="data-card-field-content ${truncated ? 'truncated' : ''}" id="${fieldId}" data-full-content="${this.escapeHtml(value)}">
                    ${this.highlightSearch(value.substring(0, truncated ? 150 : value.length))}
                    ${truncated ? '...' : ''}
                </div>
                ${truncated ? `<div class="expand-btn" data-target="${fieldId}" onclick="window.finalDataManager && window.finalDataManager.toggleExpand('${fieldId}')">展开</div>` : ''}
            `;
        } else {
            displayValue = String(value);
        }

        return `
            <div class="data-card-field">
                <div class="data-card-field-label">${label}</div>
                ${displayValue}
            </div>
        `;
    }

    renderTableView(data) {
        const table = document.getElementById('dataTable');
        const headers = document.getElementById('tableHeaders');
        const body = document.getElementById('tableBody');

        // 渲染表头
        const visibleFields = Object.keys(this.visibleFields).filter(field => this.visibleFields[field]);
        headers.innerHTML = visibleFields.map(field => `<th>${this.fieldLabels[field]}</th>`).join('') + '<th>操作</th>';

        // 渲染表格内容
        if (data.length === 0) {
            body.innerHTML = `
                <tr>
                    <td colspan="${visibleFields.length + 1}" class="text-center">
                        <div class="empty-state">
                            <i class="fas fa-search"></i>
                            <h5>没有找到匹配的数据</h5>
                            <p>请调整筛选条件或清空筛选重新搜索</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        body.innerHTML = data.map(item => {
            const cells = visibleFields.map(field => {
                return `<td>${this.renderTableCell(field, item[field])}</td>`;
            }).join('');
            
            return `
                <tr>
                    ${cells}
                </tr>
            `;
        }).join('');
    }

    renderTableCell(fieldKey, value) {
        if (!value) return '-';

        if (fieldKey === 'domain_tags' && Array.isArray(value)) {
            return value.slice(0, 3).map(tag => `<span class="tag domain-tag">${tag}</span>`).join('') +
                   (value.length > 3 ? `<span class="tag">+${value.length - 3}</span>` : '');
        } else if (fieldKey === 'entity_mapping' && typeof value === 'object') {
            const entities = Object.values(value).slice(0, 2);
            return entities.map(entity => `<span class="tag entity-tag">${entity}</span>`).join('') +
                   (Object.values(value).length > 2 ? `<span class="tag">+${Object.values(value).length - 2}</span>` : '');
        } else if (typeof value === 'string') {
            const truncated = value.length > 100;
            const cellId = `cell_${fieldKey}_${Math.random().toString(36).substr(2, 9)}`;
            return `
                <div class="table-cell-content ${truncated ? 'truncated' : ''}" id="${cellId}" data-full-content="${this.escapeHtml(value)}">
                    ${this.highlightSearch(value.substring(0, truncated ? 100 : value.length))}
                    ${truncated ? '...' : ''}
                    ${truncated ? `<div class="table-expand-btn" data-target="${cellId}" onclick="window.finalDataManager && window.finalDataManager.toggleExpand('${cellId}')">展开</div>` : ''}
                </div>
            `;
        }

        return String(value);
    }

    highlightSearch(text) {
        if (!text) return '';
        
        const searchTerms = [this.filters.question, this.filters.answer, this.filters.reasoning]
            .filter(term => term && term.length > 0);
            
        if (searchTerms.length === 0) return text;

        let highlightedText = text;
        searchTerms.forEach(term => {
            const regex = new RegExp(`(${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
            highlightedText = highlightedText.replace(regex, '<span class="search-highlight">$1</span>');
        });

        return highlightedText;
    }

    showDetail(uniqueId) {
        const item = this.allData.find(d => d.unique_id === uniqueId);
        if (!item) {
            console.warn('Item not found:', uniqueId);
            return;
        }

        const modalContent = document.getElementById('dataDetailContent');
        if (!modalContent) {
            console.error('Modal content element not found');
            return;
        }

        modalContent.innerHTML = Object.keys(this.fieldLabels).map(field => {
            const value = item[field];
            if (!value) return '';

            let displayValue = '';
            if (typeof value === 'object') {
                displayValue = `<pre>${JSON.stringify(value, null, 2)}</pre>`;
            } else {
                displayValue = this.escapeHtml(String(value));
            }

            return `
                <div class="detail-field">
                    <div class="detail-field-label">${this.fieldLabels[field]}</div>
                    <div class="detail-field-content">${displayValue}</div>
                </div>
            `;
        }).join('');

        const modalElement = document.getElementById('dataDetailModal');
        if (!modalElement) {
            console.error('Modal element not found');
            return;
        }

        // 检查是否有Bootstrap
        if (typeof bootstrap !== 'undefined' && bootstrap.Modal) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
        } else {
            // 备选方案：直接显示模态框
            modalElement.style.display = 'block';
            modalElement.classList.add('show');
            document.body.classList.add('modal-open');
            
            // 添加背景遮罩
            const backdrop = document.createElement('div');
            backdrop.className = 'modal-backdrop fade show';
            backdrop.id = 'modal-backdrop-temp';
            document.body.appendChild(backdrop);
            
            // 点击关闭按钮或遮罩关闭模态框
            const closeModal = () => {
                modalElement.style.display = 'none';
                modalElement.classList.remove('show');
                document.body.classList.remove('modal-open');
                const tempBackdrop = document.getElementById('modal-backdrop-temp');
                if (tempBackdrop) {
                    tempBackdrop.remove();
                }
            };
            
            // 绑定关闭事件
            modalElement.querySelectorAll('[data-bs-dismiss="modal"]').forEach(btn => {
                btn.onclick = closeModal;
            });
            backdrop.onclick = closeModal;
        }
    }

    toggleExpand(elementId) {
        console.log('toggleExpand called with elementId:', elementId);
        const element = document.getElementById(elementId);
        if (!element) {
            console.warn('Element not found:', elementId);
            return;
        }

        const isExpanded = element.classList.contains('expanded');
        const fullContent = element.getAttribute('data-full-content');
        
        console.log('Element found, isExpanded:', isExpanded, 'hasFullContent:', !!fullContent);
        
        if (!fullContent) {
            console.warn('No full content data found for element:', elementId);
            return;
        }
        
        if (isExpanded) {
            // 收起：恢复截断状态
            element.classList.remove('expanded');
            element.classList.add('truncated');
            // 判断是表格还是卡片，使用不同的截断长度
            const isTableCell = element.classList.contains('table-cell-content');
            const truncateLength = isTableCell ? 100 : 150;
            element.innerHTML = this.highlightSearch(fullContent.substring(0, truncateLength)) + '...';
        } else {
            // 展开：显示完整内容
            element.classList.add('expanded');
            element.classList.remove('truncated');
            element.innerHTML = this.highlightSearch(fullContent);
        }
        
        // 更新按钮文本
        const expandBtn = element.parentElement.querySelector('.expand-btn, .table-expand-btn');
        if (expandBtn) {
            expandBtn.textContent = element.classList.contains('expanded') ? '收起' : '展开';
            console.log('Button text updated to:', expandBtn.textContent);
        } else {
            console.warn('Expand button not found');
        }
    }

    renderPagination() {
        const totalPages = Math.ceil(this.filteredData.length / this.pageSize);
        const pagination = document.getElementById('paginationControls');
        const paginationInfo = document.getElementById('paginationInfo');

        // 更新分页信息
        const startIndex = (this.currentPage - 1) * this.pageSize + 1;
        const endIndex = Math.min(this.currentPage * this.pageSize, this.filteredData.length);
        
        if (this.filteredData.length > 0) {
            paginationInfo.textContent = `显示第 ${startIndex} - ${endIndex} 条，共 ${this.filteredData.length} 条`;
        } else {
            paginationInfo.textContent = '暂无数据';
        }

        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        let paginationHtml = '';
        
        // 上一页
        paginationHtml += `
            <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link page-btn" href="#" data-page="${this.currentPage - 1}">上一页</a>
            </li>
        `;

        // 页码
        const start = Math.max(1, this.currentPage - 2);
        const end = Math.min(totalPages, this.currentPage + 2);

        if (start > 1) {
            paginationHtml += `<li class="page-item"><a class="page-link page-btn" href="#" data-page="1">1</a></li>`;
            if (start > 2) paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }

        for (let i = start; i <= end; i++) {
            paginationHtml += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link page-btn" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }

        if (end < totalPages) {
            if (end < totalPages - 1) paginationHtml += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
            paginationHtml += `<li class="page-item"><a class="page-link page-btn" href="#" data-page="${totalPages}">${totalPages}</a></li>`;
        }

        // 下一页
        paginationHtml += `
            <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link page-btn" href="#" data-page="${this.currentPage + 1}">下一页</a>
            </li>
        `;

        pagination.innerHTML = paginationHtml;
    }

    goToPage(page) {
        const totalPages = Math.ceil(this.filteredData.length / this.pageSize);
        if (page < 1 || page > totalPages) return;
        
        this.currentPage = page;
        this.renderData();
    }

    updateStats() {
        document.getElementById('totalCount').textContent = this.allData.length.toLocaleString();
        document.getElementById('filteredCount').textContent = this.filteredData.length.toLocaleString();
        
        const fileCount = [...new Set(this.allData.map(item => item.source))].length;
        document.getElementById('fileCount').textContent = fileCount;
        
        // 计算缺少唯一ID的数量（检查字段不存在或值为空）
        const missingIdCount = this.allData.filter(item => !item.unique_id || item.unique_id.trim() === '').length;
        document.getElementById('missingIdCount').textContent = missingIdCount;
        
        // 更新生成ID按钮的状态和文本
        const generateBtn = document.getElementById('generateIdsBtn');
        if (generateBtn) {
            if (missingIdCount > 0) {
                generateBtn.innerHTML = `<i class="fas fa-fingerprint"></i> 生成ID (${missingIdCount})`;
                generateBtn.classList.remove('btn-success');
                generateBtn.classList.add('btn-warning');
                generateBtn.disabled = false;
                generateBtn.title = `为${missingIdCount}条缺少ID的数据生成唯一标识符`;
            } else {
                generateBtn.innerHTML = `<i class="fas fa-check"></i> 全部已有ID`;
                generateBtn.classList.remove('btn-warning');
                generateBtn.classList.add('btn-success');
                generateBtn.disabled = true;
                generateBtn.title = '所有数据都已经有唯一ID';
            }
        }
    }

    changePageSize(newSize) {
        this.pageSize = newSize;
        this.currentPage = 1; // 重置到第一页
        this.renderData();
        
        // 保存用户偏好
        localStorage.setItem('finalDataPageSize', newSize.toString());
    }

    toggleFieldControl() {
        const panel = document.getElementById('fieldControlPanel');
        panel.classList.toggle('d-none');
    }

    selectAllFields() {
        Object.keys(this.visibleFields).forEach(field => {
            this.visibleFields[field] = true;
            document.getElementById(`field_${field}`).checked = true;
        });
        this.saveFieldPreferences();
        this.renderData();
    }

    selectNoneFields() {
        Object.keys(this.visibleFields).forEach(field => {
            this.visibleFields[field] = false;
            document.getElementById(`field_${field}`).checked = false;
        });
        this.saveFieldPreferences();
        this.renderData();
    }

    resetDefaultFields() {
        const defaultFields = {
            unique_id: true,
            question: true,
            answer: true,
            language: true,
            domain_tags: true,
            entities: false,
            entity_mapping: false,
            reasoning_path: false,
            mapped_reasoning_path: false,
            source: false
        };
        
        Object.keys(defaultFields).forEach(field => {
            this.visibleFields[field] = defaultFields[field];
            document.getElementById(`field_${field}`).checked = defaultFields[field];
        });
        this.saveFieldPreferences();
        this.renderData();
    }

    clearFilters() {
        // 清空文本筛选
        document.getElementById('questionFilter').value = '';
        document.getElementById('answerFilter').value = '';
        document.getElementById('reasoningFilter').value = '';
        
        // 清空多选筛选
        document.getElementById('languageFilter').selectedIndex = -1;
        document.getElementById('domainTagsFilter').selectedIndex = -1;
        document.getElementById('entitiesFilter').selectedIndex = -1;
        document.getElementById('sourceFilter').selectedIndex = -1;
        
        // 重置逻辑关系
        document.getElementById('domainTagsOr').checked = true;
        document.getElementById('entitiesOr').checked = true;
        
        this.updateFilter();
    }

    async exportData() {
        try {
            const dataToExport = this.filteredData.map(item => {
                const exportItem = {};
                Object.keys(this.visibleFields).forEach(field => {
                    if (this.visibleFields[field]) {
                        exportItem[field] = item[field];
                    }
                });
                return exportItem;
            });

            const blob = new Blob([JSON.stringify(dataToExport, null, 2)], {
                type: 'application/json'
            });
            
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `final_datasets_export_${new Date().toISOString().slice(0, 10)}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('导出数据错误:', error);
            alert('导出数据失败: ' + error.message);
        }
    }

    async generateMissingIds() {
        const missingCount = this.allData.filter(item => !item.unique_id || item.unique_id.trim() === '').length;
        
        if (missingCount === 0) {
            alert('所有数据都已经有唯一ID，无需生成！');
            return;
        }
        
        if (!confirm(`将为 ${missingCount} 条缺少唯一ID的数据项生成ID并保存到文件。\n\n✅ 已有ID的数据不会被覆盖\n⚠️ 此操作会直接修改原始文件\n\n是否继续？`)) {
            return;
        }

        const button = document.getElementById('generateIdsBtn');
        const originalText = button.innerHTML;
        
        try {
            // 显示加载状态
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在生成...';
            
            const response = await fetch('/api/final_datasets/generate_missing_ids', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                const stats = result.stats;
                let message = `✅ 批量生成ID完成！\n\n`;
                message += `总共生成了 ${stats.total_generated} 个唯一ID\n`;
                message += `更新了 ${stats.updated_files.length} 个文件\n\n`;
                
                if (stats.updated_files.length > 0) {
                    message += `详细信息：\n`;
                    stats.updated_files.forEach(file => {
                        message += `• ${file.file}: 生成了 ${file.generated_count} 个ID\n`;
                    });
                }
                
                alert(message);
                
                // 重新加载数据以显示新生成的ID
                await this.loadData();
                this.applyFilters();
                this.renderData();
            } else {
                throw new Error(result.error || '生成ID失败');
            }
        } catch (error) {
            console.error('生成ID错误:', error);
            alert('生成ID失败: ' + error.message);
        } finally {
            // 恢复按钮的加载状态，但具体的启用/禁用状态由updateStats决定
            // 因为loadData()会调用updateStats()，所以这里不需要手动设置disabled状态
        }
    }

    async checkDuplicateIds() {
        const button = document.getElementById('checkDuplicatesBtn');
        const originalText = button.innerHTML;
        
        try {
            // 显示加载状态
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 检查中...';
            
            const response = await fetch('/api/final_datasets/check_duplicates');
            const result = await response.json();
            
            if (result.success) {
                const stats = result.stats;
                const duplicates = result.duplicates;
                
                let message = `🔍 ID重复检查报告\n\n`;
                message += `📊 统计信息：\n`;
                message += `• 总ID数量: ${stats.total_ids}\n`;
                message += `• 唯一ID数量: ${stats.unique_ids}\n`;
                message += `• 重复ID数量: ${stats.duplicate_count}\n`;
                message += `• 缺少ID数量: ${stats.missing_ids}\n\n`;
                
                if (stats.duplicate_count > 0) {
                    message += `⚠️ 发现重复ID：\n`;
                    Object.keys(duplicates).slice(0, 5).forEach(dupId => {
                        const info = duplicates[dupId];
                        message += `• ${dupId} (重复${info.count}次)\n`;
                        info.sources.forEach(source => {
                            message += `  - ${source.file}:${source.line} "${source.question}"\n`;
                        });
                    });
                    
                    if (Object.keys(duplicates).length > 5) {
                        message += `... 还有 ${Object.keys(duplicates).length - 5} 个重复ID\n`;
                    }
                } else {
                    message += `✅ 没有发现重复ID！`;
                }
                
                alert(message);
            } else {
                throw new Error(result.error || '检查重复失败');
            }
        } catch (error) {
            console.error('检查重复错误:', error);
            alert('检查重复失败: ' + error.message);
        } finally {
            // 恢复按钮状态
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    async cleanDirtyIds() {
        if (!confirm('将清理普通版本文件中的脏数据（unique_id字段）。\n\n⚠️ 仅清理有对应with_tags版本的文件\n⚠️ 此操作会直接修改原始文件\n\n是否继续？')) {
            return;
        }

        const button = document.getElementById('cleanDirtyBtn');
        const originalText = button.innerHTML;
        
        try {
            // 显示加载状态
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 清理中...';
            
            const response = await fetch('/api/final_datasets/clean_dirty_ids', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                const stats = result.stats;
                
                let message = `🧹 脏数据清理完成！\n\n`;
                message += `📊 清理统计：\n`;
                message += `• 扫描文件数: ${stats.scanned_files}\n`;
                message += `• 清理文件数: ${stats.cleaned_files.length}\n`;
                message += `• 清理ID总数: ${stats.total_cleaned}\n\n`;
                
                if (stats.cleaned_files.length > 0) {
                    message += `📄 清理详情：\n`;
                    stats.cleaned_files.forEach(file => {
                        message += `• ${file.file}: 清理了 ${file.cleaned_count} 个ID\n`;
                    });
                } else {
                    message += `✅ 没有发现需要清理的脏数据！`;
                }
                
                alert(message);
                
                // 重新加载数据以显示更新后的状态
                await this.loadData();
                this.applyFilters();
                this.renderData();
            } else {
                throw new Error(result.error || '清理脏数据失败');
            }
        } catch (error) {
            console.error('清理脏数据错误:', error);
            alert('清理脏数据失败: ' + error.message);
        } finally {
            // 恢复按钮状态
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    saveFieldPreferences() {
        localStorage.setItem('finalDataFieldPreferences', JSON.stringify(this.visibleFields));
    }

    loadUserPreferences() {
        // 加载页面大小偏好
        const savedPageSize = localStorage.getItem('finalDataPageSize');
        if (savedPageSize) {
            this.pageSize = parseInt(savedPageSize);
            // 设置选择器的值
            setTimeout(() => {
                const pageSizeSelect = document.getElementById('pageSizeSelect');
                if (pageSizeSelect) {
                    pageSizeSelect.value = savedPageSize;
                }
            }, 0);
        }

        // 加载字段显示偏好
        this.loadFieldPreferences();
    }

    loadFieldPreferences() {
        const saved = localStorage.getItem('finalDataFieldPreferences');
        if (saved) {
            try {
                this.visibleFields = { ...this.visibleFields, ...JSON.parse(saved) };
            } catch (error) {
                console.error('加载字段偏好设置失败:', error);
            }
        }
    }

    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        const dataArea = document.getElementById('dataDisplayArea');
        
        if (show) {
            spinner.style.display = 'block';
            dataArea.style.display = 'none';
        } else {
            spinner.style.display = 'none';
            dataArea.style.display = 'block';
        }
    }

    showError(message) {
        // 可以使用toast或alert显示错误
        alert(message);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// 工具函数
function debounce(func, wait) {
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

// 初始化
let finalDataManager;

// 确保全局变量在各种情况下都可用
function initializeFinalDataManager() {
    console.log('Initializing FinalDataManager...');
    try {
        finalDataManager = new FinalDataManager();
        window.finalDataManager = finalDataManager;
        console.log('FinalDataManager initialized successfully and available globally');
        
        // 测试一下实例方法是否可用
        if (typeof finalDataManager.showDetail === 'function') {
            console.log('showDetail method is available');
        }
        if (typeof finalDataManager.toggleExpand === 'function') {
            console.log('toggleExpand method is available');
        }
    } catch (error) {
        console.error('Error initializing FinalDataManager:', error);
    }
}

// 多种方式确保初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeFinalDataManager);
} else {
    // DOM已经加载完成
    initializeFinalDataManager();
}

// 备用初始化
window.addEventListener('load', () => {
    if (!window.finalDataManager) {
        console.log('Backup initialization...');
        initializeFinalDataManager();
    }
}); 