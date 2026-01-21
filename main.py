"""
BDSM 论坛工具 - Kivy GUI 版本
分类标签页 + 弹出对话框输入 + 用户名密码登录
修复: 延迟初始化避免线程冲突
"""
import os
import sys
import threading

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import get_color_from_hex
from functools import partial

# 注册中文字体
DEFAULT_FONT = None

def init_chinese_font():
    """初始化中文字体，尝试多个来源"""
    global DEFAULT_FONT

    # 1. 尝试项目内的字体文件
    font_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
    # 尝试多个可能的字体文件名
    font_names = [
        'NotoSansSC-Regular.ttf',
        'NotoSansSC-VariableFont_wght.ttf',
        'NotoSansSC.ttf',
    ]
    for fname in font_names:
        font_path = os.path.join(font_dir, fname)
        if os.path.exists(font_path):
            try:
                LabelBase.register(name='NotoSansSC', fn_regular=font_path)
                DEFAULT_FONT = 'NotoSansSC'
                print(f"使用项目字体: {font_path}")
                return
            except Exception as e:
                print(f"加载项目字体失败: {e}")

    # 2. 尝试 Android 系统中文字体
    android_fonts = [
        '/system/fonts/NotoSansCJK-Regular.ttc',
        '/system/fonts/NotoSansSC-Regular.otf',
        '/system/fonts/DroidSansFallback.ttf',
        '/system/fonts/NotoSansHans-Regular.otf',
    ]
    for afont in android_fonts:
        if os.path.exists(afont):
            try:
                LabelBase.register(name='ChineseFont', fn_regular=afont)
                DEFAULT_FONT = 'ChineseFont'
                print(f"使用系统字体: {afont}")
                return
            except Exception as e:
                print(f"加载系统字体 {afont} 失败: {e}")

    # 3. 使用 Roboto 作为最后备选（可能不支持中文）
    print("警告: 未找到中文字体，部分中文可能显示为方块")
    DEFAULT_FONT = None

init_chinese_font()

# 颜色主题
COLORS = {
    'bg': get_color_from_hex('#1a1a2e'),
    'card': get_color_from_hex('#16213e'),
    'primary': get_color_from_hex('#e94560'),
    'secondary': get_color_from_hex('#0f3460'),
    'text': get_color_from_hex('#eaeaea'),
    'text_dim': get_color_from_hex('#888888'),
    'success': get_color_from_hex('#4ecca3'),
    'warning': get_color_from_hex('#ffc107'),
    'error': get_color_from_hex('#ff6b6b'),
}


class StyledSpinnerOption(Button):
    """Spinner 下拉选项的自定义样式"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = COLORS['card']
        self.color = COLORS['text']
        self.font_name = DEFAULT_FONT if DEFAULT_FONT else 'Roboto'
        self.size_hint_y = None
        self.height = dp(44)


class StyledSpinner(Spinner):
    """自定义样式下拉框"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.option_cls = StyledSpinnerOption
        self.background_normal = ''
        self.background_color = COLORS['secondary']
        self.color = COLORS['text']
        self.font_name = DEFAULT_FONT if DEFAULT_FONT else 'Roboto'
        self.dropdown_cls.max_height = dp(200)  # 设置下拉菜单最大高度


class StyledButton(Button):
    """自定义样式按钮"""
    def __init__(self, bg_color=None, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_color = bg_color or COLORS['primary']
        self.color = COLORS['text']
        self.font_name = DEFAULT_FONT if DEFAULT_FONT else 'Roboto'
        self.bold = True


class StyledTextInput(TextInput):
    """自定义样式输入框"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_active = ''
        self.background_color = COLORS['card']
        self.foreground_color = COLORS['text']
        self.cursor_color = COLORS['primary']
        self.hint_text_color = COLORS['text_dim']
        self.font_name = DEFAULT_FONT if DEFAULT_FONT else 'Roboto'
        self.padding = [dp(15), dp(12)]


class StyledLabel(Label):
    """自定义样式标签"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color = COLORS['text']
        self.font_name = DEFAULT_FONT if DEFAULT_FONT else 'Roboto'


class CardLayout(BoxLayout):
    """卡片样式布局"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*COLORS['card'])
            self.rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class InputDialog(Popup):
    """弹出输入对话框"""
    def __init__(self, title, fields, callback, **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.title_color = COLORS['text']
        self.title_size = dp(18)
        self.separator_color = COLORS['primary']
        self.size_hint = (0.85, None)
        self.height = dp(80 + 60 * len(fields) + 70)
        self.background_color = COLORS['card']
        self.callback = callback
        self.inputs = {}

        content = BoxLayout(orientation='vertical', spacing=dp(15), padding=dp(15))

        for field in fields:
            row = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(10))
            lbl = StyledLabel(
                text=field.get("label", ""),
                size_hint_x=0.35,
                halign='right',
                valign='middle'
            )
            lbl.bind(size=lbl.setter('text_size'))
            inp = StyledTextInput(
                text=str(field.get("default", "")),
                hint_text=field.get("hint", ""),
                multiline=False,
                size_hint_x=0.65
            )
            self.inputs[field.get("key", field.get("label"))] = inp
            row.add_widget(lbl)
            row.add_widget(inp)
            content.add_widget(row)

        # 按钮行
        btn_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(15))
        cancel_btn = StyledButton(
            text='取消',
            bg_color=COLORS['secondary'],
            on_press=self.dismiss
        )
        confirm_btn = StyledButton(
            text='确定',
            on_press=self.on_confirm
        )
        btn_row.add_widget(cancel_btn)
        btn_row.add_widget(confirm_btn)
        content.add_widget(btn_row)

        self.content = content

    def on_confirm(self, instance):
        values = {key: inp.text for key, inp in self.inputs.items()}
        self.dismiss()
        if self.callback:
            self.callback(values)


class LoginScreen(BoxLayout):
    """登录界面"""
    def __init__(self, app, error_msg=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'
        self.padding = dp(25)
        self.spacing = dp(15)

        # 背景色
        with self.canvas.before:
            Color(*COLORS['bg'])
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # 顶部空白
        self.add_widget(Widget(size_hint_y=0.1))

        # Logo/标题区
        title_card = CardLayout(orientation='vertical', size_hint_y=None, height=dp(100), padding=dp(20))
        title_card.add_widget(StyledLabel(
            text='BDSM 论坛工具',
            font_size=dp(28),
            bold=True
        ))
        title_card.add_widget(StyledLabel(
            text='爬虫 / 投票 / 账号管理',
            font_size=dp(14),
            color=COLORS['text_dim']
        ))
        self.add_widget(title_card)

        self.add_widget(Widget(size_hint_y=0.05))

        # 登录表单卡片
        form_card = CardLayout(orientation='vertical', size_hint_y=None, height=dp(280), padding=dp(20), spacing=dp(12))

        # 登录方式选择
        self.login_type = StyledSpinner(
            text='手机号 + 密码',
            values=['手机号 + 密码', '短信验证码', '直接输入 Token'],
            size_hint_y=None,
            height=dp(44)
        )
        self.login_type.bind(text=self.on_login_type_change)
        form_card.add_widget(self.login_type)

        # 手机号
        self.phone_input = StyledTextInput(
            hint_text='手机号',
            multiline=False,
            size_hint_y=None,
            height=dp(44)
        )
        form_card.add_widget(self.phone_input)

        # 密码/验证码/Token
        self.password_input = StyledTextInput(
            hint_text='密码',
            multiline=False,
            password=True,
            size_hint_y=None,
            height=dp(44)
        )
        form_card.add_widget(self.password_input)

        # 发送验证码按钮容器
        self.sms_container = BoxLayout(size_hint_y=None, height=dp(44))
        self.sms_btn = StyledButton(
            text='发送验证码',
            bg_color=COLORS['secondary'],
            on_press=self.send_sms
        )
        form_card.add_widget(self.sms_container)

        # 按钮行
        btn_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))

        # 登录按钮
        self.login_btn = StyledButton(
            text='登  录',
            on_press=self.do_login
        )
        btn_row.add_widget(self.login_btn)

        # 跳过登录按钮
        skip_btn = StyledButton(
            text='跳过登录',
            bg_color=COLORS['secondary'],
            on_press=self.skip_login
        )
        btn_row.add_widget(skip_btn)

        form_card.add_widget(btn_row)

        self.add_widget(form_card)

        # 已保存账号区
        self.saved_accounts_layout = BoxLayout(orientation='vertical', size_hint_y=0.35)
        self.add_widget(self.saved_accounts_layout)

        # 状态显示
        self.status_label = StyledLabel(
            text=error_msg if error_msg else '',
            size_hint_y=None,
            height=dp(30),
            color=COLORS['error'] if error_msg else COLORS['text_dim']
        )
        self.add_widget(self.status_label)

        # 延迟加载已保存账号
        Clock.schedule_once(self.load_saved_accounts, 0.5)

    def _update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def load_saved_accounts(self, dt=None):
        self.saved_accounts_layout.clear_widgets()

        # 检查 spider 是否已初始化
        if not self.app.spider:
            self.saved_accounts_layout.add_widget(StyledLabel(
                text='初始化中...',
                size_hint_y=None,
                height=dp(30),
                font_size=dp(14),
                color=COLORS['warning']
            ))
            return

        try:
            from app.your_code import load_accounts
            accounts = load_accounts(self.app.spider)

            if accounts:
                header = StyledLabel(
                    text='已保存账号',
                    size_hint_y=None,
                    height=dp(30),
                    font_size=dp(14),
                    color=COLORS['text_dim']
                )
                self.saved_accounts_layout.add_widget(header)

                scroll = ScrollView(size_hint_y=1)
                acc_list = GridLayout(cols=1, spacing=dp(8), size_hint_y=None, padding=[0, dp(5)])
                acc_list.bind(minimum_height=acc_list.setter('height'))

                for i, acc in enumerate(accounts[:4]):
                    name = acc.get("昵称", "未命名")
                    phone = acc.get("手机号", "")
                    phone_display = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "Token"

                    btn = StyledButton(
                        text=f'{name} ({phone_display})',
                        size_hint_y=None,
                        height=dp(42),
                        bg_color=COLORS['secondary']
                    )
                    btn.bind(on_press=partial(self.quick_login, acc))
                    acc_list.add_widget(btn)

                scroll.add_widget(acc_list)
                self.saved_accounts_layout.add_widget(scroll)
        except Exception as e:
            print(f"加载账号失败: {e}")

    def on_login_type_change(self, spinner, text):
        self.sms_container.clear_widgets()

        # 清空密码/验证码/Token输入框
        self.password_input.text = ''

        if text == '手机号 + 密码':
            self.phone_input.hint_text = '手机号'
            self.phone_input.disabled = False
            self.password_input.hint_text = '密码'
            self.password_input.password = True
        elif text == '短信验证码':
            self.phone_input.hint_text = '手机号'
            self.phone_input.disabled = False
            self.password_input.hint_text = '验证码'
            self.password_input.password = False
            self.sms_container.add_widget(self.sms_btn)
        else:  # 直接输入 Token
            self.phone_input.hint_text = '（不需要）'
            self.phone_input.text = ''
            self.phone_input.disabled = True
            self.password_input.hint_text = 'Token'
            self.password_input.password = False

    def send_sms(self, instance):
        phone = self.phone_input.text.strip()
        if len(phone) != 11:
            self.status_label.text = '手机号格式错误'
            return

        self.status_label.text = '发送中...'
        threading.Thread(target=self._send_sms_thread, args=(phone,), daemon=True).start()

    def _send_sms_thread(self, phone):
        try:
            from app.your_code import send_sms_code
            success = send_sms_code(self.app.spider, phone)
            self.update_status('验证码已发送' if success else '发送失败')
        except Exception as e:
            self.update_status(f'发送失败: {e}')

    def skip_login(self, instance):
        """跳过登录，直接进入主界面"""
        self.status_label.text = '未登录模式，部分功能不可用'
        self.status_label.color = COLORS['warning']
        self.app.token = None  # 确保 token 为 None
        Clock.schedule_once(lambda dt: self.app.show_main_screen(), 0.3)

    def do_login(self, instance):
        # 检查 spider 是否已初始化
        if not self.app.spider:
            self.status_label.text = '系统未初始化，请重启应用'
            self.status_label.color = COLORS['error']
            return

        self.status_label.text = '登录中...'
        self.login_btn.disabled = True
        threading.Thread(target=self._login_thread, daemon=True).start()

    def _login_thread(self):
        try:
            # 再次检查 spider
            if not self.app.spider:
                self.update_status('系统未初始化')
                self.enable_login_btn()
                return

            from app.your_code import login_with_account, test_token_valid

            login_type = self.login_type.text
            phone = self.phone_input.text.strip()
            password = self.password_input.text.strip()

            token = None
            if login_type == '手机号 + 密码':
                token = login_with_account(self.app.spider, phone=phone, password=password, login_type=1)
            elif login_type == '短信验证码':
                token = login_with_account(self.app.spider, phone=phone, pcode=password, login_type=2)
            else:
                token = password
                if len(token) < 20:
                    self.update_status('Token 过短')
                    self.enable_login_btn()
                    return

            if token and test_token_valid(self.app.spider, token):
                self.app.spider.set_token(token)
                self.app.token = token
                self.update_status('登录成功')
                Clock.schedule_once(lambda dt: self.app.show_main_screen(), 0.3)
            else:
                self.update_status('登录失败')
                self.enable_login_btn()
        except Exception as e:
            self.update_status(f'登录错误: {e}')
            self.enable_login_btn()

    def quick_login(self, acc, instance):
        token = acc.get("Token")
        if token:
            self.status_label.text = '登录中...'
            threading.Thread(target=self._quick_login_thread, args=(token, acc), daemon=True).start()

    def _quick_login_thread(self, token, acc):
        try:
            from app.your_code import test_token_valid, load_accounts, save_accounts
            import time

            if test_token_valid(self.app.spider, token):
                self.app.spider.set_token(token)
                self.app.token = token
                accounts = load_accounts(self.app.spider)
                for a in accounts:
                    if a.get("Token") == token:
                        a["最后登录"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        break
                save_accounts(self.app.spider, accounts)
                self.update_status('登录成功')
                Clock.schedule_once(lambda dt: self.app.show_main_screen(), 0.3)
            else:
                self.update_status('Token 已失效')
        except Exception as e:
            self.update_status(f'登录错误: {e}')

    @mainthread
    def update_status(self, text):
        self.status_label.text = text

    @mainthread
    def enable_login_btn(self):
        self.login_btn.disabled = False


class MainScreen(BoxLayout):
    """主界面 - 标签页"""
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.orientation = 'vertical'

        # 日志缓冲区（解决日志卡顿问题）
        self._log_buffer = []
        self._log_update_scheduled = False

        # 背景色
        with self.canvas.before:
            Color(*COLORS['bg'])
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # 顶部状态栏
        top_bar = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(10), dp(5)], spacing=dp(10))
        with top_bar.canvas.before:
            Color(*COLORS['card'])
            self.top_rect = Rectangle(pos=top_bar.pos, size=top_bar.size)
        top_bar.bind(pos=self._update_top, size=self._update_top)

        # 根据登录状态显示不同信息
        if app.token:
            status_text = f'已登录: {app.token[:12]}...'
            status_color = COLORS['text']
        else:
            status_text = '未登录 (部分功能不可用)'
            status_color = COLORS['warning']

        self.status_label = StyledLabel(
            text=status_text,
            size_hint_x=0.65,
            font_size=dp(13),
            color=status_color
        )
        logout_btn = StyledButton(
            text='登录' if not app.token else '退出',
            size_hint_x=0.35,
            bg_color=COLORS['primary'] if not app.token else COLORS['error'],
            on_press=self.logout
        )
        top_bar.add_widget(self.status_label)
        top_bar.add_widget(logout_btn)
        self.add_widget(top_bar)

        # 标签页面板
        self.tabs = TabbedPanel(
            do_default_tab=False,
            tab_width=dp(70),
            tab_height=dp(40),
            background_color=COLORS['bg']
        )

        self.tabs.add_widget(self.create_crawler_tab())
        self.tabs.add_widget(self.create_search_tab())
        self.tabs.add_widget(self.create_vote_tab())
        self.tabs.add_widget(self.create_follow_tab())
        self.tabs.add_widget(self.create_account_tab())

        self.add_widget(self.tabs)

        # 输出日志区
        log_container = CardLayout(size_hint_y=0.32, padding=dp(10))
        self.log_scroll = ScrollView()
        self.log_label = StyledLabel(
            text='[日志输出]\n',
            size_hint_y=None,
            text_size=(Window.width - dp(40), None),
            halign='left',
            valign='top',
            font_size=dp(12)
        )
        self.log_label.bind(texture_size=self.log_label.setter('size'))
        self.log_scroll.add_widget(self.log_label)
        log_container.add_widget(self.log_scroll)
        self.add_widget(log_container)

    def _update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def _update_top(self, *args):
        self.top_rect.pos = args[0].pos
        self.top_rect.size = args[0].size

    def create_tab_content(self, buttons):
        """创建标签页内容"""
        layout = GridLayout(cols=2, spacing=dp(12), padding=dp(15), size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        for text, callback in buttons:
            btn = StyledButton(
                text=text,
                size_hint_y=None,
                height=dp(55),
                on_press=callback
            )
            layout.add_widget(btn)

        scroll = ScrollView()
        scroll.add_widget(layout)
        return scroll

    def create_crawler_tab(self):
        tab = TabbedPanelItem(text='帖子', font_name=DEFAULT_FONT if DEFAULT_FONT else 'Roboto')
        buttons = [
            ('批量搜索多页', self.on_batch_crawl),
            ('搜索特定帖', self.on_crawl_post),
            ('搜索用户全部', self.on_crawl_user),
            ('用户文件', self.on_user_files),
        ]
        tab.add_widget(self.create_tab_content(buttons))
        return tab

    def create_search_tab(self):
        tab = TabbedPanelItem(text='搜索', font_name=DEFAULT_FONT if DEFAULT_FONT else 'Roboto')
        buttons = [
            ('搜索帖子', self.on_search_posts),
            ('用户名搜索', self.on_search_username),
        ]
        tab.add_widget(self.create_tab_content(buttons))
        return tab

    def create_vote_tab(self):
        tab = TabbedPanelItem(text='投票', font_name=DEFAULT_FONT if DEFAULT_FONT else 'Roboto')
        buttons = [
            ('单任务投票', self.on_single_vote),
            ('批量投票', self.on_batch_vote),
            ('投票文件', self.on_vote_files),
        ]
        tab.add_widget(self.create_tab_content(buttons))
        return tab

    def create_follow_tab(self):
        tab = TabbedPanelItem(text='关注', font_name=DEFAULT_FONT if DEFAULT_FONT else 'Roboto')
        buttons = [
            ('查询关注列表', self.on_query_attention),
        ]
        tab.add_widget(self.create_tab_content(buttons))
        return tab

    def create_account_tab(self):
        tab = TabbedPanelItem(text='账号', font_name=DEFAULT_FONT if DEFAULT_FONT else 'Roboto')
        buttons = [
            ('切换账号', self.on_switch_account),
            ('管理账号', self.on_manage_accounts),
            ('Token状态', self.on_token_status),
            ('清除登录', self.on_clear_login),
        ]
        tab.add_widget(self.create_tab_content(buttons))
        return tab

    # ========== 爬虫功能 ==========
    def on_batch_crawl(self, instance):
        dialog = InputDialog(
            title='批量搜索',
            fields=[
                {"key": "start", "label": "开始页码", "default": "1"},
                {"key": "pages", "label": "搜索页数", "default": "3"},
            ],
            callback=self._do_batch_crawl
        )
        dialog.open()

    def _do_batch_crawl(self, values):
        start = int(values.get("start", 1) or 1)
        pages = int(values.get("pages", 3) or 3)
        self.run_task(lambda: self.app.spider.crawl_and_save_posts(start_page=start, max_pages=pages))

    def on_crawl_post(self, instance):
        dialog = InputDialog(
            title='搜索特定帖子',
            fields=[{"key": "pid", "label": "帖子ID", "default": ""}],
            callback=self._do_crawl_post
        )
        dialog.open()

    def _do_crawl_post(self, values):
        pid = int(values.get("pid", 0) or 0)
        if pid:
            self.run_task(lambda: self.app.spider.crawl_specific_post(pid))

    def on_crawl_user(self, instance):
        dialog = InputDialog(
            title='搜索用户全部帖子',
            fields=[
                {"key": "uid", "label": "用户ID", "default": ""},
                {"key": "pages", "label": "搜索页数", "default": "10"},
            ],
            callback=self._do_crawl_user
        )
        dialog.open()

    def _do_crawl_user(self, values):
        uid = int(values.get("uid", 0) or 0)
        pages = int(values.get("pages", 10) or 10)
        if uid:
            self.run_task(lambda: self.app.spider.crawl_user_posts_gui(uid, pages))

    def on_user_files(self, instance):
        self.run_task(lambda: self.app.spider.show_user_files())

    # ========== 搜索功能 ==========
    def on_search_posts(self, instance):
        dialog = InputDialog(
            title='搜索帖子',
            fields=[
                {"key": "keyword", "label": "关键词", "default": ""},
                {"key": "pages", "label": "搜索页数", "default": "3"},
            ],
            callback=self._do_search_posts
        )
        dialog.open()

    def _do_search_posts(self, values):
        keyword = values.get("keyword", "")
        pages = int(values.get("pages", 3) or 3)
        if keyword:
            self.run_task(lambda: self.app.spider.search_and_save_posts_gui(keyword, pages))

    def on_search_username(self, instance):
        dialog = InputDialog(
            title='用户名搜索',
            fields=[
                {"key": "username", "label": "用户名", "default": ""},
                {"key": "pages", "label": "搜索页数", "default": "30"},
                {"key": "threads", "label": "线程数", "default": "8"},
            ],
            callback=self._do_search_username
        )
        dialog.open()

    def _do_search_username(self, values):
        username = values.get("username", "")
        pages = int(values.get("pages", 30) or 30)
        threads = int(values.get("threads", 8) or 8)
        if username:
            self.run_task(lambda: self.app.spider.search_username_gui(username, pages, threads))

    # ========== 投票功能 ==========
    def on_single_vote(self, instance):
        dialog = InputDialog(
            title='单任务投票',
            fields=[{"key": "tid", "label": "任务ID", "default": ""}],
            callback=self._do_single_vote
        )
        dialog.open()

    def _do_single_vote(self, values):
        tid = int(values.get("tid", 0) or 0)
        if tid:
            self.run_task(lambda: self.app.spider.vote_single_gui(tid))

    def on_batch_vote(self, instance):
        dialog = InputDialog(
            title='批量投票',
            fields=[
                {"key": "start", "label": "起始ID", "default": "1"},
                {"key": "end", "label": "结束ID", "default": "100"},
                {"key": "threads", "label": "线程数", "default": "50"},
            ],
            callback=self._do_batch_vote
        )
        dialog.open()

    def _do_batch_vote(self, values):
        start = int(values.get("start", 1) or 1)
        end = int(values.get("end", 100) or 100)
        threads = int(values.get("threads", 50) or 50)
        if start > end:
            start, end = end, start
        self.run_task(lambda: self.app.spider.batch_vote_gui(start, end, threads))

    def on_vote_files(self, instance):
        self.run_task(lambda: self.app.spider.show_vote_files())

    # ========== 关注功能 ==========
    def on_query_attention(self, instance):
        dialog = InputDialog(
            title='查询关注列表',
            fields=[
                {"key": "user_id", "label": "用户ID", "default": ""},
                {"key": "page", "label": "页码", "default": "1"},
            ],
            callback=self._do_query_attention
        )
        dialog.open()

    def _do_query_attention(self, values):
        user_id = values.get("user_id", "").strip()
        page = int(values.get("page", 1) or 1)
        if user_id and user_id.isdigit():
            self.run_task(lambda: self.app.spider.query_attention_gui(int(user_id), page))

    # ========== 账号功能 ==========
    def on_switch_account(self, instance):
        self.app.show_login_screen()

    def on_manage_accounts(self, instance):
        try:
            from app.your_code import load_accounts
            accounts = load_accounts(self.app.spider)
            if not accounts:
                self.log('无保存账号')
                return

            info = '已保存账号:\n'
            for i, acc in enumerate(accounts, 1):
                info += f"{i}. {acc.get('昵称')} - {acc.get('最后登录')}\n"
            self.log(info)
        except Exception as e:
            self.log(f'错误: {e}')

    def on_token_status(self, instance):
        try:
            from app.your_code import check_token_status
            self.run_task(lambda: check_token_status(self.app.spider, self.app.token))
        except Exception as e:
            self.log(f'错误: {e}')

    def on_clear_login(self, instance):
        self.app.spider.clear_login_state()
        self.log('登录状态已清除')

    def logout(self, instance):
        self.app.token = None
        self.app.show_login_screen()

    # ========== 工具方法 ==========
    def run_task(self, func, require_login=True):
        """在后台线程运行任务"""
        # 检查是否需要登录
        if require_login and not self.app.token:
            self.log('此功能需要登录，请先登录账号')
            return

        def wrapper():
            import builtins
            old_print = builtins.print
            builtins.print = self.log
            try:
                func()
            except Exception as e:
                self.log(f'错误: {e}')
            finally:
                builtins.print = old_print

        threading.Thread(target=wrapper, daemon=True).start()

    @mainthread
    def log(self, *args, **kwargs):
        """日志输出 - 使用缓冲区批量更新，避免UI卡顿"""
        text = ' '.join(str(a) for a in args) + '\n'
        self._log_buffer.append(text)

        # 安排批量更新，避免频繁刷新UI
        if not self._log_update_scheduled:
            self._log_update_scheduled = True
            Clock.schedule_once(self._flush_log_buffer, 0.1)

    def _flush_log_buffer(self, dt=None):
        """刷新日志缓冲区到UI"""
        self._log_update_scheduled = False
        if not self._log_buffer:
            return

        # 合并所有缓冲的日志
        new_text = ''.join(self._log_buffer)
        self._log_buffer.clear()

        # 更新日志显示
        current_text = self.log_label.text
        self.log_label.text = current_text + new_text

        # 限制日志长度，防止内存占用过高
        if len(self.log_label.text) > 15000:
            self.log_label.text = self.log_label.text[-10000:]

        # 滚动到底部
        self.log_scroll.scroll_y = 0


class BDSMApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spider = None
        self.token = None
        self.root_widget = None

    def build(self):
        self.title = 'BDSM 论坛工具'
        Window.clearcolor = COLORS['bg']

        # 在 Android 上先请求权限
        self._request_permissions_on_start()

        self.root_widget = BoxLayout()

        # 延迟初始化 spider 和显示登录界面
        Clock.schedule_once(self.init_app, 0.5)

        # 先显示加载画面
        loading = BoxLayout(orientation='vertical')
        with loading.canvas.before:
            Color(*COLORS['bg'])
            Rectangle(pos=(0, 0), size=Window.size)
        loading.add_widget(StyledLabel(
            text='加载中...',
            font_size=dp(20)
        ))
        self.root_widget.add_widget(loading)

        return self.root_widget

    def _request_permissions_on_start(self):
        """应用启动时请求所有存储权限（覆盖所有Android版本）"""
        try:
            from kivy.utils import platform
            if platform != 'android':
                return

            from android.permissions import request_permissions, Permission
            import android

            # 获取Android SDK版本
            sdk_version = int(android.api_version)
            print(f"Android SDK版本: {sdk_version}")

            permissions_to_request = []

            # Android 13+ (API 33+) 需要细分的媒体权限
            if sdk_version >= 33:
                permissions_to_request.extend([
                    Permission.READ_MEDIA_IMAGES,
                    Permission.READ_MEDIA_VIDEO,
                    Permission.READ_MEDIA_AUDIO,
                ])

            # Android 11+ (API 30+) 需要 MANAGE_EXTERNAL_STORAGE
            if sdk_version >= 30:
                # MANAGE_EXTERNAL_STORAGE 需要特殊处理，跳转设置页面
                try:
                    from android import mActivity
                    from jnius import autoclass

                    Environment = autoclass('android.os.Environment')
                    if not Environment.isExternalStorageManager():
                        Intent = autoclass('android.content.Intent')
                        Settings = autoclass('android.provider.Settings')
                        Uri = autoclass('android.net.Uri')

                        intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
                        uri = Uri.parse("package:" + mActivity.getPackageName())
                        intent.setData(uri)
                        mActivity.startActivity(intent)
                except Exception as e:
                    print(f"请求MANAGE_EXTERNAL_STORAGE失败: {e}")

            # Android 6-12 (API 23-32) 使用传统存储权限
            permissions_to_request.extend([
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
            ])

            # 请求权限
            if permissions_to_request:
                print(f"请求权限: {permissions_to_request}")
                request_permissions(permissions_to_request)

        except ImportError as e:
            print(f"导入android模块失败: {e}")
        except Exception as e:
            print(f"请求权限失败: {e}")

    def init_app(self, dt):
        """延迟初始化"""
        try:
            from app.your_code import BDSMForumSpider, test_token_valid

            # 确定数据保存目录
            data_dir = self._get_data_dir()
            self.spider = BDSMForumSpider(data_dir=data_dir)
            print(f"数据保存目录: {data_dir}")

            # 尝试自动登录
            auto_token = self.spider.load_login_state()
            if auto_token:
                # 在后台线程验证 token
                threading.Thread(target=self._try_auto_login, args=(auto_token,), daemon=True).start()
            else:
                self.show_login_screen()
        except Exception as e:
            print(f"初始化失败: {e}")
            # 即使失败也要创建 spider，避免 None 错误
            try:
                from app.your_code import BDSMForumSpider
                data_dir = self._get_data_dir()
                self.spider = BDSMForumSpider(data_dir=data_dir)
            except:
                pass
            self.show_login_screen(error_msg=f"初始化错误: {e}")

    def _get_data_dir(self):
        """获取数据保存目录，Android上使用 /sdcard/bdsm数据/"""
        try:
            from kivy.utils import platform
            if platform == 'android':
                # 尝试申请存储权限
                self._request_android_permissions()
                # 使用外部存储目录
                sdcard_dir = "/sdcard/bdsm数据"
                try:
                    os.makedirs(sdcard_dir, exist_ok=True)
                    # 测试是否可写
                    test_file = os.path.join(sdcard_dir, ".test_write")
                    with open(test_file, 'w') as f:
                        f.write("test")
                    os.remove(test_file)
                    print(f"使用外部存储: {sdcard_dir}")
                    return sdcard_dir
                except Exception as e:
                    print(f"外部存储不可用: {e}，使用应用内目录")
                    return os.path.join(self.user_data_dir, "bdsm_data")
            else:
                # 非Android平台使用应用数据目录
                return os.path.join(self.user_data_dir, "bdsm_data")
        except Exception as e:
            print(f"获取数据目录失败: {e}")
            return os.path.join(self.user_data_dir, "bdsm_data")

    def _request_android_permissions(self):
        """申请Android存储权限"""
        try:
            from android.permissions import request_permissions, Permission, check_permission

            # 检查是否已有权限
            if not check_permission(Permission.WRITE_EXTERNAL_STORAGE):
                print("申请存储权限...")
                request_permissions([
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE
                ])
                # 等待权限结果
                import time
                time.sleep(1)
        except ImportError:
            # 非Android平台或没有android模块
            pass
        except Exception as e:
            print(f"申请权限失败: {e}")

    def _try_auto_login(self, token):
        try:
            from app.your_code import test_token_valid
            if test_token_valid(self.spider, token):
                self.spider.set_token(token)
                self.token = token
                Clock.schedule_once(lambda dt: self.show_main_screen(), 0)
            else:
                Clock.schedule_once(lambda dt: self.show_login_screen(), 0)
        except:
            Clock.schedule_once(lambda dt: self.show_login_screen(), 0)

    @mainthread
    def show_login_screen(self, error_msg=None):
        self.root_widget.clear_widgets()
        self.root_widget.add_widget(LoginScreen(self, error_msg=error_msg))

    @mainthread
    def show_main_screen(self):
        self.root_widget.clear_widgets()
        self.root_widget.add_widget(MainScreen(self))


if __name__ == '__main__':
    BDSMApp().run()
