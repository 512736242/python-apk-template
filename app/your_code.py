"""
在这里编写你的 Python 代码
修改 run() 函数的内容即可

所有 print() 输出都会显示在 APP 界面上
"""


def run(args: list = None):
    """
    主函数 - 在这里写你的代码

    参数:
        args: 用户在输入框中输入的参数列表
              例如用户输入 "hello world" -> args = ["hello", "world"]

    返回:
        任意值，会显示在输出区域
    """

    # ===== 示例代码，请替换为你自己的代码 =====

    print("Hello from Python APK!")
    print(f"收到参数: {args}")

    # 简单计算示例
    if args and len(args) >= 2:
        try:
            a, b = float(args[0]), float(args[1])
            print(f"{a} + {b} = {a + b}")
            print(f"{a} * {b} = {a * b}")
        except ValueError:
            print("参数不是有效数字")

    # 返回值会显示在输出区域
    return "执行完成"


# ===== 你可以在下面添加更多辅助函数 =====

def helper_function():
    """示例辅助函数"""
    pass
