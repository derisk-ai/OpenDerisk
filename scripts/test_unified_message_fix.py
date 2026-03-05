#!/usr/bin/env python3
"""
测试历史消息读取修复

验证Core V2的历史消息能否正确读取
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from derisk.storage.unified_message_dao import UnifiedMessageDAO
from derisk.core.interface.unified_message import UnifiedMessage


async def test_gpts_messages(conv_uid: str):
    """测试从gpts_messages读取消息
    
    Args:
        conv_uid: 对话ID
    """
    print(f"\n{'='*60}")
    print(f"测试对话: {conv_uid}")
    print('='*60)
    
    dao = UnifiedMessageDAO()
    
    try:
        # 1. 检查对话是否存在
        print("\n1. 检查对话是否存在...")
        messages = await dao.get_messages_by_conv_id(conv_uid, limit=1)
        
        if messages:
            print(f"✅ 找到对话，共 {len(messages)} 条消息")
        else:
            print("❌ 未找到对话或消息为空")
            return
        
        # 2. 加载所有消息
        print("\n2. 加载所有消息...")
        all_messages = await dao.get_messages_by_conv_id(conv_uid)
        print(f"✅ 加载了 {len(all_messages)} 条消息")
        
        # 3. 显示消息详情
        print("\n3. 消息详情:")
        for idx, msg in enumerate(all_messages[:5]):  # 只显示前5条
            print(f"\n消息 #{idx + 1}:")
            print(f"  ID: {msg.message_id}")
            print(f"  类型: {msg.message_type}")
            print(f"  发送者: {msg.sender}")
            print(f"  内容: {msg.content[:100]}..." if len(msg.content) > 100 else f"  内容: {msg.content}")
            print(f"  轮次: {msg.rounds}")
        
        if len(all_messages) > 5:
            print(f"\n... 还有 {len(all_messages) - 5} 条消息未显示")
        
        print("\n✅ 测试成功：消息可以正常读取")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_conversation_list(conv_session_id: str):
    """测试会话列表读取
    
    Args:
        conv_session_id: 会话ID
    """
    print(f"\n{'='*60}")
    print(f"测试会话: {conv_session_id}")
    print('='*60)
    
    dao = UnifiedMessageDAO()
    
    try:
        messages = await dao.get_messages_by_session(conv_session_id)
        
        if messages:
            print(f"✅ 找到会话，共 {len(messages)} 条消息")
        else:
            print("❌ 未找到会话")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("历史消息读取测试（Core V2）")
    print("="*60)
    
    # 使用你提供的conv_uid
    conv_uid = "04ae4084-1639-11f1-ab79-a62ccd5aa23f"
    
    # 运行测试
    asyncio.run(test_gpts_messages(conv_uid))
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()