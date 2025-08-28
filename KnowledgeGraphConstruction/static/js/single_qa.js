/**
 * Single QA页面JavaScript
 */

// Socket.IO连接
const socket = io();

// 全局变量
let svg, g, simulation, zoom;
let currentGraphData = {nodes: [], links: []};
let expansionInfo = null;  // expansion状态信息
let isBuilding = false;
let graphContainer; // 图谱容器元素

// DOM元素
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const logContainer = document.getElementById('log-container');
const nodeCountEl = document.getElementById('node-count');
const linkCountEl = document.getElementById('link-count');
const qaResultContainer = document.getElementById('qa-result-container');
const qaResultContent = document.getElementById('qa-result-content');
const expansionInfoContainer = document.getElementById('expansion-info'); // expansion信息容器

// 初始化图谱
function initGraph() {
    graphContainer = document.querySelector('.graph-container');
    const width = graphContainer.clientWidth;
    const height = graphContainer.clientHeight;
    
    svg = d3.select('#graph-svg')
        .attr('width', width)
        .attr('height', height)
        .attr('viewBox', `0 0 ${width} ${height}`)
        .attr('preserveAspectRatio', 'xMidYMid meet');
    
    svg.selectAll('*').remove();
    
    // 添加缩放和平移功能
    zoom = d3.zoom()
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
    
    // 高亮箭头（用于采样图）
    defs.append('marker')
        .attr('id', 'arrowhead-highlight')
        .attr('viewBox', '0 -8 16 16')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 10)
        .attr('markerHeight', 10)
        .attr('orient', 'auto')
        .attr('markerUnits', 'strokeWidth')
        .append('path')
        .attr('d', 'M0,-6L12,0L0,6L3,0Z')
        .style('fill', '#1d4ed8')
        .style('stroke', 'none');
    
    g = svg.append('g');
    
    // 初始化力导向模拟 - 优化为稳定的网状结构
    simulation = d3.forceSimulation()
        .force('link', d3.forceLink().id(d => d.id).distance(120).strength(0.8))  // 减少距离，增强连接强度
        .force('charge', d3.forceManyBody().strength(-800).distanceMax(400))  // 适中的排斥力，避免过度分散
        .force('center', d3.forceCenter(width / 2, height / 2).strength(0.1))  // 轻微的中心引力
        .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 10).strength(0.9))  // 动态碰撞半径
        .alphaDecay(0.02)  // 加快收敛速度，减少无意义的移动
        .velocityDecay(0.4)  // 降低阻尼，允许更自然的移动
        .alphaTarget(0.1);  // 保持轻微的活力
}

// 创建带位置的节点 - 有序网状分布算法
function createPositionedNode(id, name, type, index, totalNodes) {
    const containerWidth = graphContainer.clientWidth || 1200;
    const containerHeight = graphContainer.clientHeight || 800;
    const centerX = containerWidth / 2;
    const centerY = containerHeight / 2;
    
    let x, y;
    
    if (totalNodes <= 1) {
        x = centerX;
        y = centerY;
    } else if (totalNodes <= 6) {
        // 少量节点：正六边形分布
        const angle = (index / totalNodes) * 2 * Math.PI;
        const radius = 120;
        x = centerX + Math.cos(angle) * radius;
        y = centerY + Math.sin(angle) * radius;
    } else if (totalNodes <= 20) {
        // 中等节点：多层圆形分布
        const layer = Math.floor(Math.sqrt(index));
        const nodesInLayer = Math.max(6, layer * 6);
        const angleStep = (2 * Math.PI) / nodesInLayer;
        const angle = (index % nodesInLayer) * angleStep;
        const radius = 80 + layer * 100; // 层间距离100px
        
        x = centerX + Math.cos(angle) * radius;
        y = centerY + Math.sin(angle) * radius;
    } else {
        // 大量节点：网格化螺旋分布
        const gridSize = Math.ceil(Math.sqrt(totalNodes)) + 2;
        const cellWidth = Math.max(120, Math.min(containerWidth, containerHeight) / gridSize);
        const cellHeight = cellWidth * 0.866; // 六边形比例
        
        const row = Math.floor(index / gridSize);
        const col = index % gridSize;
        
        // 六边形网格偏移
        const offsetX = (row % 2) * (cellWidth / 2);
        
        x = (col - gridSize / 2) * cellWidth + centerX + offsetX;
        y = (row - gridSize / 2) * cellHeight + centerY;
        
        // 添加少量随机偏移，避免过于规整
        x += (Math.random() - 0.5) * 40;
        y += (Math.random() - 0.5) * 40;
    }
    
    return {
        id: id,
        name: name,
        type: type,
        x: x,
        y: y
    };
}

// 字符串哈希函数
function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return hash;
}

// 高亮采样图（星座图）
function highlightSampledGraph(sampledNodes, sampledLinks) {
    if (!g) {
        console.warn('SVG图形容器未初始化，无法高亮星座图');
        return;
    }
    
    console.log('开始高亮星座图:', {
        sampledNodes: sampledNodes.length,
        sampledLinks: sampledLinks.length,
        nodeIds: sampledNodes.map(n => n.id || n.name),
        currentNodes: currentGraphData.nodes.length
    });
    
    // 获取采样节点和连线的ID
    const sampledNodeIds = new Set();
    sampledNodes.forEach(node => {
        const nodeId = node.id || node.name;
        if (nodeId) sampledNodeIds.add(nodeId);
    });
    
    const sampledLinkIds = new Set();
    sampledLinks.forEach(link => {
        const sourceId = link.source_id || link.source;
        const targetId = link.target_id || link.target;
        if (sourceId && targetId) {
            sampledLinkIds.add(`${sourceId}-${targetId}`);
            // 也添加反向连接
            sampledLinkIds.add(`${targetId}-${sourceId}`);
        }
    });
    
    // 添加连接星座图节点的边
    const connectedLinkIds = new Set([...sampledLinkIds]);
    
    // 遍历当前图谱数据中的所有连线，查找连接到星座图节点的边
    currentGraphData.links.forEach(link => {
        const sourceId = link.source_id || link.source;
        const targetId = link.target_id || link.target;
        
        // 如果连线的任一端是星座图节点，则也高亮这条连线
        if (sampledNodeIds.has(sourceId) || sampledNodeIds.has(targetId)) {
            connectedLinkIds.add(`${sourceId}-${targetId}`);
            connectedLinkIds.add(`${targetId}-${sourceId}`);
            console.log(`添加连接边: ${sourceId} -> ${targetId}`);
        }
    });
    
    console.log('星座图节点IDs:', Array.from(sampledNodeIds));
    console.log('星座图及连接的连线IDs:', Array.from(connectedLinkIds));
    
    // 重置所有节点为正常状态
    g.selectAll('.node-group').each(function(d) {
        const nodeGroup = d3.select(this);
        const circle = nodeGroup.select('circle');
        
        // 先重置为正常状态
        const standardColor = getNodeColor(d);
        circle.style('fill', standardColor)
              .style('stroke', '#6b7280')
              .style('stroke-width', '2px')
              .style('opacity', 1)
              .style('filter', 'none');
        nodeGroup.classed('sampled', false);
    });
    
    // 高亮采样的节点
    let highlightedNodesCount = 0;
    g.selectAll('.node-group').each(function(d) {
        const nodeGroup = d3.select(this);
        const circle = nodeGroup.select('circle');
        
        if (sampledNodeIds.has(d.id) || sampledNodeIds.has(d.name)) {
            // 星座图节点：适度高亮，不过于强烈
            circle.style('fill', '#3b82f6')
                  .style('stroke', '#1d4ed8')
                  .style('stroke-width', '4px')
                  .style('opacity', 1)
                  .style('filter', 'drop-shadow(0 0 8px rgba(59, 130, 246, 0.6))');
            nodeGroup.classed('sampled', true);
            highlightedNodesCount++;
            console.log(`高亮节点: ${d.name} (${d.id})`);
        } else {
            // 非星座图节点：适度降低透明度，不过于淡化
            const standardColor = getNodeColor(d);
            circle.style('fill', standardColor)
                  .style('stroke', '#6b7280')
                  .style('stroke-width', '1px')
                  .style('opacity', 0.4)
                  .style('filter', 'none');
            nodeGroup.classed('sampled', false);
        }
    });
    
    // 重置所有连线为正常状态
    g.selectAll('.link').each(function(d) {
        const link = d3.select(this);
        link.style('stroke', '#94a3b8')
            .style('stroke-width', 2)
            .style('opacity', 1)
            .style('marker-end', 'url(#arrowhead)')
            .style('filter', 'none')
            .classed('sampled', false);
    });
    
    // 高亮采样的连线和连接线
    let highlightedLinksCount = 0;
    g.selectAll('.link').each(function(d) {
        const link = d3.select(this);
        
        // 获取连线的源和目标ID，考虑d3力导向图的对象引用
        let sourceId, targetId;
        if (typeof d.source === 'object') {
            sourceId = d.source.id;
        } else {
            sourceId = d.source;
        }
        
        if (typeof d.target === 'object') {
            targetId = d.target.id;
        } else {
            targetId = d.target;
        }
        
        const linkId1 = `${sourceId}-${targetId}`;
        const linkId2 = `${targetId}-${sourceId}`;
        
        if (connectedLinkIds.has(linkId1) || connectedLinkIds.has(linkId2)) {
            // 星座图连线：适度高亮，不过于强烈
            link.style('stroke', '#1d4ed8')
                .style('stroke-width', 4)
                .style('opacity', 1)
                .style('marker-end', 'url(#arrowhead-highlight)')
                .style('filter', 'drop-shadow(0 0 4px rgba(29, 78, 216, 0.5))')
                .classed('sampled', true);
            highlightedLinksCount++;
            console.log(`高亮连线: ${sourceId} -> ${targetId}`);
        } else {
            // 非星座图连线：适度降低透明度
            link.style('stroke', '#94a3b8')
                .style('stroke-width', 1)
                .style('opacity', 0.3)
                .style('marker-end', 'url(#arrowhead)')
                .style('filter', 'none')
                .classed('sampled', false);
        }
    });
    
    console.log(`星座图高亮完成: ${highlightedNodesCount} 个节点, ${highlightedLinksCount} 个连线`);
}

// 显示tooltip - 显示完整节点信息
function showTooltip(event, d) {
    console.log('showTooltip被调用，节点数据:', d);
    
    let tooltip = document.getElementById('tooltip');
    if (!tooltip) {
        // 如果tooltip不存在，创建一个
        tooltip = document.createElement('div');
        tooltip.id = 'tooltip';
        document.body.appendChild(tooltip);
        console.log('创建了tooltip元素');
    } else {
        console.log('使用现有的tooltip元素');
    }
    
    // 显示完整的节点名称
    let tooltipContent = `<strong style="font-size: 14px; color: white;">${d.name}</strong>`;
    
    // 显示节点类型
    if (d.type && d.type !== 'unknown') {
        tooltipContent += `<br/><span style="color: #94a3b8;">类型: ${d.type}</span>`;
    }
    
    // 计算并显示连接数
    const connectionCount = currentGraphData.links.filter(link => 
        (link.source_id || link.source) === d.id || 
        (link.target_id || link.target) === d.id
    ).length;
    tooltipContent += `<br/><span style="color: #94a3b8;">连接数: ${connectionCount}</span>`;
    
    // 显示expansion状态
    if (d.expansion_status && d.expansion_status !== 'normal') {
        const statusMap = {
            'current': '当前拓展节点',
            'expansion': '拓展节点',
            'sampled': '采样节点'
        };
        tooltipContent += `<br/><span style="color: #60a5fa;">状态: ${statusMap[d.expansion_status] || d.expansion_status}</span>`;
    }
    
    // 显示拓展顺序
    if (d.expansion_order !== undefined && d.expansion_order !== null) {
        tooltipContent += `<br/><span style="color: #60a5fa;">拓展顺序: ${d.expansion_order + 1}</span>`;
    }
    
    // 显示描述（如果有）
    if (d.description && d.description.trim()) {
        const shortDesc = d.description.length > 100 ? d.description.substring(0, 100) + '...' : d.description;
        tooltipContent += `<br/><span style="color: #94a3b8; font-size: 12px;">描述: ${shortDesc}</span>`;
    }
    
    tooltip.innerHTML = tooltipContent;
    
    // 强制设置关键样式确保显示
    tooltip.style.zIndex = '9999';
    tooltip.style.position = 'fixed';  // 使用fixed而不是absolute，避免被SVG遮挡
    tooltip.style.pointerEvents = 'none';
    
    // 计算tooltip位置，避免超出屏幕（先隐藏以获取准确尺寸）
    let left = event.clientX + 15;  // 使用clientX而不是pageX
    let top = event.clientY - 10;   // 使用clientY而不是pageY
    
    tooltip.style.visibility = 'hidden';
    tooltip.classList.add('show');  // 添加show类名以确保CSS样式生效
    
    const rect = tooltip.getBoundingClientRect();
    
    if (left + rect.width > window.innerWidth) {
        left = event.pageX - rect.width - 15;
    }
    if (top + rect.height > window.innerHeight) {
        top = event.pageY - rect.height - 10;
    }
    
    // 设置最终位置并显示
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.visibility = 'visible';
    
    console.log('tooltip显示位置:', { left, top, rect, className: tooltip.className });
}

// 隐藏tooltip
function hideTooltip() {
    console.log('hideTooltip被调用');
    const tooltip = document.getElementById('tooltip');
    if (tooltip) {
        tooltip.classList.remove('show');  // 移除show类名
        tooltip.style.visibility = 'hidden';
        console.log('tooltip已隐藏，类名:', tooltip.className);
    }
}

// 更新统计信息
function updateStatistics() {
    if (nodeCountEl) nodeCountEl.textContent = currentGraphData.nodes.length;
    if (linkCountEl) linkCountEl.textContent = currentGraphData.links.length;
}

// 动态调整SVG视图以包含所有节点
function adjustViewBox() {
    if (!currentGraphData.nodes || currentGraphData.nodes.length === 0) return;
    
    // 计算所有节点的边界
    const padding = 100; // 边距
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    
    currentGraphData.nodes.forEach(node => {
        const radius = getNodeRadius(node);
        minX = Math.min(minX, node.x - radius);
        maxX = Math.max(maxX, node.x + radius);
        minY = Math.min(minY, node.y - radius);
        maxY = Math.max(maxY, node.y + radius);
    });
    
    // 计算总的图谱尺寸
    const graphWidth = maxX - minX + padding * 2;
    const graphHeight = maxY - minY + padding * 2;
    const graphCenterX = (minX + maxX) / 2;
    const graphCenterY = (minY + maxY) / 2;
    
    // 获取容器尺寸
    const containerWidth = graphContainer.clientWidth;
    const containerHeight = graphContainer.clientHeight;
    
    // 计算最合适的缩放比例
    const scale = Math.min(
        containerWidth / graphWidth,
        containerHeight / graphHeight,
        1.0  // 不超过1:1显示
    );
    
    // 设置viewBox以包含所有节点
    const viewBoxWidth = Math.max(graphWidth, containerWidth / scale);
    const viewBoxHeight = Math.max(graphHeight, containerHeight / scale);
    const viewBoxX = graphCenterX - viewBoxWidth / 2;
    const viewBoxY = graphCenterY - viewBoxHeight / 2;
    
    svg.attr('viewBox', `${viewBoxX} ${viewBoxY} ${viewBoxWidth} ${viewBoxHeight}`)
       .attr('preserveAspectRatio', 'xMidYMid meet');
}

// 获取节点半径（基于连接数）
function getNodeRadius(d) {
    if (!d || !currentGraphData.links) return 25;
    
    // 计算节点的连接数
    const connectionCount = currentGraphData.links.filter(link => 
        (link.source_id || link.source) === d.id || 
        (link.target_id || link.target) === d.id
    ).length;
    
    // 基础半径 + 根据连接数增加半径
    const baseRadius = 25;
    const radiusIncrement = Math.min(connectionCount * 2, 15); // 最多增加15px
    return baseRadius + radiusIncrement;
}

// 获取节点颜色 - 简化配色方案
function getNodeColor(d) {
    // 根据expansion状态决定颜色
    if (d.expansion_status === 'current') {
        return '#1e40af';  // 深蓝色 - 当前expansion节点
    } else if (d.expansion_status === 'expansion') {
        return '#60a5fa';  // 浅蓝色 - expansion节点
    } else {
        return '#94a3b8';  // 统一的灰色 - 普通节点
    }
}

// 截断文本
function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// 拖拽事件处理
function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}

// 清空图谱
function clearGraph() {
    if (g) {
        g.selectAll('*').remove();
    }
    currentGraphData = {nodes: [], links: []};
    updateStatistics();
}

// 增量更新图表
function updateGraph(data, isIncremental = false) {
    if (!g || !simulation) return;
    
    // 更新expansion信息
    if (data.expansion_info) {
        expansionInfo = data.expansion_info;
        updateExpansionDisplay();
        
        // 确保expansion序列中的所有节点都有正确的状态
        if (expansionInfo.expansion_nodes && expansionInfo.expansion_nodes.length > 0) {
            const expansionNodeIds = new Set(expansionInfo.expansion_nodes.map(n => n.id));
            const currentNodeId = expansionInfo.current_node ? expansionInfo.current_node.id : null;
            
            // 更新节点的expansion状态
            if (data.nodes) {
                data.nodes.forEach(node => {
                    if (expansionNodeIds.has(node.id)) {
                        if (node.id === currentNodeId) {
                            node.expansion_status = 'current';
                        } else {
                            node.expansion_status = 'expansion';
                        }
                    }
                });
            }
        }
    }
    
    // 处理节点数据
    if (data.nodes && Array.isArray(data.nodes)) {
        if (!isIncremental) {
            // 完全重新加载
            currentGraphData.nodes = data.nodes.map((node, index) => {
                const positionedNode = createPositionedNode(node.id, node.name, node.type, index, data.nodes.length);
                return {
                    ...positionedNode,
                    ...node,  // 保留所有原始数据
                    type: node.type || 'concept',
                    description: node.description || '',
                    group: node.group || 0,
                    expansion_status: node.expansion_status || 'normal',
                    expansion_order: node.expansion_order
                };
            });
        } else {
            // 增量更新
            const existingNodeIds = new Set(currentGraphData.nodes.map(n => n.id));
            data.nodes.forEach(node => {
                if (!existingNodeIds.has(node.id)) {
                    const positionedNode = createPositionedNode(node.id, node.name, node.type, currentGraphData.nodes.length, currentGraphData.nodes.length + 1);
                    currentGraphData.nodes.push({
                        ...positionedNode,
                        ...node,  // 保留所有原始数据
                        type: node.type || 'concept',
                        description: node.description || '',
                        group: node.group || 0,
                        expansion_status: node.expansion_status || 'normal',
                        expansion_order: node.expansion_order
                    });
                } else {
                    // 更新现有节点的所有属性
                    const existingNode = currentGraphData.nodes.find(n => n.id === node.id);
                    if (existingNode) {
                        // 保留位置信息，更新其他所有属性
                        const oldX = existingNode.x;
                        const oldY = existingNode.y;
                        Object.assign(existingNode, node);
                        existingNode.x = oldX;
                        existingNode.y = oldY;
                        
                        // 确保expansion状态正确更新
                        existingNode.expansion_status = node.expansion_status || 'normal';
                        existingNode.expansion_order = node.expansion_order;
                    }
                }
            });
        }
    }
    
    // 处理连线数据
    if (data.links && Array.isArray(data.links)) {
        const processedLinks = data.links.map(link => {
            // 确保source和target字段标准化
            const sourceId = link.source_id || link.source;
            const targetId = link.target_id || link.target;
            
            return {
                ...link,
                source: sourceId,
                target: targetId,
                source_id: sourceId,
                target_id: targetId,
                id: `${sourceId}-${targetId}-${link.relation || link.relationship || 'related'}`
            };
        });
        
        if (!isIncremental) {
            currentGraphData.links = processedLinks;
        } else {
            // 增量添加连线
            const existingLinkIds = new Set(currentGraphData.links.map(l => l.id));
            processedLinks.forEach(link => {
                if (!existingLinkIds.has(link.id)) {
                    currentGraphData.links.push(link);
                }
            });
        }
    }
    
    // 确保初始节点被正确标记为expansion状态
    ensureInitialNodeExpansionStatus();
    
    // 更新可视化
    renderCurrentGraph();
    
    // 更新统计信息
    updateStatistics();
    
    addLog('INFO', `图谱${isIncremental ? '增量' : '完全'}更新: ${currentGraphData.nodes.length} 个节点, ${currentGraphData.links.length} 个关系`);
}

// 统一的图形渲染函数
function renderCurrentGraph() {
    if (!g || !simulation) return;
    
    const nodes = currentGraphData.nodes;
    const links = currentGraphData.links;
    
    // 预过滤有效连线 - 改进日志和错误处理
    const validLinks = links.filter(link => {
        const sourceId = link.source_id || link.source;
        const targetId = link.target_id || link.target;
        const sourceNode = nodes.find(n => n.id === sourceId);
        const targetNode = nodes.find(n => n.id === targetId);
        
        if (!sourceNode || !targetNode) {
            // 减少噪音，只在debug模式下输出详细错误
            if (console.debug) {
                console.debug('连线无效，缺少节点:', {
                    sourceId, 
                    targetId, 
                    hasSource: !!sourceNode, 
                    hasTarget: !!targetNode,
                    link
                });
            }
            return false;
        }
        return true;
    });
    
    // 清理旧的连线和标签，避免重叠
    g.selectAll('.link').remove();
    g.selectAll('.link-label').remove();
    
    // 添加新连线
    const linkSelection = g.selectAll('.link')
        .data(validLinks, d => d.id || `${d.source}-${d.target}-${d.relation}`);
    
    const newLinks = linkSelection.enter()
        .append('line')
        .attr('class', 'link')
        .style('stroke', '#64748b')
        .style('stroke-width', 2.5)
        .style('opacity', 0.8)
        .style('marker-end', 'url(#arrowhead)');
    
    // 合并新旧连线
    const allLinks = newLinks.merge(linkSelection);
    
    // 处理边标签（关系名称）
    const linkLabelSelection = g.selectAll('.link-label')
        .data(validLinks, d => d.id || `${d.source}-${d.target}-${d.relation}`);
        
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
            const relation = d.relation || d.relationship || '关联';
            return relation.length > 6 ? relation.substring(0, 5) + '...' : relation;
        });
    
    // 合并新旧标签
    const allLinkLabels = newLinkLabels.merge(linkLabelSelection);
    
    // 处理节点组 - 避免重复创建
    const nodeSelection = g.selectAll('.node-group')
        .data(nodes, d => d.id);
    
    // 移除旧节点组
    nodeSelection.exit().remove();
    
    // 添加新节点组
    const newNodeGroups = nodeSelection.enter()
        .append('g')
        .attr('class', 'node-group')
        .style('cursor', 'pointer')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));
    
    // 为新节点组添加圆形 - 使用动态半径
    newNodeGroups.append('circle')
        .attr('r', d => getNodeRadius(d));
    
    // 为新节点组添加文字标签 - 改进文本显示
    newNodeGroups.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', '.3em')
        .style('font-size', '12px')
        .style('font-weight', 'bold')
        .style('pointer-events', 'none')
        .style('fill', '#ffffff');
    
    // 合并新旧节点组
    const allNodeGroups = newNodeGroups.merge(nodeSelection);
    
    // 清除所有旧的hover事件，重新绑定
    allNodeGroups
        .on('mouseover', null)
        .on('mouseout', null)
        .on('mouseover', function(event, d) {
            console.log('鼠标悬浮在节点上:', d.name);
            showTooltip(event, d);
        })
        .on('mouseout', function(event, d) {
            console.log('鼠标离开节点:', d.name);
            hideTooltip();
        });
            
            // 更新所有节点的样式和文本
            allNodeGroups.each(function(d) {
                const nodeGroup = d3.select(this);
                const circle = nodeGroup.select('circle');
                const text = nodeGroup.select('text');
                
                // 更新圆形半径
                circle.attr('r', getNodeRadius(d));
                
                // 使用简化的颜色方案
                const fillColor = getNodeColor(d);
                let strokeColor = '#ffffff';
                let strokeWidth = 2;
                
                // 设置边框样式
                if (d.expansion_status === 'current') {
                    strokeColor = '#1e3a8a';
                    strokeWidth = 4;
                } else if (d.expansion_status === 'expansion') {
                    strokeColor = '#2563eb';
                    strokeWidth = 3;
                } else {
                    strokeColor = '#6b7280';
                    strokeWidth = 2;
                }
                
                circle.style('fill', fillColor)
                      .style('stroke', strokeColor)
                      .style('stroke-width', strokeWidth + 'px');
                
                // 改进文本显示 - 限制为5个字符，鼠标悬浮显示完整名称
                const displayName = d.name.length > 5 ? d.name.substring(0, 4) + '…' : d.name;
                text.text(displayName);
            });
    
    // 更新力模拟 - 确保连线正确引用节点
    simulation.nodes(nodes);
    
    // 确保有效连线的source和target指向正确的ID
    validLinks.forEach(link => {
        const sourceId = link.source_id || link.source;
        const targetId = link.target_id || link.target;
        link.source = sourceId;
        link.target = targetId;
    });
    
    console.log('设置力模拟:', {
        nodeCount: nodes.length,
        validLinkCount: validLinks.length,
        sampleNode: nodes[0],
        sampleLink: validLinks[0]
    });
    
                // 重新创建力链接，确保干净的状态
            simulation.force('link', d3.forceLink(validLinks)
                .id(d => d.id)
                .distance(120)  // 与初始化保持一致
                .strength(0.8)  // 与初始化保持一致
            );
    simulation.alpha(0.3).restart();
    
                // 计算线条与圆的交点，避免穿过节点
            function getLinePoints(source, target) {
                const sourceRadius = getNodeRadius(source) + 2;
                const targetRadius = getNodeRadius(target) + 2;
                
                const dx = target.x - source.x;
                const dy = target.y - source.y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance === 0) return { x1: source.x, y1: source.y, x2: target.x, y2: target.y };
                
                const unitX = dx / distance;
                const unitY = dy / distance;
                
                return {
                    x1: source.x + unitX * sourceRadius,
                    y1: source.y + unitY * sourceRadius,
                    x2: target.x - unitX * targetRadius,
                    y2: target.y - unitY * targetRadius
                };
            }
            
            // 设置tick事件处理
            simulation.on('tick', () => {
                // 更新连线位置 - 从节点边缘开始，不穿过节点
                allLinks.each(function(d) {
                    const line = d3.select(this);
                    const points = getLinePoints(d.source, d.target);
                    line.attr('x1', points.x1)
                        .attr('y1', points.y1)
                        .attr('x2', points.x2)
                        .attr('y2', points.y2);
                });
        
        // 更新边标签位置（在边的中点）
        allLinkLabels
            .attr('x', d => (d.source.x + d.target.x) / 2)
            .attr('y', d => (d.source.y + d.target.y) / 2);
        
                        // 更新节点组位置 - 移除边界限制，允许自由扩展
                allNodeGroups
                    .attr('transform', d => `translate(${d.x},${d.y})`);
                
                // 动态调整SVG视图以包含所有节点
                adjustViewBox();
    });
    
            console.log(`图表渲染完成: ${nodes.length} 个节点, ${validLinks.length} 个关系`);
        
        // 渲染完成后调整视图范围
        setTimeout(() => adjustViewBox(), 100);
}

// 查找初始节点
function findInitialNode() {
    if (!currentGraphData.nodes || currentGraphData.nodes.length === 0) return null;
    
    // 方法1: 查找expansion_order为0的节点
    let initialNode = currentGraphData.nodes.find(node => node.expansion_order === 0);
    if (initialNode) {
        console.log('通过expansion_order找到初始节点:', initialNode);
        return initialNode;
    }
    
    // 方法2: 获取用户输入的初始实体名称
    const initialEntityInput = document.getElementById('initial-entity');
    if (initialEntityInput && initialEntityInput.value.trim()) {
        const inputEntity = initialEntityInput.value.trim();
        initialNode = currentGraphData.nodes.find(node => 
            node.name === inputEntity || 
            node.id === inputEntity ||
            node.name.includes(inputEntity) ||
            inputEntity.includes(node.name)
        );
        if (initialNode) {
            console.log('通过用户输入找到初始节点:', initialNode, '输入:', inputEntity);
            return initialNode;
        }
    }
    
    // 方法3: 查找第一个添加的节点（通常是数组中的第一个）
    if (currentGraphData.nodes.length > 0) {
        initialNode = currentGraphData.nodes[0];
        console.log('使用第一个节点作为初始节点:', initialNode);
        return initialNode;
    }
    
    return null;
}

// 确保初始节点被正确标记为expansion状态
function ensureInitialNodeExpansionStatus() {
    if (!currentGraphData.nodes || currentGraphData.nodes.length === 0) return;
    
    // 查找初始节点
    const initialNode = findInitialNode();
    if (!initialNode) return;
    
    // 如果初始节点没有被标记为expansion状态，强制设置
    if (initialNode.expansion_status === 'normal' || !initialNode.expansion_status) {
        initialNode.expansion_status = 'expansion';
        initialNode.expansion_order = 0;
        console.log(`强制设置初始节点expansion状态: ${initialNode.name} (${initialNode.id})`);
    }
    
    // 确保所有expansion_order为数字的节点都有expansion状态
    currentGraphData.nodes.forEach(node => {
        if (typeof node.expansion_order === 'number' && node.expansion_order >= 0) {
            if (node.expansion_status === 'normal' || !node.expansion_status) {
                node.expansion_status = 'expansion';
                console.log(`更新节点expansion状态: ${node.name} (order: ${node.expansion_order})`);
            }
        }
    });
}

// 更新expansion状态显示
function updateExpansionDisplay() {
    if (!expansionInfo) return;
    
    const expansionContainer = document.getElementById('expansion-info');
    if (!expansionContainer) return;
    
    // 确保expansion状态正确
    ensureInitialNodeExpansionStatus();
    
    // 显示expansion信息容器
    expansionContainer.style.display = 'block';
    
    let html = `
        <div class="expansion-step">
            <strong>迭代 ${expansionInfo.iteration}: ${expansionInfo.action}</strong>
        </div>
        <div class="expansion-stats">
            <span>Expansion节点: ${expansionInfo.total_expansion_nodes}</span>
            <span>总节点: ${expansionInfo.total_nodes}</span>
        </div>
    `;
    
    if (expansionInfo.expansion_nodes && expansionInfo.expansion_nodes.length > 0) {
        html += '<div class="expansion-nodes">';
        html += '<strong>Expansion序列:</strong><br>';
        
        // 去重expansion节点列表 - 同时检查ID和名称
        const uniqueNodes = [];
        const seenIds = new Set();
        const seenNames = new Set();
        
        // 首先尝试找到初始节点并添加到序列开头
        const initialNode = findInitialNode();
        if (initialNode && !seenIds.has(initialNode.id) && !seenNames.has(initialNode.name)) {
            seenIds.add(initialNode.id);
            seenNames.add(initialNode.name);
            uniqueNodes.push({
                id: initialNode.id,
                name: initialNode.name,
                order: -1  // 标记为初始节点
            });
            console.log(`添加初始节点: ${initialNode.name} (${initialNode.id})`);
        }
        
        expansionInfo.expansion_nodes.forEach(node => {
            const nodeId = node.id;
            const nodeName = node.name;
            
            // 检查是否已经添加过相同ID或相同名称的节点
            if (!seenIds.has(nodeId) && !seenNames.has(nodeName)) {
                seenIds.add(nodeId);
                seenNames.add(nodeName);
                uniqueNodes.push(node);
            } else {
                console.log(`跳过重复节点: ${nodeName} (${nodeId})`);
            }
        });
        
        // 显示去重后的节点列表
        uniqueNodes.forEach((node, idx) => {
            const isCurrent = expansionInfo.current_node && node.id === expansionInfo.current_node.id;
            const isInitial = node.order === -1;
            let style = 'color: #60a5fa;';
            let suffix = '';
            
            if (isCurrent) {
                style = 'color: #1e40af; font-weight: bold;';
                suffix = ' (当前)';
            } else if (isInitial) {
                style = 'color: #10b981; font-weight: bold;';
                suffix = ' (初始)';
            }
            
            html += `<span style="${style}">${idx + 1}. ${node.name}${suffix}</span><br>`;
        });
        html += '</div>';
    }
    
    expansionContainer.innerHTML = html;
}

// 更新进度
function updateProgress(percent, text) {
    progressFill.style.width = `${percent}%`;
    progressText.textContent = text;
}

// 显示QA结果
function showQAResult(qaResult) {
    const qaResultContainer = document.getElementById('qa-result-container');
    
    if (qaResult && qaResult.question) {
        // 设置问题
        const qaContent = document.createElement('div');
        qaContent.className = 'qa-content';
        qaContent.innerHTML = `
            <div class="qa-question">
                <h3>❓ 问题</h3>
                <p>${qaResult.question}</p>
            </div>
            <div class="qa-answer">
                <h3>✅ 答案</h3>
                <p>${qaResult.answer || '暂无答案'}</p>
            </div>
            ${qaResult.reasoning_path || qaResult.reasoning ? `
                <div class="qa-reasoning">
                    <h3>${qaResult.reasoning_path ? '推理路径' : '推理过程'}</h3>
                    <p>${qaResult.reasoning_path || qaResult.reasoning}</p>
                </div>
            ` : ''}
        `;
        
        qaResultContainer.innerHTML = '';
        qaResultContainer.appendChild(qaContent);
        qaResultContainer.style.display = 'block';
    }
}

// 折叠/展开QA结果
function toggleQAResult() {
    const content = qaResultContent;
    const isHidden = content.style.display === 'none';
    content.style.display = isHidden ? 'block' : 'none';
    
    const button = document.querySelector('.qa-result-header .btn-small');
    button.textContent = isHidden ? '折叠' : '展开';
}

// 添加日志条目
function addLog(level, message) {
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry ${level}`;
    logEntry.innerHTML = `
        <span class="log-timestamp">[${timestamp}]</span> ${message}
    `;
    
    logContainer.appendChild(logEntry);
    logContainer.scrollTop = logContainer.scrollHeight;
}

// 清空日志
function clearLogs() {
    logContainer.innerHTML = '';
}

// 图谱控制函数
function zoomIn() {
    if (!svg || !zoom) return;
    svg.transition().duration(200).call(zoom.scaleBy, 1.4);
}

function zoomOut() {
    if (!svg || !zoom) return;
    svg.transition().duration(200).call(zoom.scaleBy, 1 / 1.4);
}

function resetZoom() {
    if (!svg || !zoom || !g) return;
    
    // 计算图谱的边界
    const nodes = g.selectAll('.node').nodes();
    if (nodes.length === 0) {
        svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
        return;
    }
    
    // 获取所有节点的位置
    const positions = nodes.map(node => {
        const transform = d3.select(node).attr('transform');
        const match = transform.match(/translate\(([^,]+),([^)]+)\)/);
        return match ? [+match[1], +match[2]] : [0, 0];
    });
    
    const xExtent = d3.extent(positions, d => d[0]);
    const yExtent = d3.extent(positions, d => d[1]);
    
    const padding = 100;
    const graphWidth = (xExtent[1] - xExtent[0]) + padding * 2;
    const graphHeight = (yExtent[1] - yExtent[0]) + padding * 2;
    
    const containerWidth = graphContainer.clientWidth;
    const containerHeight = graphContainer.clientHeight;
    
    const scale = Math.min(
        containerWidth / graphWidth,
        containerHeight / graphHeight,
        2.0
    );
    
    const centerX = containerWidth / 2 - (xExtent[0] + xExtent[1]) / 2 * scale;
    const centerY = containerHeight / 2 - (yExtent[0] + yExtent[1]) / 2 * scale;
    
    svg.transition().duration(500).call(
        zoom.transform,
        d3.zoomIdentity.translate(centerX, centerY).scale(scale)
    );
}

function fitView() {
    if (!g || !simulation || g.selectAll('.node').empty()) return;
    
    const nodes = g.selectAll('.node').data();
    if (nodes.length === 0) return;
    
    const xExtent = d3.extent(nodes, d => d.x);
    const yExtent = d3.extent(nodes, d => d.y);
    
    if (!xExtent[0] || !xExtent[1] || !yExtent[0] || !yExtent[1]) return;
    
    const padding = 100;
    const graphWidth = Math.max(xExtent[1] - xExtent[0], 200) + padding * 2;
    const graphHeight = Math.max(yExtent[1] - yExtent[0], 200) + padding * 2;
    
    const scale = Math.min(graphContainer.clientWidth / graphWidth, graphContainer.clientHeight / graphHeight, 1.5);
    const centerX = graphContainer.clientWidth / 2 - (xExtent[0] + xExtent[1]) / 2 * scale;
    const centerY = graphContainer.clientHeight / 2 - (yExtent[0] + yExtent[1]) / 2 * scale;
    
    svg.transition().duration(1000).call(
        zoom.transform,
        d3.zoomIdentity.translate(centerX, centerY).scale(scale)
    );
}

function redistributeNodes() {
    if (!g || !simulation || currentGraphData.nodes.length === 0) return;
    
    const nodes = currentGraphData.nodes;
    
    // 重新计算所有节点位置
    nodes.forEach((node, index) => {
        const positionedNode = createPositionedNode(node.id, node.name, node.type, index, nodes.length);
        node.x = positionedNode.x;
        node.y = positionedNode.y;
        // 清除固定位置，允许力导向调整
        node.fx = null;
        node.fy = null;
    });
    
    // 重新启动模拟
    simulation.nodes(nodes);
    simulation.alpha(0.8).restart();  // 适度重启，避免过于剧烈的变化
    
    // 调整视图以适应新的节点分布
    setTimeout(() => adjustViewBox(), 200);
}

// Socket.IO事件监听
socket.on('connect', function() {
    console.log('已连接到服务器');
    addLog('INFO', '已连接到服务器');
    
    // 测试WebSocket连接
    console.log('WebSocket连接状态:', socket.connected);
});

socket.on('disconnect', function() {
    console.log('已断开连接');
    addLog('WARNING', '已断开与服务器的连接');
});

socket.on('log_message', function(data) {
    // 如果有trace_id，在消息中显示
    let message = data.message;
    if (data.trace_id && data.trace_id !== 'NO_TRACE') {
        message = `[${data.trace_id}] ${message}`;
    }
    addLog(data.level, message);
});

socket.on('progress_update', function(data) {
    console.log('收到进度更新:', data);
    updateProgress(data.progress, data.step);
});

socket.on('graph_update', function(data) {
    console.log('收到图谱更新:', data);
    
    // 调试expansion状态
    if (data.nodes) {
        const expansionNodes = data.nodes.filter(n => n.expansion_status === 'expansion' || n.expansion_status === 'current');
        console.log('Expansion节点数据:', expansionNodes.map(n => ({
            id: n.id,
            name: n.name,
            status: n.expansion_status,
            order: n.expansion_order
        })));
    }
    
    // 如果有expansion信息，显示expansion容器
    if (data.expansion_info) {
        const expansionContainer = document.getElementById('expansion-info');
        if (expansionContainer) {
            expansionContainer.style.display = 'block';
        }
        console.log('Expansion信息:', data.expansion_info);
    }
    
    updateGraph(data, true);
});

socket.on('sampled_graph_update', function(data) {
    console.log('收到星座图更新:', data);
    const sampledNodes = data.nodes.map(node => ({...node, sampled: true}));
    const sampledLinks = data.links.map(link => ({...link, sampled: true}));
    highlightSampledGraph(sampledNodes, sampledLinks);
    addLog('INFO', `星座图高亮：${data.nodes.length} 个节点，${data.links.length} 个关系`);
});

socket.on('building_complete', function(data) {
    console.log('构建完成:', data);
    console.log('构建完成数据详情:', {
        hasGraphData: !!data.graph_data,
        hasQAResult: !!data.qa_result,
        graphNodes: data.graph_data ? data.graph_data.nodes.length : 0,
        graphLinks: data.graph_data ? data.graph_data.links.length : 0
    });
    isBuilding = false;
    startBtn.disabled = false;
    stopBtn.disabled = true;
    
    // 不再在building_complete中更新图表，避免重复
    // 图表应该已经通过graph_update事件更新过了
    
    if (data.qa_result) {
        showQAResult(data.qa_result);
        addLog('INFO', '问答对已生成');
        
        // 显示QA内容摘要
        if (data.qa_result.question) {
            addLog('INFO', `问题: ${data.qa_result.question.substring(0, 100)}${data.qa_result.question.length > 100 ? '...' : ''}`);
        }
        if (data.qa_result.answer) {
            addLog('INFO', `答案: ${data.qa_result.answer.substring(0, 100)}${data.qa_result.answer.length > 100 ? '...' : ''}`);
        }
    }
    
    addLog('SUCCESS', '知识图谱构建完成！');
});

socket.on('error', function(data) {
    console.error('错误:', data);
    addLog('ERROR', data.message || '发生未知错误');
    
    isBuilding = false;
    startBtn.disabled = false;
    stopBtn.disabled = true;
});

// 按钮事件处理
startBtn.addEventListener('click', function() {
    if (isBuilding) return;
    
    const entity = document.getElementById('initial-entity').value.trim();
    const maxRelations = parseInt(document.getElementById('max-relations').value) || 50;
    const maxIterations = parseInt(document.getElementById('max-iterations').value) || 3;
    const sampleSize = parseInt(document.getElementById('sample-size').value) || 8;
    const samplingAlgorithm = document.getElementById('sampling-algorithm').value || 'mixed';
    
    if (!entity) {
        alert('请输入初始实体');
        return;
    }
    
    // 清空图谱和日志
    clearGraph();
    clearLogs();
    qaResultContainer.style.display = 'none';
    
    // 更新UI状态
    isBuilding = true;
    startBtn.disabled = true;
    stopBtn.disabled = false;
    
    // 发送构建请求
    fetch('/api/start_building', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            entity: entity,
            max_nodes: maxRelations, // 这里传递最大关系数
            max_iterations: maxIterations,
            sample_size: sampleSize,
            sampling_algorithm: samplingAlgorithm
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            throw new Error(data.error);
        }
        addLog('INFO', `开始构建知识图谱：${entity}`);
    })
    .catch(error => {
        console.error('构建失败:', error);
        addLog('ERROR', `构建失败: ${error.message}`);
        isBuilding = false;
        startBtn.disabled = false;
        stopBtn.disabled = true;
    });
});

stopBtn.addEventListener('click', function() {
    fetch('/api/stop_building', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        addLog('INFO', '已停止构建');
        isBuilding = false;
        startBtn.disabled = false;
        stopBtn.disabled = true;
    })
    .catch(error => {
        console.error('停止失败:', error);
        addLog('ERROR', `停止失败: ${error.message}`);
    });
});

// 窗口大小变化时重新调整图谱
window.addEventListener('resize', function() {
    if (svg && graphContainer && simulation) {
        const width = graphContainer.clientWidth;
        const height = graphContainer.clientHeight;
        
        svg.attr('width', width).attr('height', height);
        
        // 更新力导向布局的中心点和碰撞检测
        simulation.force('center', d3.forceCenter(width / 2, height / 2))
                  .force('collision', d3.forceCollide().radius(d => getNodeRadius(d) + 10).strength(0.9))
                  .alpha(0.2)  // 轻微重启，避免剧烈变化
                  .restart();
    }
});

// 测试tooltip显示
window.testTooltip = function() {
    const tooltip = document.getElementById('tooltip');
    if (!tooltip) {
        const newTooltip = document.createElement('div');
        newTooltip.id = 'tooltip';
        document.body.appendChild(newTooltip);
        console.log('创建了测试tooltip');
    }
    
    const testTooltip = document.getElementById('tooltip');
    testTooltip.innerHTML = '<strong style="color: white;">测试Tooltip - 如果你看到这个，说明tooltip正常工作!</strong>';
    testTooltip.style.position = 'fixed';
    testTooltip.style.top = '100px';
    testTooltip.style.left = '100px';
    testTooltip.style.zIndex = '9999';
    testTooltip.style.background = 'rgba(15, 23, 42, 0.95)';
    testTooltip.style.color = 'white';
    testTooltip.style.padding = '12px 16px';
    testTooltip.style.borderRadius = '8px';
    testTooltip.style.border = '1px solid rgba(255, 255, 255, 0.1)';
    testTooltip.style.visibility = 'visible';
    testTooltip.classList.add('show');
    
    console.log('测试tooltip已显示在屏幕左上角，3秒后自动隐藏');
    
    setTimeout(() => {
        testTooltip.style.visibility = 'hidden';
        testTooltip.classList.remove('show');
        console.log('测试tooltip已隐藏');
    }, 3000);
};

// 调试函数 - 在浏览器控制台中调用 debugGraph() 来查看节点状态
window.debugGraph = function() {
    console.log('=== 图谱调试信息 ===');
    
    // 确保expansion状态是最新的
    ensureInitialNodeExpansionStatus();
    
    console.log('当前节点数:', currentGraphData.nodes.length);
    console.log('当前连线数:', currentGraphData.links.length);
    console.log('所有节点信息:');
    currentGraphData.nodes.forEach((node, idx) => {
        console.log(`节点${idx + 1}:`, {
            id: node.id,
            name: node.name,
            type: node.type,
            expansion_status: node.expansion_status,
            expansion_order: node.expansion_order
        });
    });
    
    const expansionNodes = currentGraphData.nodes.filter(n => n.expansion_status === 'expansion' || n.expansion_status === 'current');
    console.log('Expansion节点:', expansionNodes.map(n => ({
        name: n.name,
        id: n.id,
        status: n.expansion_status,
        order: n.expansion_order
    })));
    
    // 调试expansion序列
    if (expansionInfo) {
        console.log('ExpansionInfo:', expansionInfo);
        console.log('ExpansionInfo.expansion_nodes:', expansionInfo.expansion_nodes);
    }
    
    console.log('SVG节点组数量:', g ? g.selectAll('.node-group').size() : 0);
    console.log('SVG连线数量:', g ? g.selectAll('.link').size() : 0);
    
    // 查找初始节点
    const initialNode = findInitialNode();
    console.log('识别的初始节点:', initialNode);
    
    console.log('==================');
};

// 添加tooltip调试函数
window.debugTooltip = function() {
    const tooltip = document.getElementById('tooltip');
    console.log('Tooltip元素:', tooltip);
    console.log('Tooltip内容:', tooltip ? tooltip.innerHTML : 'null');
    console.log('Tooltip类名:', tooltip ? tooltip.className : 'null');
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initGraph();
    addLog('INFO', '系统已初始化，准备就绪');
    console.log('调试提示: 在控制台中输入 debugGraph() 来查看节点状态');
}); 