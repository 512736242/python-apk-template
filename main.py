"""
Python APK Template - 主入口文件
用户无需修改此文件，只需修改 app/your_code.py
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.utils import platform

import sys
from io import StringIO

# 导入用户代码
from app.your_code import run


class OutputLabel(Label):
    pass


class MainApp(App):
    def build(self):
        self.title = "Python Runner"

        # 主布局
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # 输入区域
        input_layout = BoxLayout(size_hint_y=0.15, spacing=10)
        self.input_field = TextInput(
            hint_text='输入参数 (可选)',
            multiline=False,
            size_hint_x=0.7
        )
        run_btn = Button(
            text='运行',
            size_hint_x=0.3,
            on_press=self.execute_code
        )
        input_layout.add_widget(self.input_field)
        input_layout.add_widget(run_btn)

        # 输出区域 (可滚动)
        scroll = ScrollView(size_hint_y=0.8)
        self.output_label = Label(
            text='点击"运行"执行脚本\n输出将显示在这里',
            size_hint_y=None,
            text_size=(Window.width - 40, None),
            halign='left',
            valign='top'
        )
        self.output_label.bind(texture_size=self.output_label.setter('size'))
        scroll.add_widget(self.output_label)

        # 清除按钮
        clear_btn = Button(
            text='清除输出',
            size_hint_y=0.05,
            on_press=self.clear_output
        )

        layout.add_widget(input_layout)
        layout.add_widget(scroll)
        layout.add_widget(clear_btn)

        return layout

    def execute_code(self, instance):
        """执行用户代码并捕获输出"""
        # 捕获 stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            user_input = self.input_field.text.strip()
            args = user_input.split() if user_input else []

            # 调用用户的 run 函数
            result = run(args)

            output = captured_output.getvalue()
            if result is not None:
                output += f"\n返回值: {result}"

            self.output_label.text = output if output else "(无输出)"

        except Exception as e:
            self.output_label.text = f"错误: {type(e).__name__}\n{str(e)}"

        finally:
            sys.stdout = old_stdout

    def clear_output(self, instance):
        self.output_label.text = ''
        self.input_field.text = ''


if __name__ == '__main__':
    MainApp().run()
