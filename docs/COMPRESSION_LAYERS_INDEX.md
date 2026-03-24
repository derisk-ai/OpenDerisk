# Compression Layers - Complete Documentation Index

## 📚 Documentation Files

All three layers (Truncation, Pruning, Compaction) have been fully mapped and documented.

### 1. **COMPRESSION_LAYERS_MAPPING.md** ⭐ START HERE
   **Comprehensive architecture document (18KB)**
   
   Contains:
   - Complete overview of all three compression layers
   - Detailed code analysis for each layer
   - File locations and class descriptions
   - Method signatures and parameters
   - Data classes and result structures
   - Cross-layer integration patterns
   - Message metadata tracking system
   - Token estimation formulas
   - Configuration patterns
   - Logging points mapped by file and line
   - Differences between expand vs core_v2 implementations
   - Test file locations

   **Best for:** Understanding the complete architecture

---

### 2. **COMPRESSION_LAYERS_QUICK_REFERENCE.md** ⚡ QUICK LOOKUP
   **Quick reference guide (11KB)**
   
   Contains:
   - One-page summary per layer
   - Configuration parameters cheat sheet
   - Logging quick map
   - Message type classification
   - File storage strategies
   - Integration points
   - Token estimation quick formula
   - Typical flow example
   - Debugging tips
   - Common issues & solutions
   - Key takeaways

   **Best for:** Quick reference during implementation

---

### 3. **COMPRESSION_LAYERS_FILE_INVENTORY.md** 📂 IMPLEMENTATION GUIDE
   **File organization and API reference (14KB)**
   
   Contains:
   - Complete file organization by layer
   - Key classes & methods for each layer
   - Data flow diagram
   - Detailed logging locations with line numbers
   - Configuration hierarchy
   - Testing information
   - Four integration paths (ReActMaster, Core v2, Unified, Hierarchical)
   - Navigation commands
   - Summary statistics

   **Best for:** Implementation and code navigation

---

## 🎯 Quick Start Guide

### To Understand the Architecture
1. Read **COMPRESSION_LAYERS_MAPPING.md** sections:
   - "Overview"
   - "Layer 1/2/3: Implementation Files"
   - "Cross-Layer Integration"

### To Find Specific Code
1. Use **COMPRESSION_LAYERS_QUICK_REFERENCE.md** section "Layer Locations"
2. Or use **COMPRESSION_LAYERS_FILE_INVENTORY.md** sections:
   - "File Organization by Layer"
   - "Key Classes & Methods"

### To Implement Features
1. Reference **COMPRESSION_LAYERS_FILE_INVENTORY.md**:
   - "Integration Paths" (4 different approaches)
   - "Logging Locations" (exact file:line pairs)

### To Debug Issues
1. Use **COMPRESSION_LAYERS_QUICK_REFERENCE.md**:
   - "Debugging Tips"
   - "Common Issues"

---

## 📍 File Locations Summary

### Layer 1: Truncation 🔪
```
expand:
  packages/derisk-core/src/derisk/agent/expand/react_master_agent/truncation.py
core_v2:
  packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/output_truncator.py
```

### Layer 2: Pruning ✂️
```
expand:
  packages/derisk-core/src/derisk/agent/expand/react_master_agent/prune.py
core_v2:
  packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/history_pruner.py
```

### Layer 3: Compaction 📦
```
expand:
  packages/derisk-core/src/derisk/agent/expand/react_master_agent/session_compaction.py
core_v2:
  packages/derisk-core/src/derisk/agent/core_v2/builtin_agents/react_components/context_compactor.py
shared:
  packages/derisk-core/src/derisk/agent/shared/hierarchical_context/hierarchical_compactor.py
unified:
  packages/derisk-core/src/derisk/agent/core/memory/compaction_pipeline.py
```

---

## 🔑 Key Concepts at a Glance

### Three-Layer Compression Architecture
```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Truncation (Immediate)                          │
│ - Truncates single large tool output                     │
│ - Saves full content to AgentFileSystem                  │
│ - Default: 50 lines / 5KB (expand) or 2000/50KB (v2)    │
│ - Triggers: When single output exceeds limit            │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Pruning (Periodic)                              │
│ - Marks old tool outputs with placeholder                │
│ - Preserves context metadata                             │
│ - Default: 4000 tokens threshold                         │
│ - Triggers: Every 5 rounds or when tokens accumulate    │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Compaction (On Demand)                          │
│ - Summarizes old messages using LLM                      │
│ - Archives compressed chapters                           │
│ - Default: 80% of 128K token window = 102.4K            │
│ - Triggers: When context exceeds threshold               │
└─────────────────────────────────────────────────────────┘
```

### Message Metadata Tracking
```
Truncation adds:
  - file_key (AFS identifier for full content)
  - suggestion (hint for agent how to access full content)

Pruning adds:
  - context["compacted"] = True
  - context["compacted_at"] = timestamp
  - context["original_summary"] = brief excerpt

Compaction adds:
  - context["is_compaction_summary"] = True
  - context["compacted_roles"] = [list of compressed roles]
  - context["compaction_timestamp"] = timestamp
```

### Token Estimation
```
Tokens ≈ len(text_in_characters) / 4

Triggers:
  - Prune: cumulative tokens > 4000
  - Compact: total tokens > 102400 (80% of 128K)
```

---

## 📊 Statistics

| Metric | Count |
|--------|-------|
| Total compression-related files | 20+ |
| Lines of code | 3000+ |
| Distinct log points | 20+ |
| Configuration parameters | 30+ |
| Message metadata flags | 10+ |
| Supported integrations | 4+ |

---

## 🔍 Search Tips

### Find Truncation Code
```bash
grep -r "class Truncator" packages/derisk-core/src/
grep -r "truncate" packages/derisk-core/src/derisk/agent/expand/react_master_agent/
```

### Find Pruning Code
```bash
grep -r "class.*Pruner" packages/derisk-core/src/
grep -r "compacted" packages/derisk-core/src/derisk/agent/expand/react_master_agent/
```

### Find Compaction Code
```bash
grep -r "class.*Compaction" packages/derisk-core/src/
grep -r "is_overflow" packages/derisk-core/src/
```

### Find Logging Statements
```bash
grep -r "logger.info" packages/derisk-core/src/derisk/agent/ | grep -E "(Truncat|Prun|Compact)"
grep -r "\[AFS\]" packages/derisk-core/src/
grep -r "\[Truncator\]" packages/derisk-core/src/
grep -r "\[Pruner\]" packages/derisk-core/src/
grep -r "\[Compactor\]" packages/derisk-core/src/
```

---

## 🎓 Learning Path

### Phase 1: Understanding (Read First)
1. COMPRESSION_LAYERS_MAPPING.md - Architecture overview
2. COMPRESSION_LAYERS_QUICK_REFERENCE.md - Layer summaries

### Phase 2: Implementation (Use for Coding)
1. COMPRESSION_LAYERS_FILE_INVENTORY.md - File locations
2. COMPRESSION_LAYERS_QUICK_REFERENCE.md - Config parameters
3. Source code files for exact implementation

### Phase 3: Integration (Multiple Approaches)
1. ReActMasterAgent - All-in-one solution
2. Core v2 Components - Pick and choose
3. Unified Pipeline - v1 + v2 compatibility
4. Hierarchical Compaction - Advanced chapter-based

### Phase 4: Debugging & Optimization
1. COMPRESSION_LAYERS_QUICK_REFERENCE.md - Debugging tips
2. Logging statements in source code
3. Test files for reference implementations

---

## ✅ What's Documented

### Layer 1: Truncation
- ✅ Main implementation (expand/truncation.py)
- ✅ Simplified version (core_v2/output_truncator.py)
- ✅ AgentFileSystem integration
- ✅ Legacy fallback mode
- ✅ Async/sync versions
- ✅ Logging points
- ✅ Configuration options

### Layer 2: Pruning
- ✅ Main implementation (expand/prune.py)
- ✅ Simplified version (core_v2/history_pruner.py)
- ✅ Message classification
- ✅ Token-based strategy
- ✅ Metadata preservation
- ✅ Logging points
- ✅ Configuration options

### Layer 3: Compaction
- ✅ Session compaction (expand/session_compaction.py)
- ✅ Context compaction (core_v2/context_compactor.py)
- ✅ Hierarchical compaction (shared/hierarchical_compactor.py)
- ✅ Unified pipeline (core/memory/compaction_pipeline.py)
- ✅ LLM-based summarization
- ✅ Logging points
- ✅ Configuration options
- ✅ Archive system

### Supporting Infrastructure
- ✅ Message adapters (v1/v2 compatibility)
- ✅ History archival system
- ✅ Token estimation
- ✅ Content protection mechanisms
- ✅ Recovery tools

### Testing & Integration
- ✅ Test file locations
- ✅ Integration paths
- ✅ Configuration hierarchy
- ✅ Data flow diagrams

---

## 🚀 Next Steps

The documentation is complete. Ready for:

1. **Logging Instrumentation** - Add detailed logging to each layer
2. **Monitoring Dashboard** - Track compression metrics
3. **Performance Benchmarking** - Measure token savings
4. **Integration Testing** - Validate long conversation flows
5. **Recovery Tools** - Add debugging/recovery utilities
6. **Documentation Generation** - Auto-generate from docstrings

---

## 📞 Document Cross-References

### MAPPING.md References
- Architecture Overview → QUICK_REFERENCE.md "Three-Layer Architecture"
- File Locations → FILE_INVENTORY.md "File Organization by Layer"
- Configuration → QUICK_REFERENCE.md "Configuration Parameters"
- Logging → FILE_INVENTORY.md "Logging Locations"

### QUICK_REFERENCE.md References
- Layer Details → MAPPING.md "Layer 1/2/3: Core Implementation Files"
- Integration → FILE_INVENTORY.md "Integration Paths"
- Configuration → MAPPING.md "Configuration Patterns"

### FILE_INVENTORY.md References
- Complete Code → Source files in packages/derisk-core/src/
- Testing → packages/derisk-core/tests/
- Architecture → MAPPING.md "Cross-Layer Integration"

---

## 📋 Document Maintenance

Last updated: 2025-03-04

Documents cover:
- All production code in packages/derisk-core/src/
- All test files in packages/derisk-core/tests/
- All documentation in docs/

If you find outdated information:
1. Update the source code
2. Update relevant documentation file
3. Cross-reference between documents
