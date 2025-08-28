# Intelligent Knowledge Graph Construction System - Web Interface Features Guide

## 🌐 System Overview

This system provides a comprehensive web-based visualization interface that supports the complete workflow from knowledge graph construction to high-quality QA generation. It features modern frontend design with integrated real-time charts, interactive graph visualization, and intelligent data management capabilities.

## 📱 Page Navigation & Features

### 🏠 Main Navigation Page (`/`)
**Template File**: `templates/navigation.html`

**Core Features**:
- 🎯 **Modern Card-Style Navigation** - Intuitive functional module selection interface
- 📊 **Quick Status Overview** - System status and recent activity display
- 🚀 **One-Click Access** - Quick access to all functional modules
- 📱 **Responsive Design** - Compatible with desktop and mobile devices

**Use Cases**: System entry point, feature overview, and quick navigation

---

### 🔬 Single QA Testing Page (`/single-qa`)
**Template File**: `templates/single_qa.html`

**Core Features**:
- **📝 Entity Input Module**
  - Smart input field supporting entity names (e.g., "diabetes", "artificial intelligence")
  - Real-time input validation and suggestions
  
- **⚙️ Parameter Control Panel**
  - Maximum nodes setting (recommended 100-400)
  - Iteration count control (recommended 5-15)
  - Sampling strategy selection (5 algorithms: mixed, max_chain, etc.)
  
- **📈 Real-time Visualization Module**
  - Left-side D3.js force-directed graph showing real-time graph construction
  - Dynamic rendering of nodes and connections
  - Interactive graph operations (zoom, drag, node click)
  
- **📋 Detailed Log Stream**
  - Right-side real-time log display with WebSocket updates
  - Construction step tracking and error monitoring
  - Trace ID support for issue diagnosis
  
- **🎯 QA Results Display**
  - Generated question-answer pairs after construction completion
  - Answer quality analysis and metadata information

**Use Cases**: Single entity deep analysis, algorithm testing, parameter tuning validation

---

### 🚀 Batch Generation Page (`/batch-generation`)
**Template File**: `templates/batch_generation.html`

**Core Features**:
- **📂 Multiple Data Source Support**
  - ✏️ **Manual Input** - Bulk entity input via text box with line separation
  - 📁 **File Upload** - Multiple format support: .txt, .csv, .json, .jsonl
  
- **⚙️ Batch Configuration Panel**
  - Generation quantity control (supports 1-1000 entities)
  - Sampling parameter settings (nodes, iterations, algorithm selection)
  - Quality level settings (fast/standard/high-quality modes)
  - QPS limits and concurrency control
  
- **📊 Real-time Monitoring Dashboard**
  - Current processing entity display
  - Overall progress bar and percentage
  - Success rate statistics and failure records
  - Estimated completion time (ETA)
  
- **💾 Results Management Module**
  - Real-time preview of generated results
  - One-click JSONL format download
  - Save to evaluation dataset functionality
  - Failed task retry mechanism

**Use Cases**: Large-scale QA dataset generation, educational training data preparation, enterprise knowledge base construction

---

### 📊 Data Evaluation Page (`/data-evaluation`)
**Template File**: `templates/data_evaluation.html`

**Core Features**:
- **🔍 Intelligent Evaluation Engine**
  - 🧠 **DeepSeek R1 Model** - High-quality answer generation based on latest reasoning model
  - ⚖️ **Smart Comparison** - Automatic comparison between standard and predicted answers
  - 📊 **Multi-dimensional Assessment** - Accuracy, similarity, language quality, logical consistency
  
- **📈 Evaluation Dimension Analysis**
  - Answer accuracy statistics
  - Semantic similarity calculation
  - Reasoning chain completeness check
  - Knowledge coverage analysis
  
- **📊 Visualization Analysis Module**
  - Chart.js interactive charts
  - Multi-dimensional radar charts
  - Time series trend analysis
  - Error type distribution statistics
  
- **💼 Dataset Management**
  - Upload evaluation datasets
  - Batch evaluation task management
  - Evaluation result download and export
  - Historical evaluation record queries

**Use Cases**: QA quality assessment, model performance analysis, dataset quality control

---

### 🆚 Comparison Evaluation Page (`/comparison-evaluation`)
**Template File**: `templates/comparison_evaluation.html`

**Core Features**:
- **🔄 A/B Testing Framework**
  - Parallel comparison of multiple datasets
  - Performance comparison across different models
  - Algorithm effectiveness comparative analysis
  
- **📊 Comparison Dimension Settings**
  - Custom evaluation metrics
  - Weight allocation mechanisms
  - Statistical significance testing
  
- **📈 Visual Comparison Reports**
  - Side-by-side comparison charts
  - Difference heatmaps
  - Performance improvement/degradation analysis
  
- **💾 Comparison History Management**
  - Historical comparison record queries
  - Comparison result export
  - Report generation and sharing

**Use Cases**: Algorithm performance comparison, model upgrade validation, quality improvement analysis

---

### 🗃️ Data Management Page (`/data-management`)
**Template File**: `templates/data_management.html`

**Core Features**:
- **📁 Dataset Management Center**
  - View, edit, and delete generated datasets
  - Multi-format support (JSONL, JSON, CSV)
  - Dataset merge and split functionality
  
- **🔍 Smart Content Preview**
  - Online QA content preview with pagination
  - Keyword search and filtering capabilities
  - Real-time data quality checking
  
- **📊 Quality Analysis Tools**
  - Dataset statistics (question count, average length, etc.)
  - Quality distribution analysis and visualization
  - Anomaly detection and marking
  
- **🔧 Data Preprocessing Tools**
  - Language detection and classification
  - Information leakage detection
  - Entity replacement and anonymization
  - Duplicate data removal
  
- **📥 Batch Operations**
  - Batch format conversion
  - Multi-file merge processing
  - Bulk download and export

**Use Cases**: Data cleaning, quality control, format conversion, dataset maintenance

---

### 🏷️ Domain Tagging Page (`/domain-tags`)
**Template File**: `templates/domain_tags.html`

**Core Features**:
- **🎯 Smart Auto-Tagging**
  - AI automatic entity domain identification (medical, technology, culture, education, etc.)
  - LLM-based semantic understanding annotation
  - Batch annotation processing support
  
- **✏️ Manual Correction Functions**
  - Manual annotation and editing interface
  - Batch tag modification tools
  - Annotation history and rollback
  
- **📊 Statistical Analysis Module**
  - Domain distribution statistical charts
  - Annotation quality analysis
  - Domain coverage assessment
  
- **🏷️ Tag Management System**
  - Predefined domain tag library (sports, academic, politics, entertainment, literature, culture, economics, technology, history, medical, etc.)
  - Custom tag creation
  - Tag hierarchy management

**Use Cases**: Dataset classification, domain specialization, content organization, knowledge categorization

---

### 📚 Runs QA Generation Page (`/runs-qa-generation`)
**Template File**: `templates/runs_qa_generation.html`

**Core Features**:
- **📂 Run Record Management**
  - Historical construction run record viewing
  - Run status and metadata display
  - Failed task reprocessing
  
- **🔄 Secondary QA Generation**
  - Generate new QA based on existing graph data
  - Secondary application of different sampling strategies
  - QPS-controlled batch processing
  
- **📊 Performance Monitoring**
  - Real-time generation progress tracking
  - Success rate and quality statistics
  - Resource usage monitoring
  
- **💾 Result Integration**
  - Multi-run result merging
  - Incremental update support
  - Version management and rollback

**Use Cases**: Graph reuse, incremental generation, historical data utilization

---

### 🎯 Final Datasets Page (`/final-datasets`)
**Template File**: `templates/final_datasets.html`

**Core Features**:
- **📋 Dataset Overview**
  - Final production dataset management
  - Version control and tag management
  - Dataset metadata display
  
- **🔍 Advanced Filtering**
  - Multi-dimensional data filtering
  - Custom query conditions
  - Real-time search and filtering
  
- **📊 Quality Assurance**
  - Unique ID management and validation
  - Duplicate data detection
  - Data integrity checking
  
- **📤 Production-Ready Export**
  - Multi-format export support
  - Bulk download functionality
  - Deployment-ready data package generation

**Use Cases**: Production data management, official releases, quality review, version publishing

---

## 🔧 Technical Features

### 📡 Real-time Communication
- **WebSocket Support** - All pages support real-time status updates
- **Progress Tracking** - Real-time progress display for long-running tasks
- **Error Monitoring** - Real-time error capture and user alerts

### 🎨 Modern UI
- **Responsive Design** - Beautiful Bootstrap-based interface
- **Interactive Charts** - Chart.js and D3.js visualization components
- **Intuitive Operations** - Drag-and-drop, click, batch selection interactions

### 💾 Data Persistence
- **Auto-save** - Automatic result saving to prevent data loss
- **Resume Capability** - Support for interruption recovery of large tasks
- **Version Management** - Version tracking for data changes

### 🔒 Quality Assurance
- **Parameter Validation** - Real-time input parameter validation
- **Error Handling** - Comprehensive error capture and notification mechanisms
- **Log Tracking** - Detailed operation logs and Trace support

## 🎯 Usage Recommendations

### 🚀 Quick Start Workflow
1. **Main Navigation** → Understand system capabilities
2. **Single QA Testing** → Familiarize with basic operations
3. **Batch Generation** → Process actual data
4. **Data Evaluation** → Validate result quality
5. **Data Management** → Organize and optimize data

### 💡 Best Practices
- **Test First**: Use single QA testing to validate parameter settings
- **Batch Processing**: Process large datasets in batches
- **Quality Monitoring**: Regularly use evaluation features to check data quality
- **Backup Important Data**: Download and backup important data promptly
- **Parameter Tuning**: Adjust generation parameters based on specific needs

### 🔄 Typical Workflows

#### 🎓 Educational Training Scenario
```
Entity Preparation → Single QA Testing → Batch Generation → Quality Evaluation → Final Export
```

#### 🔬 Research Development Scenario
```
Literature Entities → Parameter Tuning → Large-scale Generation → Comparative Analysis → Publication
```

#### 🏢 Enterprise Application Scenario
```
Domain Terms → Custom Tagging → Batch Processing → Quality Control → Production Deployment
```

### ⚙️ Performance Optimization

#### 🚀 High-Speed Processing Mode
- Increase parallel workers (recommended ≤5)
- Higher QPS limits (note API restrictions)
- Reduce max nodes and sample size
- Optimize model selection in configuration

#### 🎯 High-Quality Mode
- Increase sample size (recommended 15-20)
- Increase max nodes (recommended 250-400)
- Use max_chain sampling algorithm
- Increase max iterations

#### 💰 Cost-Optimized Mode
- Single worker with low QPS
- Smaller sample sizes
- Efficient model selection
- Batch processing scheduling

## 📊 Output Formats & Integration

### 📄 Supported Export Formats
- **JSONL** - Standard question-answer pairs
- **JSON** - Structured data with metadata
- **CSV** - Tabular format for analysis
- **TXT** - Plain text for simple use cases

### 🔌 API Integration
- **REST APIs** - All page functions accessible via REST
- **WebSocket Events** - Real-time status updates
- **Batch Processing** - Asynchronous task management
- **Authentication** - Secure access control

### 📈 Analytics & Reporting
- **Performance Metrics** - Generation speed, success rates
- **Quality Metrics** - Accuracy, consistency, coverage
- **Usage Statistics** - User activity, resource utilization
- **Custom Reports** - Configurable analysis dashboards

## 🛠️ Troubleshooting

### ❌ Common Issues
- **Connection Problems**: Check WebSocket connectivity
- **Performance Issues**: Adjust concurrency settings
- **Quality Problems**: Review parameter configurations
- **Data Issues**: Use validation and cleaning tools

### 📞 Support Resources
- **System Logs**: Detailed logging with trace IDs
- **Error Messages**: Clear error descriptions and solutions
- **Documentation**: Comprehensive user guides
- **Community**: User forums and knowledge base

---

📞 **Technical Support**: Check system logs or contact technical team for issues
⭐ **Continuous Updates**: System features are continuously optimized, check update notes regularly
🌟 **Open Source**: Contributions welcome - submit issues and pull requests!
