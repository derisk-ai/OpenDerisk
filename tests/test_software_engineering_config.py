"""
软件工程配置测试
验证软件工程最佳实践配置的加载和应用
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from derisk.agent.core_v2.software_engineering_loader import (
    SoftwareEngineeringConfigLoader,
    CodeQualityChecker,
    get_software_engineering_config,
    check_code_quality,
)
from derisk.agent.core_v2.software_engineering_integrator import (
    SoftwareEngineeringIntegrator,
    CodingStrategyEnhancer,
    create_coding_strategy_enhancer,
)


def test_config_loading():
    """测试配置加载"""
    print("=" * 60)
    print("测试软件工程配置加载")
    print("=" * 60)

    config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "configs", "engineering")
    
    loader = SoftwareEngineeringConfigLoader(config_dir)
    config = loader.load_all_configs()

    print(f"\n设计原则数量: {len(config.design_principles)}")
    for name, principle in config.design_principles.items():
        print(f"  - {principle.name}: {'启用' if principle.enabled else '禁用'}")

    print(f"\n质量门禁数量: {len(config.quality_gates)}")
    for gate in config.quality_gates:
        print(f"  - {gate.name}: 阈值={gate.threshold}, 动作={gate.action}")

    print(f"\n安全约束数量: {len(config.security_constraints)}")
    for constraint in config.security_constraints:
        print(f"  - [{constraint.severity.value}] {constraint.name}")

    print(f"\n反模式数量: {len(config.anti_patterns)}")
    for ap in config.anti_patterns:
        print(f"  - {ap.name}")

    return config


def test_code_quality_checker():
    """测试代码质量检查"""
    print("\n" + "=" * 60)
    print("测试代码质量检查")
    print("=" * 60)

    config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "configs", "engineering")
    config = get_software_engineering_config(config_dir)
    checker = CodeQualityChecker(config)

    test_code = '''
def process_data(a, b, c, d, e, f, g, h):
    """这是一个参数过多的函数"""
    password = "hardcoded_secret_123"
    api_key = "sk-xxxxx"
    
    result = []
    for i in range(100):
        for j in range(100):
            for k in range(100):
                for l in range(100):
                    if i > 50:
                        if j > 50:
                            if k > 50:
                                if l > 50:
                                    result.append(i + j + k + l)
    return result

class GodClass:
    def method1(self): pass
    def method2(self): pass
    def method3(self): pass
    def method4(self): pass
    def method5(self): pass
    def method6(self): pass
    def method7(self): pass
    def method8(self): pass
    def method9(self): pass
    def method10(self): pass
    def method11(self): pass
    def method12(self): pass
    def method13(self): pass
    def method14(self): pass
    def method15(self): pass
    def method16(self): pass
    def method17(self): pass
    def method18(self): pass
    def method19(self): pass
    def method20(self): pass
    def method21(self): pass
'''

    result = checker.check_code(test_code, "python")

    print(f"\n检查结果: {'通过' if result['passed'] else '未通过'}")
    print(f"代码行数: {result['metrics']['code_lines']}")

    if result['violations']:
        print(f"\n违规项 ({len(result['violations'])}):")
        for v in result['violations']:
            print(f"  - [{v['severity']}] {v['name']}: {v['description']}")

    if result['warnings']:
        print(f"\n警告 ({len(result['warnings'])}):")
        for w in result['warnings']:
            print(f"  - [{w['severity']}] {w['name']}: {w['description']}")

    if result['suggestions']:
        print(f"\n建议 ({len(result['suggestions'])}):")
        for s in result['suggestions']:
            print(f"  - {s['name']}: {s['description']}")

    return result


def test_system_prompt_enhancement():
    """测试系统提示增强"""
    print("\n" + "=" * 60)
    print("测试系统提示增强")
    print("=" * 60)

    config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "configs", "engineering")
    enhancer = create_coding_strategy_enhancer(config_dir)

    base_prompt = "你是一个AI助手。"
    enhanced = enhancer.enhance_system_prompt(base_prompt)

    print("\n增强后的系统提示 (前1000字符):")
    print("-" * 40)
    print(enhanced[:1000])
    print("-" * 40)
    print(f"总长度: {len(enhanced)} 字符")


def test_integrator():
    """测试集成器"""
    print("\n" + "=" * 60)
    print("测试软件工程集成器")
    print("=" * 60)

    config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "configs", "engineering")
    integrator = SoftwareEngineeringIntegrator(config_dir)

    print("\n设计原则提示:")
    print("-" * 40)
    print(integrator.get_design_principles_prompt()[:500])

    print("\n安全约束提示:")
    print("-" * 40)
    print(integrator.get_security_constraints_prompt()[:500])

    print("\n架构规则提示:")
    print("-" * 40)
    print(integrator.get_architecture_rules_prompt())


def main():
    """运行所有测试"""
    print("开始测试软件工程配置集成")
    print("=" * 60)

    try:
        test_config_loading()
        test_code_quality_checker()
        test_system_prompt_enhancement()
        test_integrator()

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()