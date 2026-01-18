"""
示例计算器 - 带日志输出
"""
from datetime import datetime


def log(message: str):
    """输出带时间戳的日志"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def run(args: list = None):
    """
    计算器主函数

    用法:
        数字1 运算符 数字2
        例如: 10 + 5
        支持: + - * / ^ %
    """
    log("计算器启动")
    log(f"收到输入: {args}")

    if not args:
        log("错误: 未输入任何内容")
        print("\n使用方法:")
        print("  输入: 数字1 运算符 数字2")
        print("  例如: 10 + 5")
        print("\n支持的运算符:")
        print("  +  加法")
        print("  -  减法")
        print("  *  乘法")
        print("  /  除法")
        print("  ^  幂运算")
        print("  %  取余")
        return

    if len(args) < 3:
        log("错误: 参数不足，需要 3 个参数")
        print("正确格式: 数字1 运算符 数字2")
        return

    try:
        a = float(args[0])
        op = args[1]
        b = float(args[2])
        log(f"解析参数: a={a}, op='{op}', b={b}")
    except ValueError as e:
        log(f"错误: 参数解析失败 - {e}")
        print("请输入有效的数字")
        return

    log(f"开始计算: {a} {op} {b}")

    result = None
    if op == '+':
        result = a + b
        log("执行加法运算")
    elif op == '-':
        result = a - b
        log("执行减法运算")
    elif op == '*':
        result = a * b
        log("执行乘法运算")
    elif op == '/':
        if b == 0:
            log("错误: 除数不能为零!")
            print("错误: 除数不能为零!")
            return
        result = a / b
        log("执行除法运算")
    elif op == '^':
        result = a ** b
        log("执行幂运算")
    elif op == '%':
        if b == 0:
            log("错误: 取余时除数不能为零!")
            print("错误: 取余时除数不能为零!")
            return
        result = a % b
        log("执行取余运算")
    else:
        log(f"错误: 不支持的运算符 '{op}'")
        print(f"不支持的运算符: {op}")
        print("支持的运算符: + - * / ^ %")
        return

    log(f"计算完成: 结果 = {result}")
    print(f"\n{'='*30}")
    print(f"  {a} {op} {b} = {result}")
    print(f"{'='*30}")

    return result
