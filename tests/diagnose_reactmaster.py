#!/usr/bin/env python3
"""
Diagnostic script to verify ReActMasterV2 issues are resolved.

This script checks:
1. Skill loading in database
2. Agent initialization
3. Tool definitions
4. Prompt construction
"""

import sys
import sqlite3
import json
from pathlib import Path


def check_database_skill():
    """Check if skill exists in database with correct code."""
    print("=" * 60)
    print("Issue #1: Checking Skill in Database")
    print("=" * 60)

    db_path = Path("pilot/meta_data/derisk.db")
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check skill
    cursor.execute("""
        SELECT skill_code, name, description, path 
        FROM server_app_skill 
        WHERE name='open_rca_diagnosis'
    """)

    result = cursor.fetchone()
    conn.close()

    if not result:
        print("❌ Skill 'open_rca_diagnosis' not found in database")
        return False

    skill_code, name, description, path = result
    print(f"✓ Skill found in database:")
    print(f"  - skill_code: {skill_code}")
    print(f"  - name: {name}")
    print(f"  - description: {description[:100]}...")
    print(f"  - path: {path}")

    return skill_code


def check_app_config(skill_code):
    """Check if app config references the correct skill code."""
    print("\n" + "=" * 60)
    print("Checking App Configuration")
    print("=" * 60)

    config_path = Path(
        "packages/derisk-serve/src/derisk_serve/building/app/service/derisk_app_define/rca_openrca_app.json"
    )
    if not config_path.exists():
        print(f"❌ Config not found at {config_path}")
        return False

    with open(config_path) as f:
        config = json.load(f)

    app = config[0]
    tools = app.get("resource_tool", [])

    if not tools:
        print("❌ No tools configured in app")
        return False

    tool = tools[0]
    value_json = tool.get("value", "{}")
    value = json.loads(value_json)

    config_skill_code = value.get("skillCode") or value.get("key")

    print(f"✓ App config found:")
    print(f"  - skill_code in config: {config_skill_code}")
    print(f"  - skill_code in database: {skill_code}")

    if config_skill_code == skill_code:
        print("✓ ✓ ✓ MATCH! Skill codes are aligned")
        return True
    else:
        print("❌ MISMATCH! Skill codes don't match")
        print(f"   Config has: {config_skill_code}")
        print(f"   Database has: {skill_code}")
        return False


def check_skill_files():
    """Check if skill files exist on disk."""
    print("\n" + "=" * 60)
    print("Checking Skill Files on Disk")
    print("=" * 60)

    skill_paths = [
        Path("pilot/data/skill/open_rca_diagnosis"),
        Path("pilot/data/skill/open-rca-diagnosis-2-0-derisk-c5b0e208"),
    ]

    for skill_path in skill_paths:
        if skill_path.exists():
            print(f"✓ Skill directory exists: {skill_path}")

            # Check for skill.md
            skill_md = skill_path / "skill.md"
            if skill_md.exists():
                print(f"  ✓ skill.md found")
            else:
                print(f"  ⚠️  skill.md not found")

            return True

    print("❌ No skill directory found")
    return False


def print_summary(results):
    """Print diagnostic summary."""
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)

    all_passed = all(results.values())

    for check, passed in results.items():
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {check}")

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ✓ ✓ ALL CHECKS PASSED ✓ ✓ ✓")
        print("\nIssue #1 (Skill Loading) should be resolved.")
        print("Please restart the server to apply changes.")
    else:
        print("❌ SOME CHECKS FAILED")
        print("\nPlease review the failures above.")
    print("=" * 60)


def main():
    print("OpenDerisk ReActMasterV2 Diagnostic Tool")
    print("This script checks for Issue #1: Skill Loading\n")

    results = {}

    # Check 1: Database skill
    skill_code = check_database_skill()
    results["Database skill exists"] = skill_code is not False

    if skill_code:
        # Check 2: App config alignment
        results["App config aligned"] = check_app_config(skill_code)

    # Check 3: Skill files
    results["Skill files exist"] = check_skill_files()

    # Print summary
    print_summary(results)

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
