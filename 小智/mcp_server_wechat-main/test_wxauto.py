"""测试 wxauto 是否能正常连接微信"""
import sys

print("=" * 50)
print("wxauto 微信连接测试")
print("=" * 50)
print()

# 检查微信窗口
print("[1] 检查微信窗口...")
try:
    from wxauto import WeChat
    wx = WeChat()
    print("    ✓ 成功连接到微信！")
    print(f"    当前登录用户: {wx.nickname if hasattr(wx, 'nickname') else '未知'}")
except Exception as e:
    print(f"    ✗ 连接失败: {e}")
    print()
    print("请确保：")
    print("  1. 微信PC版已登录")
    print("  2. 微信窗口已打开（不能最小化到托盘）")
    print("  3. 微信版本支持（建议 3.9.x）")
    sys.exit(1)

# 测试获取会话列表
print()
print("[2] 获取会话列表...")
try:
    sessions = wx.GetSessionList()
    if sessions:
        print(f"    ✓ 获取到 {len(sessions)} 个会话")
        print("    最近会话:")
        for s in sessions[:5]:
            print(f"      - {s}")
    else:
        print("    会话列表为空")
except Exception as e:
    print(f"    ✗ 获取失败: {e}")

# 测试发送消息（可选）
print()
print("[3] 测试完成！")
print()
print("如果上面都成功，说明 wxauto 工作正常。")
print("如果连接失败，请尝试：")
print("  - 把微信窗口拖到屏幕中央")
print("  - 确保微信窗口没有被其他窗口遮挡")
print("  - 重启微信后再试")
