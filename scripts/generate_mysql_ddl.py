#!/usr/bin/env python3
"""
Generate MySQL DDL scripts from SQLAlchemy ORM model files.

This script parses the ORM model files and generates MySQL-compatible CREATE TABLE statements.
Supports both full DDL and incremental DDL generation.
"""

import os
import re
import sys
from pathlib import Path
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime


def get_project_version(project_root: Path) -> str:
    """Get the current project version from packages/__init__.py."""
    version_file = project_root / "packages" / "__init__.py"
    if version_file.exists():
        content = version_file.read_text(encoding='utf-8')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "0.0.0"


def parse_column_from_text(text, class_start, class_end):
    """Parse columns from a class definition text."""
    columns = []
    
    # Get the class body
    class_body = text[class_start:class_end]
    
    # Find all Column definitions
    # Pattern to match: column_name = Column(...)
    column_pattern = r'^\s*(\w+)\s*=\s*Column\s*\('
    
    lines = class_body.split('\n')
    current_col = None
    current_col_text = []
    
    for line in lines:
        # Skip comments and docstrings
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        
        # Check for new column definition
        match = re.match(column_pattern, line)
        if match:
            # Save previous column if exists
            if current_col and current_col_text:
                col_info = parse_column_definition(current_col, '\n'.join(current_col_text))
                if col_info:
                    columns.append(col_info)
            
            current_col = match.group(1)
            current_col_text = [line]
        elif current_col:
            # Continue capturing the current column definition
            current_col_text.append(line)
            # Check if this line ends the column definition
            if ')' in line and not line.strip().endswith(','):
                col_info = parse_column_definition(current_col, '\n'.join(current_col_text))
                if col_info:
                    columns.append(col_info)
                current_col = None
                current_col_text = []
    
    # Don't forget the last column
    if current_col and current_col_text:
        col_info = parse_column_definition(current_col, '\n'.join(current_col_text))
        if col_info:
            columns.append(col_info)
    
    return columns


def parse_column_definition(col_name, col_text):
    """Parse a single column definition."""
    col_text = col_text.strip()
    
    match = re.search(r'Column\s*\((.*)\)\s*$', col_text, re.DOTALL)
    if not match:
        return None
    
    args_text = match.group(1)
    
    col_type = None
    type_args = ''
    
    type_patterns = [
        (r'^\s*(\w+)\s*\(\s*length\s*=\s*([^)]+)\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*\(\s*(\d+)\s*\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*\(\s*([^)]+)\s*\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*,', lambda m: (m.group(1), '')),
        (r'^\s*(\w+)\s*$', lambda m: (m.group(1), '')),
    ]
    
    for pattern, extractor in type_patterns:
        type_match = re.match(pattern, args_text)
        if type_match:
            col_type, type_args = extractor(type_match)
            break
    
    if not col_type:
        return None
    
    # Check for primary_key
    is_primary = 'primary_key=True' in args_text or 'primary_key = True' in args_text
    
    # Check for nullable
    is_nullable = True
    if 'nullable=False' in args_text or 'nullable = False' in args_text:
        is_nullable = False
    
    # Check for autoincrement
    is_autoincrement = 'autoincrement=True' in args_text or 'autoincrement = True' in args_text
    
    # Extract default
    default_value = None
    default_match = re.search(r'default\s*=\s*([^,\)]+)', args_text)
    if default_match:
        default_value = default_match.group(1).strip()
    
    # Extract onupdate
    onupdate = None
    onupdate_match = re.search(r'onupdate\s*=\s*([^,\)]+)', args_text)
    if onupdate_match:
        onupdate = onupdate_match.group(1).strip()
    
    # Extract comment
    comment = None
    comment_match = re.search(r'comment\s*=\s*["\']([^"\']*)["\']', args_text)
    if comment_match:
        comment = comment_match.group(1)
    
    # Extract name (for column rename)
    db_name = col_name
    name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', args_text)
    if name_match:
        db_name = name_match.group(1)
    
    return {
        'name': col_name,
        'db_name': db_name,
        'type': col_type,
        'type_args': type_args,
        'primary_key': is_primary,
        'nullable': is_nullable,
        'autoincrement': is_autoincrement,
        'default': default_value,
        'onupdate': onupdate,
        'comment': comment,
    }


def map_type_to_mysql(col_info):
    """Map SQLAlchemy type to MySQL type."""
    col_type = col_info['type']
    type_args = col_info['type_args']
    
    type_map = {
        'String': 'VARCHAR',
        'Integer': 'INT',
        'BigInteger': 'BIGINT',
        'SmallInteger': 'SMALLINT',
        'Text': 'TEXT',
        'Boolean': 'TINYINT',
        'DateTime': 'DATETIME',
        'JSON': 'JSON',
        'Float': 'FLOAT',
    }
    
    mysql_type = type_map.get(col_type, col_type.upper())
    
    if col_type == 'Integer' and col_info.get('primary_key') and col_info.get('autoincrement'):
        return 'BIGINT'
    
    if col_type == 'String':
        if type_args:
            return f'VARCHAR({type_args})'
        return 'VARCHAR(255)'
    
    if col_type == 'Text':
        if type_args:
            try:
                # Handle length expressions
                length = type_args.replace('length=', '').strip()
                if '2**31' in length or '2147483647' in length:
                    return 'LONGTEXT'
                length_val = int(length)
                if length_val <= 255:
                    return 'TINYTEXT'
                elif length_val <= 65535:
                    return 'TEXT'
                elif length_val <= 16777215:
                    return 'MEDIUMTEXT'
                else:
                    return 'LONGTEXT'
            except ValueError:
                if '2**31' in type_args or '2147483647' in type_args:
                    return 'LONGTEXT'
        return 'TEXT'
    
    if col_type == 'Boolean':
        return 'TINYINT(1)'
    
    return mysql_type


def parse_table_args(text, start_pos):
    """Parse __table_args__ for unique constraints and indexes."""
    unique_constraints = []
    indexes = []
    
    # Find __table_args__
    table_args_match = re.search(r'__table_args__\s*=\s*\(', text[start_pos:])
    if not table_args_match:
        return unique_constraints, indexes
    
    args_start = start_pos + table_args_match.end() - 1
    
    # Find matching closing parenthesis
    depth = 1
    i = args_start + 1
    while i < len(text) and depth > 0:
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
        i += 1
    
    args_text = text[args_start:i]
    
    # Parse UniqueConstraint
    for uc_match in re.finditer(r'UniqueConstraint\s*\(([^)]+(?:\([^)]*\)[^)]*)*)\)', args_text, re.DOTALL):
        uc_content = uc_match.group(1)
        uc_cols = re.findall(r'["\']([^"\']+)["\']', uc_content)
        uc_name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', uc_content)
        uc_name = uc_name_match.group(1) if uc_name_match else f'uk_{uc_cols[0] if uc_cols else "unknown"}'
        if uc_cols:
            unique_constraints.append({'name': uc_name, 'columns': uc_cols})
    
    # Parse Index
    for idx_match in re.finditer(r'Index\s*\(([^)]+(?:\([^)]*\)[^)]*)*)\)', args_text, re.DOTALL):
        idx_content = idx_match.group(1)
        idx_cols = re.findall(r'["\']([^"\']+)["\']', idx_content)
        if len(idx_cols) > 0:
            idx_name = idx_cols[0]
            idx_columns = idx_cols[1:] if len(idx_cols) > 1 else [idx_cols[0]]
            indexes.append({'name': idx_name, 'columns': idx_columns})
    
    return unique_constraints, indexes


def parse_standalone_indexes(text, start_pos):
    """Parse standalone Index() calls outside __table_args__."""
    indexes = []
    
    # Find standalone Index calls
    for idx_match in re.finditer(r'Index\s*\(\s*["\']([^"\']+)["\']', text[start_pos:]):
        idx_content = text[start_pos + idx_match.start():]
        # Find the full Index(...) call
        depth = 0
        end_pos = 0
        for j, c in enumerate(idx_content):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    end_pos = j
                    break
        
        if end_pos > 0:
            full_idx = idx_content[:end_pos + 1]
            idx_cols = re.findall(r'["\']([^"\']+)["\']', full_idx)
            if len(idx_cols) > 1:
                idx_name = idx_cols[0]
                idx_columns = idx_cols[1:]
                indexes.append({'name': idx_name, 'columns': idx_columns})
    
    return indexes


def parse_model_file(file_path):
    """Parse a model file and extract table definitions."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    tables = []
    
    # Find all class definitions that inherit from Model
    # Pattern matches: class ClassName(Model):
    class_pattern = r'class\s+(\w+)\s*\([^)]*Model[^)]*\)\s*:'
    
    for class_match in re.finditer(class_pattern, content):
        class_name = class_match.group(1)
        class_start = class_match.end()
        
        # Find __tablename__
        tablename_match = re.search(r'__tablename__\s*=\s*["\']([^"\']+)["\']', content[class_start:class_start+500])
        if not tablename_match:
            continue
        
        table_name = tablename_match.group(1)
        
        # Find the end of the class (next class or end of file)
        next_class = re.search(r'\nclass\s+\w+', content[class_start:])
        next_func = re.search(r'\n(?:class|def)\s+\w+', content[class_start:])
        
        if next_class:
            class_end = class_start + next_class.start()
        elif next_func:
            class_end = class_start + next_func.start()
        else:
            class_end = len(content)
        
        class_body = content[class_start:class_end]
        
        # Parse columns
        columns = parse_columns_from_class_body(class_body)
        
        # Parse table args
        unique_constraints, indexes = parse_table_args(content, class_start)
        
        # Parse standalone indexes
        standalone_indexes = parse_standalone_indexes(content, class_start)
        indexes.extend(standalone_indexes)
        
        # Find primary keys
        primary_keys = [col['db_name'] for col in columns if col['primary_key']]
        
        tables.append({
            'class_name': class_name,
            'table_name': table_name,
            'columns': columns,
            'primary_keys': primary_keys,
            'unique_constraints': unique_constraints,
            'indexes': indexes,
        })
    
    return tables


def parse_columns_from_class_body(class_body):
    """Parse columns from class body text."""
    columns = []
    
    # Pattern to match column definitions
    # Match multi-line column definitions
    lines = class_body.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines, comments, docstrings
        if not line or line.startswith('#') or line.startswith('"""') or line.startswith("'''"):
            i += 1
            continue
        
        # Skip method definitions and other class attributes
        if line.startswith('def ') or line.startswith('@') or line.startswith('return'):
            i += 1
            continue
        
        # Check for column definition
        col_match = re.match(r'^(\w+)\s*=\s*Column\s*\(', line)
        if col_match:
            col_name = col_match.group(1)
            
            # Collect the full column definition (may span multiple lines)
            full_def = line
            paren_count = line.count('(') - line.count(')')
            j = i + 1
            while j < len(lines) and paren_count > 0:
                next_line = lines[j].strip()
                full_def += ' ' + next_line
                paren_count += next_line.count('(') - next_line.count(')')
                j += 1
            
            # Parse the column definition
            col_info = parse_single_column(col_name, full_def)
            if col_info:
                columns.append(col_info)
            
            i = j
        else:
            i += 1
    
    return columns


def parse_single_column(col_name, full_def):
    """Parse a single column definition from full def."""
    match = re.search(r'Column\s*\((.*)\)\s*$', full_def, re.DOTALL)
    if not match:
        return None
    
    args_text = match.group(1)
    
    col_type = None
    type_args = ''
    
    type_patterns = [
        (r'^\s*(\w+)\s*\(\s*length\s*=\s*([^)]+)\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*\(\s*(\d+)\s*\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*\(\s*([^)]+)\s*\)', lambda m: (m.group(1), m.group(2))),
        (r'^\s*(\w+)\s*,', lambda m: (m.group(1), '')),
        (r'^\s*(\w+)\s*$', lambda m: (m.group(1), '')),
    ]
    
    for pattern, extractor in type_patterns:
        type_match = re.match(pattern, args_text)
        if type_match:
            col_type, type_args = extractor(type_match)
            break
    
    if not col_type:
        return None
    
    # Check for primary_key
    is_primary = 'primary_key=True' in args_text or 'primary_key = True' in args_text
    
    # Check for nullable
    is_nullable = True
    if 'nullable=False' in args_text or 'nullable = False' in args_text:
        is_nullable = False
    
    # Check for autoincrement
    is_autoincrement = 'autoincrement=True' in args_text or 'autoincrement = True' in args_text
    
    # Extract default
    default_value = None
    default_match = re.search(r'default\s*=\s*([^,\)]+)', args_text)
    if default_match:
        default_value = default_match.group(1).strip()
    
    # Extract comment
    comment = None
    comment_match = re.search(r'comment\s*=\s*["\']([^"\']*)["\']', args_text)
    if comment_match:
        comment = comment_match.group(1)
    
    # Extract name (for column rename)
    db_name = col_name
    name_match = re.search(r'name\s*=\s*["\']([^"\']*)["\']', args_text)
    if name_match:
        db_name = name_match.group(1)
    
    return {
        'name': col_name,
        'db_name': db_name,
        'type': col_type,
        'type_args': type_args,
        'primary_key': is_primary,
        'nullable': is_nullable,
        'autoincrement': is_autoincrement,
        'default': default_value,
        'comment': comment,
    }


def generate_table_ddl(table_info):
    """Generate CREATE TABLE DDL from table info."""
    lines = []
    table_name = table_info['table_name']
    
    lines.append(f'-- Table: {table_name}')
    lines.append(f'-- Source Model: {table_info["class_name"]}')
    lines.append(f'CREATE TABLE IF NOT EXISTS `{table_name}` (')
    
    column_defs = []
    column_names = set()
    
    for col in table_info['columns']:
        col_parts = []
        
        col_parts.append(f'  `{col["db_name"]}`')
        
        mysql_type = map_type_to_mysql(col)
        col_parts.append(mysql_type)
        
        if col['primary_key']:
            col_parts.append('NOT NULL')
        elif not col['nullable']:
            col_parts.append('NOT NULL')
        else:
            col_parts.append('NULL')
        
        if col['primary_key'] and (col['autoincrement'] or col['type'] == 'Integer'):
            col_parts.append('AUTO_INCREMENT')
        
        if col['default']:
            default_val = col['default']
            if default_val in ('datetime.now', 'datetime.utcnow', 'datetime.now()', 'datetime.utcnow()'):
                col_parts.append('DEFAULT CURRENT_TIMESTAMP')
            elif default_val.isdigit() or (default_val.startswith('-') and default_val[1:].isdigit()):
                col_parts.append(f'DEFAULT {default_val}')
            elif 'True' in default_val or 'False' in default_val:
                col_parts.append(f'DEFAULT {1 if "True" in default_val else 0}')
        
        if col['comment']:
            comment = col['comment'].replace("'", "''")
            col_parts.append(f"COMMENT '{comment}'")
        
        column_defs.append(' '.join(col_parts))
        column_names.add(col['db_name'])
    
    has_gmt_create = any(col['db_name'] in ('gmt_create', 'created_at') for col in table_info['columns'])
    has_gmt_modify = any(col['db_name'] in ('gmt_modify', 'updated_at') for col in table_info['columns'])
    
    if not has_gmt_create:
        column_defs.append("  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'")
        column_names.add('gmt_create')
    if not has_gmt_modify:
        column_defs.append("  `gmt_modify` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间'")
        column_names.add('gmt_modify')
    
    if table_info['primary_keys']:
        pk_cols = ', '.join([f'`{pk}`' for pk in table_info['primary_keys']])
        column_defs.append(f'  PRIMARY KEY ({pk_cols})')
    
    for uc in table_info['unique_constraints']:
        valid_cols = [c for c in uc['columns'] if c in column_names]
        if valid_cols:
            uc_cols = ', '.join([f'`{c}`' for c in valid_cols])
            column_defs.append(f'  UNIQUE KEY `{uc["name"]}` ({uc_cols})')
    
    seen_indexes = set()
    for idx in table_info['indexes']:
        valid_cols = [c for c in idx['columns'] if c in column_names]
        if not valid_cols:
            continue
        idx_key = (idx['name'], tuple(valid_cols))
        if idx_key in seen_indexes:
            continue
        seen_indexes.add(idx_key)
        idx_cols = ', '.join([f'`{c}`' for c in valid_cols])
        column_defs.append(f'  KEY `{idx["name"]}` ({idx_cols})')
    
    lines.append(',\n'.join(column_defs))
    lines.append(') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;')
    lines.append('')
    
    return '\n'.join(lines)


def find_model_files(root_dir):
    """Find all Python files that might contain ORM models."""
    model_files = []
    
    # Search in specific directories
    search_dirs = [
        'packages/derisk-core/src/derisk/storage',
        'packages/derisk-core/src/derisk/model',
        'packages/derisk-serve/src/derisk_serve',
    ]
    
    for search_dir in search_dirs:
        full_dir = Path(root_dir) / search_dir
        if full_dir.exists():
            for py_file in full_dir.rglob('*.py'):
                if py_file.is_file():
                    # Skip __pycache__ and test files
                    if '__pycache__' not in str(py_file) and 'test' not in str(py_file).lower():
                        model_files.append(str(py_file))
    
    # Remove duplicates and sort
    model_files = sorted(list(set(model_files)))
    
    return model_files


def parse_ddl_file(ddl_path: Path) -> Dict[str, Dict[str, Any]]:
    """Parse a DDL file and extract table structures."""
    tables = {}
    
    if not ddl_path.exists():
        return tables
    
    content = ddl_path.read_text(encoding='utf-8')
    
    table_pattern = r'CREATE TABLE\s+`(\w+)`\s*\((.*?)\)\s*ENGINE=InnoDB'
    
    for match in re.finditer(table_pattern, content, re.DOTALL | re.IGNORECASE):
        table_name = match.group(1)
        table_body = match.group(2)
        
        columns = {}
        indexes = {}
        unique_keys = {}
        primary_key = None
        
        lines = table_body.split('\n')
        
        for line in lines:
            line = line.strip().rstrip(',')
            if not line or line.startswith('--'):
                continue
            
            col_match = re.match(r'`(\w+)`\s+(\w+(?:\([^)]*\))?)\s*(.*)', line)
            if col_match:
                col_name = col_match.group(1)
                col_type = col_match.group(2)
                col_attrs = col_match.group(3)
                
                columns[col_name] = {
                    'type': col_type,
                    'attrs': col_attrs,
                    'full_def': line
                }
                
                if 'PRIMARY KEY' in col_attrs.upper():
                    primary_key = col_name
            
            pk_match = re.match(r'PRIMARY KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
            if pk_match:
                primary_key = pk_match.group(1)
            
            idx_match = re.match(r'(?:KEY|INDEX)\s+`(\w+)`\s*\(([^)]+)\)', line, re.IGNORECASE)
            if idx_match:
                idx_name = idx_match.group(1)
                idx_cols = idx_match.group(2)
                indexes[idx_name] = idx_cols
            
            uk_match = re.match(r'UNIQUE(?:\s+KEY)?\s+`(\w+)`\s*\(([^)]+)\)', line, re.IGNORECASE)
            if uk_match:
                uk_name = uk_match.group(1)
                uk_cols = uk_match.group(2)
                unique_keys[uk_name] = uk_cols
        
        tables[table_name] = {
            'columns': columns,
            'indexes': indexes,
            'unique_keys': unique_keys,
            'primary_key': primary_key
        }
    
    return tables


def generate_incremental_ddl(old_tables: Dict, new_tables: Dict, from_version: str, to_version: str) -> List[str]:
    """Generate incremental DDL statements from old to new schema."""
    statements = []
    
    statements.append("-- ============================================================")
    statements.append(f"-- Incremental DDL Script for Derisk")
    statements.append(f"-- Upgrade from version {from_version} to {to_version}")
    statements.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    statements.append("-- ============================================================")
    statements.append("")
    statements.append("SET NAMES utf8mb4;")
    statements.append("SET FOREIGN_KEY_CHECKS = 0;")
    statements.append("")
    
    old_table_names = set(old_tables.keys())
    new_table_names = set(new_tables.keys())
    
    added_tables = new_table_names - old_table_names
    removed_tables = old_table_names - new_table_names
    common_tables = old_table_names & new_table_names
    
    if added_tables:
        statements.append("-- ============================================================")
        statements.append("-- New Tables")
        statements.append("-- ============================================================")
        statements.append("")
        
        for table_name in sorted(added_tables):
            statements.append(f"-- Table: {table_name} (NEW)")
            table_info = new_tables[table_name]
            
            col_defs = []
            for col_name, col_info in table_info['columns'].items():
                col_defs.append(f"  {col_info['full_def']}")
            
            if table_info['primary_key'] and not any('PRIMARY KEY' in c.get('attrs', '').upper() for c in table_info['columns'].values()):
                col_defs.append(f"  PRIMARY KEY ({table_info['primary_key']})")
            
            for uk_name, uk_cols in table_info['unique_keys'].items():
                col_defs.append(f"  UNIQUE KEY `{uk_name}` ({uk_cols})")
            
            for idx_name, idx_cols in table_info['indexes'].items():
                col_defs.append(f"  KEY `{idx_name}` ({idx_cols})")
            
            statements.append(f"CREATE TABLE IF NOT EXISTS `{table_name}` (")
            statements.append(',\n'.join(col_defs))
            statements.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")
            statements.append("")
    
    if common_tables:
        statements.append("-- ============================================================")
        statements.append("-- Modified Tables")
        statements.append("-- ============================================================")
        statements.append("")
        
        for table_name in sorted(common_tables):
            old_table = old_tables[table_name]
            new_table = new_tables[table_name]
            
            old_cols = set(old_table['columns'].keys())
            new_cols = set(new_table['columns'].keys())
            
            added_cols = new_cols - old_cols
            removed_cols = old_cols - new_cols
            modified_cols = set()
            
            for col_name in old_cols & new_cols:
                old_col = old_table['columns'][col_name]
                new_col = new_table['columns'][col_name]
                if old_col['full_def'] != new_col['full_def']:
                    modified_cols.add(col_name)
            
            old_idxs = set(old_table['indexes'].keys())
            new_idxs = set(new_table['indexes'].keys())
            added_idxs = new_idxs - old_idxs
            removed_idxs = old_idxs - new_idxs
            
            old_uks = set(old_table['unique_keys'].keys())
            new_uks = set(new_table['unique_keys'].keys())
            added_uks = new_uks - old_uks
            removed_uks = old_uks - new_uks
            
            if added_cols or modified_cols or added_idxs or added_uks:
                statements.append(f"-- Table: {table_name}")
                
                if added_cols:
                    for col_name in sorted(added_cols):
                        col_info = new_table['columns'][col_name]
                        statements.append(f"ALTER TABLE `{table_name}` ADD COLUMN {col_info['full_def']};")
                
                if modified_cols:
                    for col_name in sorted(modified_cols):
                        col_info = new_table['columns'][col_name]
                        statements.append(f"ALTER TABLE `{table_name}` MODIFY COLUMN {col_info['full_def']};")
                
                if removed_cols:
                    for col_name in sorted(removed_cols):
                        statements.append(f"-- ALTER TABLE `{table_name}` DROP COLUMN `{col_name}`;")
                
                if removed_uks:
                    for uk_name in sorted(removed_uks):
                        statements.append(f"ALTER TABLE `{table_name}` DROP INDEX `{uk_name}`;")
                
                if added_uks:
                    for uk_name in sorted(added_uks):
                        uk_cols = new_table['unique_keys'][uk_name]
                        statements.append(f"ALTER TABLE `{table_name}` ADD UNIQUE KEY `{uk_name}` ({uk_cols});")
                
                if removed_idxs:
                    for idx_name in sorted(removed_idxs):
                        statements.append(f"ALTER TABLE `{table_name}` DROP INDEX `{idx_name}`;")
                
                if added_idxs:
                    for idx_name in sorted(added_idxs):
                        idx_cols = new_table['indexes'][idx_name]
                        statements.append(f"ALTER TABLE `{table_name}` ADD INDEX `{idx_name}` ({idx_cols});")
                
                statements.append("")
    
    if removed_tables:
        statements.append("-- ============================================================")
        statements.append("-- Removed Tables (commented out for safety)")
        statements.append("-- ============================================================")
        statements.append("")
        
        for table_name in sorted(removed_tables):
            statements.append(f"-- DROP TABLE IF EXISTS `{table_name}`;")
        statements.append("")
    
    statements.append("")
    statements.append("SET FOREIGN_KEY_CHECKS = 1;")
    statements.append("")
    statements.append("-- ============================================================")
    statements.append("-- End of Incremental DDL Script")
    statements.append("-- ============================================================")
    
    return statements


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 80)
    print("MySQL DDL Generation Script for Derisk Project")
    print("=" * 80)
    print()
    
    current_version = get_project_version(project_root)
    print(f"Current version: {current_version}")
    print()
    
    print("Scanning for ORM model files...")
    model_files = find_model_files(project_root)
    print(f"Found {len(model_files)} model files to parse")
    print()
    
    all_tables = []
    processed_tables = set()
    
    for file_path in model_files:
        rel_path = Path(file_path).relative_to(project_root)
        try:
            tables = parse_model_file(file_path)
            for table in tables:
                if table['table_name'] not in processed_tables:
                    all_tables.append(table)
                    processed_tables.add(table['table_name'])
                    print(f"  Found: {table['table_name']} ({table['class_name']}) - {len(table['columns'])} columns")
        except Exception as e:
            print(f"  Error parsing {rel_path}: {e}")
    
    print()
    
    schema_dir = project_root / "assets" / "schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    
    full_ddl_file = schema_dir / "derisk.sql"
    
    old_tables = {}
    old_version = None
    
    if full_ddl_file.exists():
        print("Parsing existing DDL file for incremental comparison...")
        old_tables = parse_ddl_file(full_ddl_file)
        
        old_content = full_ddl_file.read_text(encoding='utf-8')
        version_match = re.search(r'-- Version:\s*(\S+)', old_content)
        if version_match:
            old_version = version_match.group(1)
        
        print(f"Found {len(old_tables)} existing tables in old DDL (version: {old_version})")
        print()
    
    ddl_statements = []
    ddl_statements.append("-- You can change `derisk` to your actual metadata database name in your `.env` file")
    ddl_statements.append("-- eg. `LOCAL_DB_NAME=derisk`")
    ddl_statements.append("")
    ddl_statements.append("CREATE")
    ddl_statements.append("DATABASE IF NOT EXISTS derisk;")
    ddl_statements.append("use derisk;")
    ddl_statements.append("")
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("-- MySQL DDL Script for Derisk")
    ddl_statements.append(f"-- Version: {current_version}")
    ddl_statements.append("-- Generated from SQLAlchemy ORM Models")
    ddl_statements.append(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("")
    ddl_statements.append("SET NAMES utf8mb4;")
    ddl_statements.append("SET FOREIGN_KEY_CHECKS = 0;")
    ddl_statements.append("")
    
    for table in all_tables:
        ddl = generate_table_ddl(table)
        ddl_statements.append(ddl)
    
    ddl_statements.append("SET FOREIGN_KEY_CHECKS = 1;")
    ddl_statements.append("")
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("-- End of DDL Script")
    ddl_statements.append("-- ============================================================")
    
    with open(full_ddl_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ddl_statements))
    print(f"Full DDL written to: {full_ddl_file}")
    
    if old_tables and old_version and old_version != current_version:
        new_tables = parse_ddl_file(full_ddl_file)
        
        if old_tables != new_tables:
            incremental_statements = generate_incremental_ddl(old_tables, new_tables, old_version, current_version)
            
            upgrade_file = schema_dir / f"upgrade_{old_version}_to_{current_version}.sql"
            with open(upgrade_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(incremental_statements))
            print(f"Incremental DDL written to: {upgrade_file}")
        else:
            print("No schema changes detected, skipping incremental DDL generation")
    elif old_version == current_version:
        print("Same version, skipping incremental DDL generation")
    
    print()
    print(f"Total tables: {len(all_tables)}")
    print("Done!")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())