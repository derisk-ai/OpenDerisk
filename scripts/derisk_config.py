#!/usr/bin/env python3
"""配置管理CLI"""
import argparse
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "derisk-core" / "src"))

from derisk_core.config import ConfigLoader, ConfigManager, ConfigValidator

def main():
    parser = argparse.ArgumentParser(description="OpenDeRisk 配置管理")
    subparsers = parser.add_subparsers(dest="command", help="命令")
    
    init_parser = subparsers.add_parser("init", help="生成默认配置文件")
    init_parser.add_argument("-o", "--output", default="derisk.json", help="输出路径")
    
    show_parser = subparsers.add_parser("show", help="显示当前配置")
    show_parser.add_argument("-p", "--path", help="配置文件路径")
    
    validate_parser = subparsers.add_parser("validate", help="验证配置")
    validate_parser.add_argument("-p", "--path", help="配置文件路径")
    
    args = parser.parse_args()
    
    if args.command == "init":
        ConfigLoader.generate_default(args.output)
    
    elif args.command == "show":
        config = ConfigManager.init(args.path)
        print(json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False))
    
    elif args.command == "validate":
        config = ConfigManager.init(args.path)
        warnings = ConfigValidator.validate(config)
        for level, msg in warnings:
            print(f"[{level.upper()}] {msg}")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()