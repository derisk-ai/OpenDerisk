#!/usr/bin/env python3
"""
Generate MySQL DDL scripts from SQLAlchemy ORM model files.

This script parses the ORM model files and generates MySQL-compatible CREATE TABLE statements.
"""

import os
import re
from pathlib import Path
from collections import OrderedDict


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
    
    # Remove the column name and = Column( part
    match = re.search(r'Column\s*\((.*)\)\s*$', col_text, re.DOTALL)
    if not match:
        return None
    
    args_text = match.group(1)
    
    # Extract type
    type_match = re.match(r'(\w+)\s*\(([^)]*)\)', args_text)
    if type_match:
        col_type = type_match.group(1)
        type_args = type_match.group(2).strip()
    else:
        type_match = re.match(r'(\w+)', args_text)
        if type_match:
            col_type = type_match.group(1)
            type_args = ''
        else:
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
    """Parse a single column definition from full text."""
    # Extract the Column(...) part
    match = re.search(r'Column\s*\((.*)\)\s*$', full_def, re.DOTALL)
    if not match:
        return None
    
    args_text = match.group(1)
    
    # Extract type
    type_match = re.match(r'(\w+)\s*\(([^)]*)\)', args_text)
    if type_match:
        col_type = type_match.group(1)
        type_args = type_match.group(2).strip()
    else:
        type_match = re.match(r'(\w+)', args_text)
        if type_match:
            col_type = type_match.group(1)
            type_args = ''
        else:
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
    lines.append(f'DROP TABLE IF EXISTS `{table_name}`;')
    lines.append(f'CREATE TABLE `{table_name}` (')
    
    column_defs = []
    
    for col in table_info['columns']:
        col_parts = []
        
        # Column name
        col_parts.append(f'  `{col["db_name"]}`')
        
        # Column type
        mysql_type = map_type_to_mysql(col)
        col_parts.append(mysql_type)
        
        # NULL/NOT NULL
        if col['primary_key']:
            col_parts.append('NOT NULL')
        elif not col['nullable']:
            col_parts.append('NOT NULL')
        else:
            col_parts.append('NULL')
        
        # AUTO_INCREMENT for primary keys
        if col['primary_key'] and (col['autoincrement'] or col['type'] == 'Integer'):
            col_parts.append('AUTO_INCREMENT')
        
        # DEFAULT
        if col['default']:
            default_val = col['default']
            if default_val in ('datetime.now', 'datetime.utcnow', 'datetime.now()', 'datetime.utcnow()'):
                col_parts.append('DEFAULT CURRENT_TIMESTAMP')
            elif default_val.isdigit() or (default_val.startswith('-') and default_val[1:].isdigit()):
                col_parts.append(f'DEFAULT {default_val}')
            elif 'True' in default_val or 'False' in default_val:
                col_parts.append(f'DEFAULT {1 if "True" in default_val else 0}')
        
        # COMMENT
        if col['comment']:
            comment = col['comment'].replace("'", "''")
            col_parts.append(f"COMMENT '{comment}'")
        
        column_defs.append(' '.join(col_parts))
    
    # PRIMARY KEY
    if table_info['primary_keys']:
        pk_cols = ', '.join([f'`{pk}`' for pk in table_info['primary_keys']])
        column_defs.append(f'  PRIMARY KEY ({pk_cols})')
    
    # Unique constraints
    for uc in table_info['unique_constraints']:
        uc_cols = ', '.join([f'`{c}`' for c in uc['columns']])
        column_defs.append(f'  UNIQUE KEY `{uc["name"]}` ({uc_cols})')
    
    # Indexes
    for idx in table_info['indexes']:
        idx_cols = ', '.join([f'`{c}`' for c in idx['columns']])
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


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    
    print("=" * 80)
    print("MySQL DDL Generation Script for Derisk Project")
    print("=" * 80)
    print()
    
    # Find all model files
    print("Scanning for ORM model files...")
    model_files = find_model_files(project_root)
    print(f"Found {len(model_files)} model files to parse")
    print()
    
    # Parse all model files
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
    
    # Generate DDL
    ddl_statements = []
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("-- MySQL DDL Script for Derisk")
    ddl_statements.append("-- Generated from SQLAlchemy ORM Models")
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("")
    ddl_statements.append("SET NAMES utf8mb4;")
    ddl_statements.append("SET FOREIGN_KEY_CHECKS = 0;")
    ddl_statements.append("")
    
    for table in all_tables:
        ddl = generate_table_ddl(table)
        ddl_statements.append(ddl)
    
    ddl_statements.append("")
    ddl_statements.append("SET FOREIGN_KEY_CHECKS = 1;")
    ddl_statements.append("")
    ddl_statements.append("-- ============================================================")
    ddl_statements.append("-- End of DDL Script")
    ddl_statements.append("-- ============================================================")
    
    # Write to file
    output_file = project_root / "scripts" / "mysql_ddl.sql"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ddl_statements))
    
    print(f"DDL script written to: {output_file}")
    print()
    print(f"Total tables: {len(all_tables)}")
    print("Done!")


if __name__ == '__main__':
    main()