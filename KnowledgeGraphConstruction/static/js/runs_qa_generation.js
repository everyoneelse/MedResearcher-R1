// Runs记录QA生成页面JavaScript

class RunsQAGenerator {
    constructor() {
        this.socket = io();
        this.selectedRuns = new Set();
        this.availableRuns = [];
        this.currentTask = null;
        
        this.initializeEventListeners();
        this.loadRuns();
    }
    
    initializeEventListeners() {
        // 刷新按钮
        document.getElementById('refresh-runs').addEventListener('click', () => {
            this.loadRuns();
        });
        
        // 搜索过滤
        document.getElementById('search-runs').addEventListener('input', (e) => {
            this.filterRuns(e.target.value);
        });
        
        // 类型过滤
        document.getElementById('filter-type').addEventListener('change', (e) => {
            this.filterRunsByType(e.target.value);
        });
        
        // 时间筛选相关事件
        // 快捷时间按钮
        document.querySelectorAll('.quick-time-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.setQuickTimeRange(parseInt(e.target.dataset.hours), e.target);
            });
        });
        
        // 应用时间筛选
        document.getElementById('apply-time-filter').addEventListener('click', () => {
            this.applyTimeFilter();
        });
        
        // 选择时间段内所有记录
        document.getElementById('select-in-range').addEventListener('click', () => {
            this.selectAllInTimeRange();
        });
        
        // 清除时间筛选
        document.getElementById('clear-time-filter').addEventListener('click', () => {
            this.clearTimeFilter();
        });
        
        // 时间输入框变化时自动更新筛选
        document.getElementById('start-date').addEventListener('change', () => {
            this.applyTimeFilter();
        });
        
        document.getElementById('end-date').addEventListener('change', () => {
            this.applyTimeFilter();
        });
        
        // 清空选择
        document.getElementById('clear-selection').addEventListener('click', () => {
            this.clearSelection();
        });
        
        // 预览图数据
        document.getElementById('preview-graph').addEventListener('click', () => {
            this.previewGraph();
        });
        
        // 开始生成
        document.getElementById('start-generation').addEventListener('click', () => {
            this.startGeneration();
        });
        
        // 模态框关闭
        document.querySelector('.modal-close').addEventListener('click', () => {
            this.closeModal();
        });
        
        document.querySelector('.modal-overlay').addEventListener('click', () => {
            this.closeModal();
        });
        
        // Socket事件监听
        this.socket.on('runs_qa_complete', (data) => {
            this.handleGenerationComplete(data);
        });
        
        // 监听进度更新事件
        this.socket.on('runs_qa_progress', (data) => {
            this.handleGenerationProgress(data);
        });
    }
    
    async loadRuns() {
        try {
            this.showLoading('runs-list', '正在加载运行记录...');
            
            const response = await fetch('/api/runs/list');
            const data = await response.json();
            
            if (data.success) {
                this.availableRuns = data.runs;
                this.displayRuns(data.runs);
            } else {
                this.showError('runs-list', `加载失败: ${data.error}`);
            }
        } catch (error) {
            console.error('加载运行记录失败:', error);
            this.showError('runs-list', '网络错误，请检查连接');
        }
    }
    
    displayRuns(runs) {
        const container = document.getElementById('runs-list');
        
        if (runs.length === 0) {
            container.innerHTML = `
                <div class="loading" style="animation: none;">
                    📂 暂无可用的运行记录
                </div>
            `;
            return;
        }
        
        container.innerHTML = runs.map(run => this.createRunItem(run)).join('');
        
        // 绑定点击事件
        container.querySelectorAll('.run-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.type !== 'checkbox') {
                    const checkbox = item.querySelector('.checkbox');
                    checkbox.checked = !checkbox.checked;
                }
                this.toggleRunSelection(item.dataset.runId);
            });
        });
    }
    
    createRunItem(run) {
        const isSelected = this.selectedRuns.has(run.run_id);
        const hasData = run.has_graph_data;
        
        const entitiesPreview = run.entities ? 
            run.entities.slice(0, 5).map(entity => 
                `<span class="entity-tag">${entity}</span>`
            ).join('') : '';
        
        const moreEntities = run.total_entities > 5 ? 
            `<span class="entity-tag">+${run.total_entities - 5}个</span>` : '';
        
        return `
            <div class="run-item ${isSelected ? 'selected' : ''}" data-run-id="${run.run_id}">
                <input type="checkbox" class="checkbox" ${isSelected ? 'checked' : ''} ${!hasData ? 'disabled' : ''}>
                <div class="run-info">
                    <div class="run-title">${run.run_id}</div>
                    <div class="run-meta">
                        <span>时间: ${this.formatTimestamp(run.timestamp)}</span>
                        <span class="run-badge ${hasData ? 'has-data' : 'no-data'}">
                            ${hasData ? '有图数据' : '无图数据'}
                        </span>
                        ${hasData ? `<span>文件: ${run.input_files_count}个</span>` : ''}
                        ${hasData ? `<span>实体: ${run.total_entities}个</span>` : ''}
                    </div>
                    ${entitiesPreview ? `
                        <div class="entity-preview">
                            ${entitiesPreview}
                            ${moreEntities}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    formatTimestamp(timestamp) {
        if (!timestamp) return '未知时间';
        
        try {
            // 假设时间戳格式为 YYYYMMDD_HHMMSS
            const match = timestamp.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
            if (match) {
                const [, year, month, day, hour, minute, second] = match;
                return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
            }
            return timestamp;
        } catch (error) {
            return timestamp;
        }
    }
    
    toggleRunSelection(runId) {
        const run = this.availableRuns.find(r => r.run_id === runId);
        if (!run || !run.has_graph_data) return;
        
        if (this.selectedRuns.has(runId)) {
            this.selectedRuns.delete(runId);
        } else {
            this.selectedRuns.add(runId);
        }
        
        this.updateUI();
    }
    
    clearSelection() {
        this.selectedRuns.clear();
        this.updateUI();
        this.displayRuns(this.availableRuns);
    }
    
    updateUI() {
        const count = this.selectedRuns.size;
        
        // 检查是否有时间筛选
        const startDateStr = document.getElementById('start-date').value;
        const endDateStr = document.getElementById('end-date').value;
        
        if (startDateStr || endDateStr) {
            // 有时间筛选时使用专门的更新方法
            const startTime = startDateStr ? new Date(startDateStr) : null;
            const endTime = endDateStr ? new Date(endDateStr) : null;
            const filtered = this.availableRuns.filter(run => 
                this.isRunInTimeRange(run, startTime, endTime)
            );
            this.updateTimeFilterInfo(filtered.length, startTime, endTime);
        } else {
            // 没有时间筛选时使用简单文本
            document.getElementById('selected-count').textContent = `已选择 ${count} 个运行记录`;
        }
        
        const hasSelection = count > 0;
        document.getElementById('preview-graph').disabled = !hasSelection;
        document.getElementById('start-generation').disabled = !hasSelection;
    }
    
    filterRuns(searchTerm) {
        const filtered = this.availableRuns.filter(run => 
            run.run_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            (run.entities && run.entities.some(entity => 
                entity.toLowerCase().includes(searchTerm.toLowerCase())
            ))
        );
        this.displayRuns(filtered);
    }
    
    filterRunsByType(type) {
        if (type === 'all') {
            this.displayRuns(this.availableRuns);
            return;
        }
        
        const filtered = this.availableRuns.filter(run => {
            const runId = run.run_id.toLowerCase();
            switch (type) {
                case 'kg_build':
                    return runId.includes('kg_build');
                case 'task':
                    return runId.includes('task_');
                case 'batch':
                    return runId.includes('batch_');
                default:
                    return true;
            }
        });
        
        this.displayRuns(filtered);
    }
    
    // 时间筛选相关方法
    
    /**
     * 设置快捷时间范围
     * @param {number} hours 从现在往前推的小时数
     * @param {HTMLElement} target 被点击的按钮元素
     */
    setQuickTimeRange(hours, target) {
        const now = new Date();
        const startTime = new Date(now.getTime() - hours * 60 * 60 * 1000);
        
        // 设置时间输入框的值
        document.getElementById('end-date').value = this.formatDateTimeLocal(now);
        document.getElementById('start-date').value = this.formatDateTimeLocal(startTime);
        
        // 更新快捷按钮状态
        document.querySelectorAll('.quick-time-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        target.classList.add('active');
        
        // 自动应用筛选
        this.applyTimeFilter();
    }
    
    /**
     * 格式化日期时间为datetime-local输入框格式
     * @param {Date} date 
     * @returns {string}
     */
    formatDateTimeLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    }
    
    /**
     * 应用时间筛选
     */
    applyTimeFilter() {
        const startDateStr = document.getElementById('start-date').value;
        const endDateStr = document.getElementById('end-date').value;
        
        if (!startDateStr && !endDateStr) {
            // 如果没有设置时间范围，显示所有记录
            this.displayRuns(this.availableRuns);
            return;
        }
        
        const startTime = startDateStr ? new Date(startDateStr) : null;
        const endTime = endDateStr ? new Date(endDateStr) : null;
        
        // 筛选在时间范围内的运行记录
        const filtered = this.availableRuns.filter(run => {
            return this.isRunInTimeRange(run, startTime, endTime);
        });
        
        this.displayRuns(filtered);
        
        // 更新选择计数器显示时间筛选信息
        this.updateTimeFilterInfo(filtered.length, startTime, endTime);
    }
    
    /**
     * 选择时间段内所有有效记录
     */
    selectAllInTimeRange() {
        const startDateStr = document.getElementById('start-date').value;
        const endDateStr = document.getElementById('end-date').value;
        
        if (!startDateStr && !endDateStr) {
            alert('请先设置时间范围');
            return;
        }
        
        const startTime = startDateStr ? new Date(startDateStr) : null;
        const endTime = endDateStr ? new Date(endDateStr) : null;
        
        // 清空当前选择
        this.selectedRuns.clear();
        
        // 选择时间范围内所有有图数据的记录
        this.availableRuns.forEach(run => {
            if (run.has_graph_data && this.isRunInTimeRange(run, startTime, endTime)) {
                this.selectedRuns.add(run.run_id);
            }
        });
        
        // 更新UI显示
        this.updateUI();
        this.displayRuns(this.availableRuns.filter(run => 
            this.isRunInTimeRange(run, startTime, endTime)
        ));
        
        // 显示选择结果
        const selectedCount = this.selectedRuns.size;
        const message = selectedCount > 0 
            ? `已选择 ${selectedCount} 个时间段内的运行记录`
            : '时间段内没有找到有效的运行记录';
        
        // 创建临时提示
        this.showTemporaryMessage(message, selectedCount > 0 ? 'success' : 'warning');
    }
    
    /**
     * 清除时间筛选
     */
    clearTimeFilter() {
        // 清空时间输入框
        document.getElementById('start-date').value = '';
        document.getElementById('end-date').value = '';
        
        // 清除快捷按钮状态
        document.querySelectorAll('.quick-time-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // 显示所有记录
        this.displayRuns(this.availableRuns);
        
        // 清除时间筛选信息
        this.updateTimeFilterInfo(0);
    }
    
    /**
     * 检查运行记录是否在指定时间范围内
     * @param {Object} run 运行记录
     * @param {Date|null} startTime 开始时间
     * @param {Date|null} endTime 结束时间
     * @returns {boolean}
     */
    isRunInTimeRange(run, startTime, endTime) {
        const runTime = this.parseTimestamp(run.timestamp);
        if (!runTime) return true; // 如果无法解析时间，则包含在结果中
        
        if (startTime && runTime < startTime) return false;
        if (endTime && runTime > endTime) return false;
        
        return true;
    }
    
    /**
     * 解析运行记录的时间戳
     * @param {string} timestamp 时间戳字符串
     * @returns {Date|null}
     */
    parseTimestamp(timestamp) {
        if (!timestamp) return null;
        
        try {
            // 处理格式 YYYYMMDD_HHMMSS
            const match = timestamp.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
            if (match) {
                const [, year, month, day, hour, minute, second] = match;
                return new Date(
                    parseInt(year),
                    parseInt(month) - 1, // 月份从0开始
                    parseInt(day),
                    parseInt(hour),
                    parseInt(minute),
                    parseInt(second)
                );
            }
            
            // 尝试其他常见格式
            return new Date(timestamp);
        } catch (error) {
            console.warn(`无法解析时间戳: ${timestamp}`);
            return null;
        }
    }
    
    /**
     * 更新时间筛选信息显示
     * @param {number} filteredCount 筛选后的记录数量
     * @param {Date|null} startTime 开始时间
     * @param {Date|null} endTime 结束时间
     */
    updateTimeFilterInfo(filteredCount, startTime = null, endTime = null) {
        const infoElement = document.getElementById('selected-count');
        
        if (filteredCount > 0 && (startTime || endTime)) {
            const timeRangeText = this.formatTimeRangeText(startTime, endTime);
            infoElement.innerHTML = `
                当前筛选: ${filteredCount} 个记录 ${timeRangeText}<br>
                已选择 ${this.selectedRuns.size} 个运行记录
            `;
        } else {
            infoElement.textContent = `已选择 ${this.selectedRuns.size} 个运行记录`;
        }
    }
    
    /**
     * 格式化时间范围文本
     * @param {Date|null} startTime 
     * @param {Date|null} endTime 
     * @returns {string}
     */
    formatTimeRangeText(startTime, endTime) {
        if (startTime && endTime) {
            return `(${startTime.toLocaleString()} ~ ${endTime.toLocaleString()})`;
        } else if (startTime) {
            return `(从 ${startTime.toLocaleString()})`;
        } else if (endTime) {
            return `(到 ${endTime.toLocaleString()})`;
        }
        return '';
    }
    
    /**
     * 显示临时消息
     * @param {string} message 消息文本
     * @param {string} type 消息类型 ('success', 'warning', 'error')
     */
    showTemporaryMessage(message, type = 'success') {
        // 创建消息元素
        const messageEl = document.createElement('div');
        messageEl.className = `temp-message temp-message-${type}`;
        messageEl.innerHTML = `
            <span>${message}</span>
            <button onclick="this.parentElement.remove()" style="margin-left: 12px; background: none; border: none; color: inherit; font-size: 16px; cursor: pointer;">&times;</button>
        `;
        
        // 添加样式
        messageEl.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 12px 16px;
            border-radius: 6px;
            color: white;
            font-weight: 500;
            z-index: 10000;
            animation: slideInRight 0.3s ease;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            max-width: 300px;
            word-wrap: break-word;
        `;
        
        // 设置背景色
        const colors = {
            success: '#10b981',
            warning: '#f59e0b',
            error: '#ef4444'
        };
        messageEl.style.backgroundColor = colors[type] || colors.success;
        
        // 添加到页面
        document.body.appendChild(messageEl);
        
        // 自动移除
        setTimeout(() => {
            if (messageEl.parentElement) {
                messageEl.style.animation = 'slideOutRight 0.3s ease';
                setTimeout(() => {
                    if (messageEl.parentElement) {
                        messageEl.remove();
                    }
                }, 300);
            }
        }, 3000);
    }
    
    async previewGraph() {
        if (this.selectedRuns.size === 0) return;
        
        const runId = Array.from(this.selectedRuns)[0]; // 预览第一个选中的
        
        try {
            document.getElementById('graph-preview-content').innerHTML = '<div class="loading">正在加载图数据...</div>';
            document.getElementById('graph-preview-modal').style.display = 'flex';
            
            const response = await fetch(`/api/runs/${runId}/graph`);
            const data = await response.json();
            
            if (data.success) {
                this.displayGraphPreview(data.graph_data);
            } else {
                document.getElementById('graph-preview-content').innerHTML = `
                    <div class="error">加载失败: ${data.error}</div>
                `;
            }
        } catch (error) {
            console.error('预览图数据失败:', error);
            document.getElementById('graph-preview-content').innerHTML = `
                <div class="error">网络错误，请检查连接</div>
            `;
        }
    }
    
    displayGraphPreview(graphData) {
        const { entities, relationships, node_count, relationship_count } = graphData;
        
        const content = `
            <div class="graph-preview-container">
                <div class="graph-stats">
                    <div class="stat-item">
                        <span class="stat-value">${node_count}</span>
                        <div class="stat-label">节点数</div>
                    </div>
                    <div class="stat-item">
                        <span class="stat-value">${relationship_count}</span>
                        <div class="stat-label">关系数</div>
                    </div>
                    <div class="stat-item">
                        <span class="stat-value">${graphData.source}</span>
                        <div class="stat-label">数据源</div>
                    </div>
                </div>
                
                <div class="graph-visualization-section">
                    <h4>🔗 图结构可视化</h4>
                    <div id="graph-viz" class="graph-viz-container">
                        <div class="graph-controls">
                            🔗 力导向图：滚轮缩放，拖拽平移，鼠标悬停查看详情
                        </div>
                    </div>
                    <div class="graph-legend">
                        <div class="legend-section">
                            <strong>节点类型：</strong>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #f59e0b;"></div>
                                <span>人物</span>
                            </div>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #3b82f6;"></div>
                                <span>组织</span>
                            </div>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #10b981;"></div>
                                <span>地点</span>
                            </div>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #8b5cf6;"></div>
                                <span>概念</span>
                            </div>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #ef4444;"></div>
                                <span>事件</span>
                            </div>
                            <div class="legend-item">
                                <div class="legend-color" style="background-color: #6b7280;"></div>
                                <span>其他</span>
                            </div>
                        </div>
                        <div class="legend-section">
                            <strong>节点大小：</strong>
                            <span style="margin-left: 8px;">⚪ 基础25px | ⭕ 连接多+15px | 📏 动态调整 | ➡️ 带箭头连线</span>
                        </div>
                    </div>
                </div>
                
                <div class="entities-section">
                    <h4>📋 实体列表 (${entities.length}个)</h4>
                    <div class="entities-list">
                        ${entities.map(entity => `
                            <div class="entity-item">
                                <span class="entity-name">${entity.name}</span>
                                <span class="entity-type">${entity.type}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
                
                <div class="debug-section">
                    <h4>🔍 图数据调试信息</h4>
                    <div class="debug-info">
                        <div class="debug-item">
                            <strong>总实体数：</strong> ${entities.length}
                        </div>
                        <div class="debug-item">
                            <strong>总关系数：</strong> ${relationships.length}
                        </div>
                        <div class="debug-item">
                            <strong>有效连接数：</strong> <span id="valid-links-count">计算中...</span>
                        </div>
                        <div class="debug-item">
                            <strong>关系示例：</strong> 
                            ${relationships.length > 0 ? 
                                relationships.slice(0, 3).map(rel => 
                                    `<code>${rel.source || rel.source_name || rel.head || rel.from || '?'} → ${rel.target || rel.target_name || rel.tail || rel.to || '?'}</code>`
                                ).join(', ') 
                                : '<em>暂无关系数据</em>'
                            }
                        </div>
                        <div class="debug-item">
                            <strong>连接示例：</strong> <span id="connection-examples">处理中...</span>
                        </div>
                        <div class="debug-item">
                            <strong>实体名称示例：</strong> 
                            ${entities.slice(0, 5).map(e => `<code>${e.name}</code>`).join(', ')}
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.getElementById('graph-preview-content').innerHTML = content;
        
        // 绘制图
        this.drawGraph(entities, relationships);
    }
    
        drawGraph(entities, relationships) {
        // 清理之前的SVG
        d3.select("#graph-viz").selectAll("*").remove();
        
        // 设置图的尺寸
        const container = document.getElementById('graph-viz');
        const width = container.clientWidth || 600;
        const height = 400;
        
        console.log('开始绘制图，实体数量:', entities.length, '关系数量:', relationships.length);
        
        // 创建SVG
        const svg = d3.select("#graph-viz")
            .append("svg")
            .attr("width", width)
            .attr("height", height)
            .attr('viewBox', `0 0 ${width} ${height}`)
            .attr('preserveAspectRatio', 'xMidYMid meet');
            
        // 添加缩放和拖拽功能
        const zoom = d3.zoom()
            .scaleExtent([0.05, 10])
            .on('zoom', (event) => {
                g.attr('transform', event.transform);
            });
        
        svg.call(zoom);
        
        // 定义美化的箭头标记
        const defs = svg.append('defs');
        
        // 主箭头 - 更现代的样式
        defs.append('marker')
            .attr('id', 'arrowhead')
            .attr('viewBox', '0 -8 16 16')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 10)
            .attr('markerHeight', 10)
            .attr('orient', 'auto')
            .attr('markerUnits', 'strokeWidth')
            .append('path')
            .attr('d', 'M0,-6L12,0L0,6L3,0Z')
            .style('fill', '#64748b')
            .style('stroke', 'none');
        
        const g = svg.append('g');
        
        // 准备节点数据 - 智能限制数量以保证性能
        let entitiesToShow = entities;
        let entityLimitMessage = '';
        
        // 如果实体数量过多，智能选择显示
        if (entities.length > 200) {
            // 对于超大图，选择前200个实体，优先选择有关系的实体
            console.log(`实体数量过多(${entities.length})，将智能选择200个实体进行可视化`);
            
            // 计算每个实体的连接数
            const entityConnectionCount = {};
            relationships.forEach(rel => {
                const sourceKey = rel.source || rel.source_name || rel.head || rel.from || rel.subject;
                const targetKey = rel.target || rel.target_name || rel.tail || rel.to || rel.object;
                
                if (sourceKey) {
                    entityConnectionCount[sourceKey] = (entityConnectionCount[sourceKey] || 0) + 1;
                }
                if (targetKey) {
                    entityConnectionCount[targetKey] = (entityConnectionCount[targetKey] || 0) + 1;
                }
            });
            
            // 按连接数排序，选择最重要的实体
            const sortedEntities = entities.sort((a, b) => {
                const aConnections = entityConnectionCount[a.name] || 0;
                const bConnections = entityConnectionCount[b.name] || 0;
                return bConnections - aConnections;
            });
            
            entitiesToShow = sortedEntities.slice(0, 200);
            entityLimitMessage = `⚠️ 原始实体数：${entities.length}，显示最重要的200个实体`;
        }
        
        const nodes = entitiesToShow.map((entity, i) => {
            return {
                id: entity.name || entity.id || `entity_${i}`,
                name: entity.name || `实体${i}`,
                type: entity.type || 'concept',
                description: entity.description || '',
                originalId: entity.id,
                // 初始位置 - 避免重叠
                x: (width / 2) + (Math.random() - 0.5) * 200,
                y: (height / 2) + (Math.random() - 0.5) * 200
            };
        });
        
        if (entityLimitMessage) {
            console.log(entityLimitMessage);
            // 更新调试信息显示
            const debugItems = document.querySelectorAll('.debug-item');
            debugItems.forEach(item => {
                if (item.textContent.includes('总实体数')) {
                    item.innerHTML = `<strong>总实体数：</strong> ${entities.length} <em style="color: #f59e0b;">(图中显示${nodes.length}个)</em>`;
                }
            });
        }
        
        console.log('节点数据:', nodes.slice(0, 5));
        
        // 创建名称到ID的映射
        const nameToId = {};
        nodes.forEach(node => {
            nameToId[node.id] = node.id;
            nameToId[node.name] = node.id;
            if (node.originalId) {
                nameToId[node.originalId] = node.id;
            }
        });
        
        // 准备边数据 - 改进关系匹配
        const links = [];
        console.log('开始处理关系，总数:', relationships.length);
        
        relationships.forEach((rel, index) => {
            const sourceKey = rel.source || rel.source_name || rel.head || rel.from || rel.subject;
            const targetKey = rel.target || rel.target_name || rel.tail || rel.to || rel.object;
            
            if (!sourceKey || !targetKey) {
                if (index < 5) { // 只显示前5个错误，避免控制台刷屏
                    console.log(`关系${index}缺少source或target:`, rel);
                }
                return;
            }
            
            let sourceId = nameToId[sourceKey];
            let targetId = nameToId[targetKey];
            
            // 如果直接匹配失败，尝试模糊匹配
            if (!sourceId) {
                const sourceNode = nodes.find(n => 
                    n.name.includes(sourceKey) || 
                    sourceKey.includes(n.name) ||
                    n.id === sourceKey ||
                    n.originalId === sourceKey
                );
                sourceId = sourceNode ? sourceNode.id : null;
            }
            
            if (!targetId) {
                const targetNode = nodes.find(n => 
                    n.name.includes(targetKey) || 
                    targetKey.includes(n.name) ||
                    n.id === targetKey ||
                    n.originalId === targetKey
                );
                targetId = targetNode ? targetNode.id : null;
            }
            
            if (sourceId && targetId && sourceId !== targetId) {
                links.push({
                    source: sourceId,
                    target: targetId,
                    source_id: sourceId,  // 保留原始ID用于查询
                    target_id: targetId,  // 保留原始ID用于查询
                    relation: rel.relation || rel.relationship || rel.type || rel.label || 'related',
                    id: `${sourceId}-${targetId}-${rel.relation || 'related'}`,
                    originalRelation: rel
                });
                console.log(`匹配成功 ${index}: ${sourceKey} -> ${targetKey}`);
            } else {
                console.log(`跳过关系 ${index}: ${sourceKey} -> ${targetKey} (source: ${!!sourceId}, target: ${!!targetId})`);
            }
        });
        
        console.log('有效连接数量:', links.length);
        console.log('连接示例:', links.slice(0, 3).map(l => `${l.source} -[${l.relation}]-> ${l.target}`));
        
        // 更新调试信息显示
        const validLinksCountEl = document.getElementById('valid-links-count');
        const connectionExamplesEl = document.getElementById('connection-examples');
        
        if (validLinksCountEl) {
            validLinksCountEl.textContent = links.length;
            validLinksCountEl.style.color = links.length > 0 ? '#10b981' : '#ef4444';
        }
        
        if (connectionExamplesEl) {
            if (links.length > 0) {
                const examples = links.slice(0, 3).map(l => 
                    `<code>${l.source} -[${l.relation}]-> ${l.target}</code>`
                ).join(', ');
                connectionExamplesEl.innerHTML = examples;
            } else {
                connectionExamplesEl.innerHTML = '<em style="color: #ef4444;">未找到有效连接</em>';
            }
        }
        
        // 如果没有连接，创建一些随机连接以便演示
        if (links.length === 0 && nodes.length > 1) {
            console.log('没有找到有效连接，创建随机连接');
            for (let i = 0; i < Math.min(nodes.length - 1, 10); i++) {
                links.push({
                    source: nodes[i].id,
                    target: nodes[i + 1].id,
                    source_id: nodes[i].id,
                    target_id: nodes[i + 1].id,
                    relation: 'related',
                    id: `${nodes[i].id}-${nodes[i + 1].id}-related`
                });
            }
            
            // 更新显示随机连接信息
            if (validLinksCountEl) {
                validLinksCountEl.innerHTML = `${links.length} <em>(随机生成)</em>`;
                validLinksCountEl.style.color = '#f59e0b';
            }
            
            if (connectionExamplesEl) {
                const examples = links.slice(0, 3).map(l => 
                    `<code>${l.source} -[${l.relation}]-> ${l.target}</code>`
                ).join(', ');
                connectionExamplesEl.innerHTML = examples + ' <em>(随机生成用于演示)</em>';
            }
        }
        
        // 初始化力导向模拟
        const simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(120).strength(0.8))
            .force('charge', d3.forceManyBody().strength(-800).distanceMax(400))
            .force('center', d3.forceCenter(width / 2, height / 2).strength(0.1))
            .force('collision', d3.forceCollide().radius(d => this.getNodeRadius(d, links) + 10).strength(0.9))
            .alphaDecay(0.02)
            .velocityDecay(0.4)
            .alphaTarget(0.1);
        
        // 创建连线
        const linkSelection = g.selectAll('.link')
            .data(links, d => d.id);
        
        const newLinks = linkSelection.enter()
            .append('line')
            .attr('class', 'link')
            .style('stroke', '#64748b')
            .style('stroke-width', 2.5)
            .style('opacity', 0.8)
            .style('marker-end', 'url(#arrowhead)');
        
        const allLinks = newLinks.merge(linkSelection);
        
        // 处理边标签（关系名称）
        const linkLabelSelection = g.selectAll('.link-label')
            .data(links.filter(d => links.length < 20), d => d.id);
            
        const newLinkLabels = linkLabelSelection.enter()
            .append('text')
            .attr('class', 'link-label')
            .style('font-size', '11px')
            .style('fill', '#4b5563')
            .style('text-anchor', 'middle')
            .style('pointer-events', 'none')
            .style('font-weight', '500')
            .style('text-shadow', '1px 1px 2px rgba(255,255,255,0.8)')
            .text(d => {
                const relation = d.relation || '关联';
                return relation.length > 6 ? relation.substring(0, 5) + '...' : relation;
            });
        
        const allLinkLabels = newLinkLabels.merge(linkLabelSelection);
        
        // 创建节点组
        const nodeSelection = g.selectAll('.node-group')
            .data(nodes, d => d.id);
        
        nodeSelection.exit().remove();
        
        const newNodeGroups = nodeSelection.enter()
            .append('g')
            .attr('class', 'node-group')
            .style('cursor', 'pointer')
            .call(d3.drag()
                .on('start', (event, d) => this.dragstarted(event, d, simulation))
                .on('drag', (event, d) => this.dragged(event, d))
                .on('end', (event, d) => this.dragended(event, d, simulation)));
        
        // 为新节点组添加圆形
        newNodeGroups.append('circle')
            .attr('r', d => this.getNodeRadius(d, links));
        
        // 为新节点组添加文字标签
        newNodeGroups.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '.3em')
            .style('font-size', '12px')
            .style('font-weight', 'bold')
            .style('pointer-events', 'none')
            .style('fill', '#ffffff');
        
        const allNodeGroups = newNodeGroups.merge(nodeSelection);
        
        // 添加悬停事件
        allNodeGroups
            .on('mouseover', (event, d) => {
                this.showTooltip(event, d, links);
            })
            .on('mouseout', () => {
                this.hideTooltip();
            });
            
        // 更新所有节点的样式和文本
        allNodeGroups.each((d, i, nodeElements) => {
            const nodeGroup = d3.select(nodeElements[i]);
            const circle = nodeGroup.select('circle');
            const text = nodeGroup.select('text');
            
            // 更新圆形半径和样式
            circle.attr('r', this.getNodeRadius(d, links))
                  .style('fill', this.getNodeColor(d.type))
                  .style('stroke', '#ffffff')
                  .style('stroke-width', '2px');
            
            // 更新文本
            const displayName = d.name.length > 5 ? d.name.substring(0, 4) + '…' : d.name;
            text.text(displayName);
        });
        
        // 更新力模拟
        simulation.nodes(nodes);
        simulation.force('link').links(links);
        
        // 确保在力模拟启动后重新计算节点大小
        setTimeout(() => {
            allNodeGroups.each((d, i, nodeElements) => {
                const nodeGroup = d3.select(nodeElements[i]);
                const circle = nodeGroup.select('circle');
                // 重新计算半径，此时links已经被D3处理
                circle.attr('r', this.getNodeRadius(d, links));
            });
        }, 100);
        
        // 添加tick事件处理
        simulation.on('tick', () => {
            allLinks
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);
            
            allNodeGroups
                .attr('transform', d => `translate(${d.x},${d.y})`);
            
            allLinkLabels
                .attr('x', d => (d.source.x + d.target.x) / 2)
                .attr('y', d => (d.source.y + d.target.y) / 2);
        });
        
        // 添加复位按钮
        const resetButton = svg.append("g")
            .attr("class", "reset-button")
            .attr("transform", "translate(10, 10)")
            .style("cursor", "pointer")
            .on("click", () => {
                svg.transition()
                    .duration(750)
                    .call(zoom.transform, d3.zoomIdentity);
            });
            
        resetButton.append("rect")
            .attr("width", 70)
            .attr("height", 28)
            .attr("fill", "#3b82f6")
            .attr("rx", 6);
            
        resetButton.append("text")
            .attr("x", 35)
            .attr("y", 19)
            .attr("text-anchor", "middle")
            .attr("fill", "white")
            .attr("font-size", "13px")
            .attr("font-weight", "500")
            .text("🔄 复位");
        
        // 重启模拟
        simulation.alpha(1).restart();
        
        // 自动适应视图
        this.fitGraphToView(svg, g, zoom, nodes, width, height);
    }
    
    findNodeId(entityName, nodes) {
        const node = nodes.find(n => n.name === entityName || n.id === entityName);
        return node ? node.id : null;
    }
    
    fitGraphToView(svg, g, zoom, nodes, width, height) {
        if (nodes.length === 0) return;
        
        try {
            // 等待布局稳定后再适应视图
            setTimeout(() => {
                const xs = nodes.map(n => n.x).filter(x => !isNaN(x) && isFinite(x));
                const ys = nodes.map(n => n.y).filter(y => !isNaN(y) && isFinite(y));
                
                if (xs.length === 0 || ys.length === 0) {
                    console.log('节点位置数据无效');
                    return;
                }
                
                const minX = Math.min(...xs);
                const maxX = Math.max(...xs);
                const minY = Math.min(...ys);
                const maxY = Math.max(...ys);
                
                // 添加合适的边距
                const margin = 50;
                const graphWidth = maxX - minX + margin * 2;
                const graphHeight = maxY - minY + margin * 2;
                const centerX = (minX + maxX) / 2;
                const centerY = (minY + maxY) / 2;
                
                // 计算合适的缩放比例
                const scale = Math.min(
                    0.8 * width / graphWidth,
                    0.8 * height / graphHeight,
                    1.0  // 限制最大缩放
                );
                
                // 计算平移量，使图形居中
                const translateX = width / 2 - scale * centerX;
                const translateY = height / 2 - scale * centerY;
                
                console.log(`适应视图: 缩放${scale.toFixed(2)}, 平移(${translateX.toFixed(1)}, ${translateY.toFixed(1)})`);
                
                svg.transition()
                    .duration(750)
                    .call(
                        zoom.transform,
                        d3.zoomIdentity.translate(translateX, translateY).scale(scale)
                    );
            }, 500);
                
        } catch (error) {
            console.log('适应视图失败:', error);
        }
    }
    
    getNodeColor(type) {
        const colors = {
            'person': '#f59e0b',
            'organization': '#3b82f6', 
            'location': '#10b981',
            'concept': '#8b5cf6',
            'event': '#ef4444',
            'default': '#94a3b8'
        };
        return colors[type] || colors.default;
    }
    
    getNodeRadius(d, links = []) {
        if (!d) return 25;
        
        // 计算节点的连接数
        const connectionCount = links.filter(link => {
            // 处理D3转换后的source/target对象
            const sourceId = typeof link.source === 'object' ? link.source.id : (link.source_id || link.source);
            const targetId = typeof link.target === 'object' ? link.target.id : (link.target_id || link.target);
            return sourceId === d.id || targetId === d.id;
        }).length;
        
        // 基础半径 + 根据连接数增加半径
        const baseRadius = 25;
        const radiusIncrement = Math.min(connectionCount * 2, 15); // 最多增加15px
        return baseRadius + radiusIncrement;
    }
    
    showTooltip(event, d, links = []) {
        const tooltip = document.createElement('div');
        tooltip.className = 'graph-tooltip';
        
        // 计算连接数 - 处理D3转换后的source/target对象
        const connectedLinks = links.filter(link => {
            const sourceId = typeof link.source === 'object' ? link.source.id : (link.source_id || link.source);
            const targetId = typeof link.target === 'object' ? link.target.id : (link.target_id || link.target);
            return sourceId === d.id || targetId === d.id;
        });
        
        const connectionCount = connectedLinks.length;
        
        // 获取连接的节点名称和关系
        const connections = connectedLinks.map(link => {
            const sourceId = typeof link.source === 'object' ? link.source.id : (link.source_id || link.source);
            const targetId = typeof link.target === 'object' ? link.target.id : (link.target_id || link.target);
            
            if (sourceId === d.id) {
                // 当前节点是源节点，显示：关系 → 目标节点
                const targetName = typeof link.target === 'object' ? link.target.name : targetId;
                return `[${link.relation || 'related'}] → ${targetName}`;
            } else {
                // 当前节点是目标节点，显示：源节点 → 关系
                const sourceName = typeof link.source === 'object' ? link.source.name : sourceId;
                return `${sourceName} → [${link.relation || 'related'}]`;
            }
        }).slice(0, 3);
        
        const connectedNodesText = connections.join(', ');
        
        tooltip.innerHTML = `
            <div class="tooltip-title">${d.name}</div>
            <div class="tooltip-info">类型: ${d.type}</div>
            <div class="tooltip-info">连接数: ${connectionCount}</div>
            ${connectionCount > 0 ? `<div class="tooltip-info">关系: ${connectedNodesText}${connectionCount > 3 ? '...' : ''}</div>` : ''}
            ${d.description ? `<div class="tooltip-desc">${d.description}</div>` : ''}
        `;
        
        document.body.appendChild(tooltip);
        
        const rect = tooltip.getBoundingClientRect();
        tooltip.style.left = `${event.pageX - rect.width / 2}px`;
        tooltip.style.top = `${event.pageY - rect.height - 10}px`;
        
        this.currentTooltip = tooltip;
    }
    
    hideTooltip() {
        if (this.currentTooltip) {
            document.body.removeChild(this.currentTooltip);
            this.currentTooltip = null;
        }
    }
    
    dragstarted(event, d, simulation) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    dragended(event, d, simulation) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
    
    closeModal() {
        document.getElementById('graph-preview-modal').style.display = 'none';
    }
    
    async startGeneration() {
        if (this.selectedRuns.size === 0) return;
        
        try {
            // 获取配置参数
            const config = {
                run_ids: Array.from(this.selectedRuns),
                sample_size: parseInt(document.getElementById('sample-size').value),
                sampling_algorithm: document.getElementById('sampling-algorithm').value,
                questions_per_run: parseInt(document.getElementById('questions-per-run').value),
                use_unified_qa: document.getElementById('use-unified-qa').value === 'true',
                qps_limit: parseFloat(document.getElementById('qps-limit').value),
                parallel_workers: parseInt(document.getElementById('parallel-workers').value)
            };
            
            // 显示结果区域
            document.querySelector('.results-section').style.display = 'block';
            
            // 构建配置信息字符串
            const configInfo = `配置: ${config.run_ids.length}个记录, QPS限制: ${config.qps_limit}, 并发数: ${config.parallel_workers}`;
            this.updateStatus(`正在启动QA生成任务... ${configInfo}`, 0);
            
            // 发送请求
            const response = await fetch('/api/runs/generate-qa', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.currentTask = data.task_id;
                this.updateStatus('QA生成任务已启动，正在处理...', 20);
                
                // 禁用生成按钮
                document.getElementById('start-generation').disabled = true;
                document.getElementById('start-generation').textContent = '生成中...';
            } else {
                this.updateStatus(`启动失败: ${data.error}`, 0);
            }
        } catch (error) {
            console.error('启动生成失败:', error);
            this.updateStatus('网络错误，请检查连接', 0);
        }
    }
    
    handleGenerationProgress(data) {
        if (data.task_id !== this.currentTask) return;
        
        // 更新进度状态
        this.updateStatus(data.message, data.progress);
    }
    
    handleGenerationComplete(data) {
        if (data.task_id !== this.currentTask) return;
        
        if (data.success) {
            this.updateStatus(`QA生成完成！生成了 ${data.results_count} 个问答对`, 100);
            this.displayResults(data);
        } else {
            this.updateStatus(`生成失败: ${data.error}`, 0);
        }
        
        // 重新启用按钮
        document.getElementById('start-generation').disabled = false;
        document.getElementById('start-generation').textContent = '开始生成QA';
        this.currentTask = null;
    }
    
    updateStatus(message, progress) {
        document.querySelector('.status-text').textContent = message;
        document.querySelector('.progress-fill').style.width = `${progress}%`;
    }
    
    displayResults(data) {
        const qaResults = data.qa_results || [];
        
        // 计算性能统计信息
        const configInfo = this.getConfigInfo();
        const estimatedTime = data.runs_processed ? 
            `估计用时: ${(data.runs_processed / (configInfo.qps_limit || 1)).toFixed(1)}秒 (基于QPS限制)` : '';
        
        const summaryContent = `
            <div class="result-summary">
                <h3>✅ 生成完成</h3>
                <p>成功生成 <strong>${data.results_count}</strong> 个问答对</p>
                ${data.runs_processed ? `<p>处理了 <strong>${data.runs_processed}</strong> 个运行记录</p>` : ''}
                <p>结果已保存到: <code>${data.output_file}</code></p>
                
                <div class="performance-info">
                    <h4>📊 性能统计</h4>
                    <p>QPS限制: <strong>${configInfo.qps_limit || '无限制'}</strong></p>
                    <p>并发数: <strong>${configInfo.parallel_workers}</strong></p>
                    ${estimatedTime ? `<p>${estimatedTime}</p>` : ''}
                </div>
            </div>
            
            <div class="result-actions">
                <button class="btn btn-primary" onclick="window.open('/qa_output/${data.output_file.split('/').pop()}', '_blank')">
                    📥 下载结果文件
                </button>
                <button class="btn btn-secondary" onclick="navigator.clipboard.writeText('${data.output_file}')">
                    📋 复制文件路径
                </button>
            </div>
        `;
        
        const qaContent = qaResults.length > 0 ? `
            <div class="qa-results-section">
                <h3>📝 生成的问答对</h3>
                <div class="qa-list">
                    ${qaResults.map((qa, index) => this.createQAItem(qa, index + 1)).join('')}
                </div>
            </div>
        ` : '';
        
        document.getElementById('results-content').innerHTML = summaryContent + qaContent;
    }
    
    createQAItem(qa, index) {
        const question = qa.question || qa.Question || qa.问题 || '问题信息不可用';
        const answer = qa.answer || qa.Answer || qa.答案 || '答案信息不可用';
        const reasoning = qa.reasoning_process || qa.reasoning || qa.推理过程 || '';
        const sourceRun = qa.source_run_id || '未知';
        const algorithm = qa.sampling_algorithm || '未知';
        const subgraphSize = qa.subgraph_size || 0;
        const generatedAt = qa.generated_at ? new Date(qa.generated_at).toLocaleString() : '未知时间';
        
        return `
            <div class="qa-item" data-index="${index}">
                <div class="qa-header">
                    <div class="qa-title">问答对 ${index}</div>
                    <div class="qa-meta">
                        <span class="meta-tag">来源: ${sourceRun}</span>
                        <span class="meta-tag">算法: ${algorithm}</span>
                        <span class="meta-tag">子图大小: ${subgraphSize}节点</span>
                        <span class="meta-tag">时间: ${generatedAt}</span>
                    </div>
                </div>
                
                <div class="qa-content">
                    <div class="question-section">
                        <div class="section-label">❓ 问题</div>
                        <div class="question-text">${this.formatText(question)}</div>
                    </div>
                    
                    <div class="answer-section">
                        <div class="section-label">✅ 答案</div>
                        <div class="answer-text">${this.formatText(answer)}</div>
                    </div>
                    
                    ${reasoning ? `
                        <div class="reasoning-section">
                            <div class="section-label">🧠 推理过程</div>
                            <div class="reasoning-text">${this.formatText(reasoning)}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    formatText(text) {
        if (!text) return '信息不可用';
        // 简单的文本格式化，保留换行
        return text.replace(/\n/g, '<br>');
    }
    
    getConfigInfo() {
        return {
            sample_size: parseInt(document.getElementById('sample-size').value),
            sampling_algorithm: document.getElementById('sampling-algorithm').value,
            questions_per_run: parseInt(document.getElementById('questions-per-run').value),
            use_unified_qa: document.getElementById('use-unified-qa').value === 'true',
            qps_limit: parseFloat(document.getElementById('qps-limit').value),
            parallel_workers: parseInt(document.getElementById('parallel-workers').value)
        };
    }
    
    showLoading(elementId, message) {
        document.getElementById(elementId).innerHTML = `<div class="loading">${message}</div>`;
    }
    
    showError(elementId, message) {
        document.getElementById(elementId).innerHTML = `
            <div class="loading" style="animation: none; color: #dc2626;">
                ⚠️ ${message}
            </div>
        `;
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    new RunsQAGenerator();
}); 