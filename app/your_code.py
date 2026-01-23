#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time
import os
import re
import threading
from typing import Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

INVALID_CHARS = re.compile(r'[<>:\"/|?*]')
LOGIN_STATE_FILE = "login_state.json"

class ResultSaver:
    def __init__(self, save_dir, filename_prefix, start_info="", end_info=""):
        os.makedirs(save_dir, exist_ok=True)
        
        self.save_dir = save_dir
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        if start_info and end_info:
            self.filename = f"{filename_prefix}_{start_info}到{end_info}_{timestamp}.txt"
        else:
            self.filename = f"{filename_prefix}_{timestamp}.txt"
        
        self.filepath = os.path.join(save_dir, self.filename)
        self._write_header(start_info, end_info)
    
    def _write_header(self, start_info, end_info):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("                   任务结果报告\n")
            f.write("="*70 + "\n")
            f.write(f"任务时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            if start_info and end_info:
                f.write(f"任务范围: {start_info} 到 {end_info}\n")
            f.write(f"保存位置: {self.save_dir}\n")
            f.write("="*70 + "\n\n")
            f.write("详细任务记录:\n")
            f.write("="*70 + "\n")
            f.write("时间                   任务ID/名称     状态       详情\n")
            f.write("-"*70 + "\n")
    
    def save_record(self, task_id, status, details):
        try:
            with open(self.filepath, 'a', encoding='utf-8') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{timestamp}  {str(task_id):12s}   {status:8s} | {details}\n")
        except Exception as e:
            print(f"保存记录失败: {e}")
    
    def finalize(self, success, failed, total, elapsed, extra_stats=None):
        try:
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write("="*70 + "\n\n")
                f.write("任务统计信息:\n")
                f.write("="*70 + "\n")
                f.write(f"结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总任务数: {total}\n")
                f.write(f"成功数量: {success}\n")
                f.write(f"失败数量: {failed}\n")
                
                if extra_stats:
                    for key, value in extra_stats.items():
                        f.write(f"{key}: {value}\n")
                
                f.write(f"总耗时: {elapsed:.1f}秒\n")
                if elapsed > 0:
                    f.write(f"平均速度: {total/elapsed:.1f} 任务/秒\n")
                f.write(f"文件位置: {self.save_dir}\n")
                f.write(f"文件名: {self.filename}\n")
                f.write("="*70 + "\n")
        except Exception as e:
            print(f"完成文件失败: {e}")

class UsernamePostSearcher:
    def __init__(self, spider, keyword, threads=200, max_pages=5000, saver=None):
        self.spider = spider
        self.keyword = keyword
        self.threads = threads
        self.max_pages = max_pages
        self.saver = saver
        self.found_users = []
        self.lock = threading.Lock()
        self.seen_user_ids = set()
        self.user_cache = {}
        
    def get_user_full_info_cached(self, user_id):
        if user_id in self.user_cache:
            return self.user_cache[user_id]
        
        full_info = self.spider.get_complete_user_info(user_id)
        if full_info:
            self.user_cache[user_id] = full_info
            return full_info
        
        return None
    
    def search_page(self, page):
        try:
            result = self.spider.get_posts(page=page)
            if not result["success"]:
                if self.saver:
                    self.saver.save_record(f"第{page}页", "❌", f"获取失败: {result.get('error')}")
                return
            
            posts = result.get("data", [])
            page_found = 0
            
            for post in posts:
                user_info = post.get("user", {})
                user_id = user_info.get("id") or post.get("user_id")
                
                if not user_id:
                    continue
                
                full_info = self.get_user_full_info_cached(user_id)
                if not full_info:
                    continue
                    
                username = full_info.get("name", "")
                
                if user_id and self.keyword in username:
                    with self.lock:
                        if user_id not in self.seen_user_ids:
                            self.seen_user_ids.add(user_id)
                            
                            full_info['found_page'] = page
                            self.found_users.append(full_info)
                            page_found += 1
                            
                            count = len(self.found_users)
                            print(f"\n[{count}] 👤 {full_info['name']} (ID:{full_info['id']}) 第{page}页")
                            
                            self.spider.display_complete_user_info(full_info)
                            
                            if self.saver:
                                details = f"用户名: {full_info['name']}"
                                if full_info.get('sex_text'):
                                    details += f", 性别: {full_info['sex_text']}"
                                if full_info.get('sex_p_text'):
                                    details += f", 属性: {full_info['sex_p_text']}"
                                self.saver.save_record(f"用户{full_info['id']}", "✅", details)
            
            if self.saver:
                self.saver.save_record(f"第{page}页", "📊", f"处理{len(posts)}条帖子，找到{page_found}个用户")
            
            print(f"📄 第{page}页完成: {len(posts)}条帖子，找到{page_found}个用户", end='\r')
            
        except Exception as e:
            if self.saver:
                self.saver.save_record(f"第{page}页", "❌", f"搜索失败: {e}")
    
    def search_all(self):
        print(f"\n🔍 开始多线程搜索... (线程数: {self.threads}, 页数: {self.max_pages})")
        
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            for page in range(1, self.max_pages + 1):
                future = executor.submit(self.search_page, page)
                futures.append(future)
                time.sleep(0.1)
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"⚠️  任务异常: {e}")
        
        return self.found_users

class BDSMForumSpider:
    def __init__(self, token="", data_dir=None, interactive=False):
        if data_dir is None:
            if interactive:
                print("=" * 60)
                default_dir = "bdsm_data"
                data_dir = input(f"请输入数据保存目录 (默认: {default_dir}): ").strip()
                if not data_dir:
                    data_dir = default_dir
            else:
                data_dir = "bdsm_data"

        self.base_url = "https://suo.jiushu1234.com"
        self.token = token
        self.headers = self.get_generic_headers()

        self.payload_template = {
            "page": 1,
            "order": {"create_time": "desc"},
            "append": {
                "1": "files",
                "3": "is_dig",
                "6": "play.u",
                "7": "play_digs",
                "8": "gt_info",
                "user": ["sex_text", "sex_p_text", "sex_o_text"]
            },
            "with_count": ["comments", "favos", "digs"],
            "kw": "",
        }

        self.current_page = 1
        self.has_more = True

        self.data_dir = data_dir
        self.users_dir = os.path.join(data_dir, "帖子")
        self.votes_dir = os.path.join(data_dir, "投票")
        self.attention_dir = os.path.join(data_dir, "关注")
        self.search_dir = os.path.join(data_dir, "搜索")
        self.accounts_dir = os.path.join(data_dir, "账号")
        self.accounts_file = os.path.join(data_dir, "账号", "accounts.json")
        
        self.init_data_dirs()

    def init_data_dirs(self):
        dirs = [
            self.data_dir, 
            self.users_dir, 
            self.votes_dir, 
            self.attention_dir,
            self.search_dir,
            self.accounts_dir
        ]
        for path in dirs:
            os.makedirs(path, exist_ok=True)

    def get_generic_headers(self):
        headers = {
            "Host": "suo.jiushu1234.com",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": self.base_url,
            "X-Requested-With": "mark.via.gp",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": f"{self.base_url}/pd/",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        ua = ("Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36")
        headers.update({"User-Agent": ua, "lang": "zh", "plat": "android"})
        if self.token:
            headers["token"] = self.token
        return headers

    def set_token(self, token: str):
        self.token = token
        self.headers["token"] = token
        print(f"✅ Token已设置: {token[:20]}...")
        
        self.save_login_state(token)

    def save_login_state(self, token):
        login_state = {
            "token": token,
            "last_login": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expire_time": time.time() + 30 * 24 * 60 * 60
        }
        try:
            state_file = os.path.join(self.accounts_dir, "login_state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(login_state, f, ensure_ascii=False, indent=2)
            print(f"💾 登录状态已保存到账号目录")
        except Exception as e:
            print(f"❌ 保存登录状态失败: {e}")

    def load_login_state(self):
        try:
            state_file = os.path.join(self.accounts_dir, "login_state.json")
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    login_state = json.load(f)
                    
                if login_state.get("expire_time", 0) > time.time():
                    token = login_state.get("token")
                    if token and len(token) > 20:
                        last_login = login_state.get("last_login", "未知")
                        print(f"🔑 读取上次登录状态: {last_login}")
                        return token
                else:
                    print("⏰ 登录状态已过期，需要重新登录")
            else:
                print("📝 首次使用，需要登录")
        except Exception as e:
            print(f"❌ 读取登录状态失败: {e}")
        return None

    def clear_login_state(self):
        try:
            state_file = os.path.join(self.accounts_dir, "login_state.json")
            if os.path.exists(state_file):
                os.remove(state_file)
                print("🗑️  已清除登录状态")
        except:
            pass

    def get_field_comments(self):
        return {
            "id": "ID",
            "code": "响应代码",
            "msg": "响应消息",
            "data": "数据主体",
            "total": "总记录数",
            "per_page": "每页数量",
            "current_page": "当前页码",
            "last_page": "总页数",
            "uid": "被关注者用户ID",
            "attention_id": "关注记录ID",
            "create_time": "创建时间",
            "update_time": "更新时间",
            "user_id": "用户ID",
            "status": "状态",
            "title": "标题",
            "pic": "头像",
            "onclick": "浏览量",
            "play_id": "播放ID",
            "time_add": "额外时间",
            "time_end": "结束时间",
            "gongt_id": "公告ID",
            "myorder": "排序值",
            "sex": "性别代码",
            "rank_time": "排名时间",
            "nums": "数量",
            "com_count": "评论数",
            "dig_count": "点赞数",
            "rank": "排名",
            "com_my": "我的评论",
            "rank_admin": "管理员排名",
            "counts": "计数",
            "qr_id": "二维码ID",
            "video": "视频",
            "video_poster": "视频封面",
            "day_rank": "日排名",
            "create_time1": "创建时间1",
            "banner": "横幅",
            "game_id": "游戏ID",
            "is_zl": "是否置顶",
            "title_zl": "置顶标题",
            "tags": "标签",
            "reason": "原因",
            "os_id": "操作系统ID",
            "os_cate": "操作系统分类",
            "favo_count": "收藏数",
            "goods_id": "商品ID",
            "icon_tag": "图标标签",
            "ip": "IP地址",
            "is_black": "是否黑名单",
            "is_wd": "是否违规",
            "pump_qr_id": "泵二维码ID",
            "dig_down": "点踩数",
            "is_hot": "是否热门",
            "rank_good_bad": "好评差评",
            "rank_b": "B排名",
            "count_gz": "关注数",
            "file_del_num": "删除文件数",
            "rank_res": "资源排名",
            "rank_day_hour_time": "日小时排名时间",
            "rank_day_hour": "日小时排名",
            "sex_o": "性取向代码",
            "ext_field": "扩展字段",
            "files": "图片列表",
            "is_dig": "是否已点赞",
            "play": "播放内容",
            "play_digs": "播放点赞",
            "gt_info": "其他信息",
            "user": "用户信息",
            "user_name": "用户名",
            "is_admin": "是否管理员",
            "rz_sex": "认证性别",
            "tag": "标签",
            "icons": "图标",
            "birthday": "生日",
            "age": "年龄",
            "country_pic": "国旗图片",
            "sex_p": "角色代码",
            "jg_num": "警告次数",
            "pic_border": "头像边框",
            "sex_text": "性别",
            "sex_p_text": "角色",
            "sex_o_text": "性取向",
            "nick_name": "昵称",
            "intro": "个人简介",
            "country": "地区",
            "height": "身高",
            "weight": "体重",
            "last_time": "最后在线时间",
            "update_time": "更新时间",
            "money": "余额",
            "user_group_id": "用户组ID",
            "name": "真实姓名",
            "leader": "是否为领导",
            "address": "地址",
            "fen": "积分",
            "group_time": "入群时间",
            "openid": "微信openid",
            "keys": "钥匙数量",
            "is_chat": "是否允许聊天",
            "is_check": "是否已验证",
            "is_delc": "是否已删除",
            "fsr_friend": "好友数",
            "fsr_sm": "SM相关数",
            "fsr_circle": "圈子数",
            "time_cold": "冷却时间",
            "is_cold": "是否冷却中",
            "is_has_ele": "是否有元素",
            "ele_cold_num": "元素冷却数量",
            "ele_cold": "元素冷却",
            "last_ele_link": "最后元素链接时间",
            "crank": "排名",
            "rank_code": "等级代码",
            "quick_dels": "快速删除设置",
            "quick_orders": "快速排序设置",
            "star_color": "星星颜色",
            "rank_code1": "等级代码1",
            "rank_code2": "等级代码2",
            "last_line": "最后线路",
            "friend_time": "成为好友时间",
            "pump_rate": "泵率",
            "is_dh": "是否为DH",
            "is_no_circle": "是否无圈子",
            "is_unlock": "是否解锁",
            "is_rl": "是否为RL",
            "sex_cert": "性别认证",
            "zuan": "钻石数量",
            "table_name": "表名",
            "data_id": "数据ID",
            "basename": "基础名称",
            "extension": "扩展名",
            "field": "字段名",
            "filename": "文件名",
            "size": "大小",
            "type": "类型",
            "url": "图片链接",
            "ges": "其他信息",
            "check_code": "检查代码",
            "wavs": "音频信息",
            "_query_info": "查询信息",
            "_note": "注释说明",
            "api_response": "API响应数据",
            "query_time": "查询时间",
            "query_timestamp": "查询时间戳",
        }

    def format_json_with_comments(self, data: Dict) -> str:
        if not data:
            return "{}"
        
        field_comments = self.get_field_comments()
        
        def format_value(key, value, level, indent="  "):
            indent_str = indent * level
            comment = field_comments.get(key, "")
            comment_str = f"  // {comment}" if comment else ""
            
            if isinstance(value, dict):
                if not value:
                    return f'{indent_str}"{key}": {{{comment_str}\n{indent_str}}},\n'
                
                formatted = f'{indent_str}"{key}": {{{comment_str}\n'
                keys_list = list(value.keys())
                
                if key == "u":
                    keys_list = ["id"] + [k for k in keys_list if k != "id"]
                
                for i, k in enumerate(keys_list):
                    v = value[k]
                    is_last = i == len(keys_list) - 1
                    formatted_line = format_value(k, v, level + 1, indent)
                    if is_last and formatted_line.endswith(",\n"):
                        formatted_line = formatted_line[:-2] + "\n"
                    formatted += formatted_line
                
                formatted += f'{indent_str}}}'
                if level > 0 and not (level == 2 and key == "user"):
                    formatted += ","
                formatted += "\n"
                return formatted
                
            elif isinstance(value, list):
                if not value:
                    return f'{indent_str}"{key}": []{comment_str},\n'
                
                formatted = f'{indent_str}"{key}": [{comment_str}\n'
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        formatted += f'{indent_str}  {{\n'
                        item_keys = list(item.keys())
                        
                        if "u" in item_keys:
                            item_keys = ["id"] + [k for k in item_keys if k != "id"]
                        
                        for j, k in enumerate(item_keys):
                            v = item[k]
                            is_last_item = j == len(item_keys) - 1
                            item_formatted = format_value(k, v, level + 2, indent)
                            if is_last_item and item_formatted.endswith(",\n"):
                                item_formatted = item_formatted[:-2] + "\n"
                            formatted += item_formatted
                        formatted += f'{indent_str}  }}'
                    else:
                        item_str = json.dumps(item, ensure_ascii=False)
                        formatted += f'{indent_str}  {item_str}'
                    
                    if i < len(value) - 1:
                        formatted += ",\n"
                    else:
                        formatted += f'\n{indent_str}]'
                
                if level > 0:
                    formatted += ","
                formatted += "\n"
                return formatted
                
            else:
                formatted = f'{indent_str}"{key}": '
                if value is None:
                    formatted += "null"
                elif isinstance(value, str):
                    escaped = json.dumps(value, ensure_ascii=False)
                    formatted += escaped
                elif isinstance(value, bool):
                    formatted += str(value).lower()
                else:
                    formatted += str(value)
                
                formatted += f'{comment_str},\n'
                return formatted
        
        result = "{\n"
        keys = list(data.keys())
        
        is_attention_data = any(field in keys for field in ["_query_info", "_note", "api_response"])
        
        if is_attention_data:
            priority_fields = []
            for field in ["_query_info", "_note", "api_response"]:
                if field in keys:
                    priority_fields.append(field)
                    keys.remove(field)
            
            for field in ["id", "create_time", "user_id"]:
                if field in keys:
                    priority_fields.append(field)
                    keys.remove(field)
                    
            keys = priority_fields + keys
        else:
            priority_fields = []
            for field in ["id", "create_time", "user_id", "title", "content"]:
                if field in keys:
                    priority_fields.append(field)
                    keys.remove(field)
                    
            keys = priority_fields + keys
        
        for i, key in enumerate(keys):
            value = data[key]
            is_last = i == len(keys) - 1
            formatted = format_value(key, value, 1)
            
            if is_last and formatted.endswith(",\n"):
                formatted = formatted[:-2] + "\n"
            
            result += formatted
        
        if result.endswith(",\n"):
            result = result[:-2] + "\n"
        
        result += "}"
        return result

    def display_post_for_browsing(self, post_data: Dict, index: int = None):
        if not post_data:
            return
        
        post_id = post_data.get("id")
        user_info = post_data.get("user", {})
        user_id = user_info.get("id") or post_data.get("user_id")
        
        if index is not None:
            print(f"\n[{index}] 帖子ID: {post_id}")
        
        complete_user_info = None
        if user_id:
            complete_user_info = self.get_complete_user_info(user_id)
        
        if complete_user_info:
            print(f"   👤 用户: {complete_user_info.get('name', f'用户_{user_id}')} (ID: {user_id})")
            
            if complete_user_info.get('age'):
                print(f"   🎂 年龄: {complete_user_info['age']}", end="")
                if complete_user_info.get('birthday'):
                    print(f" | 生日: {complete_user_info['birthday']}")
                else:
                    print()
            
            if complete_user_info.get('sex_text'):
                gender_info = f"性别: {complete_user_info['sex_text']}"
                if complete_user_info.get('sex_o_text'):
                    gender_info += f" | 性取向: {complete_user_info['sex_o_text']}"
                if complete_user_info.get('sex_p_text'):
                    gender_info += f" | 角色: {complete_user_info['sex_p_text']}"
                print(f"   ⚧️  {gender_info}")
            
            if complete_user_info.get('height'):
                print(f"   📏 身高: {complete_user_info['height']}", end="")
                if complete_user_info.get('weight'):
                    print(f" | 体重: {complete_user_info['weight']}")
                else:
                    print()
            
            if complete_user_info.get('country'):
                print(f"   📍 地区: {complete_user_info['country']}")
            
            if complete_user_info.get('last_time'):
                print(f"   ⏰ 最后在线: {complete_user_info['last_time']}")
        
        elif user_info.get('user_name'):
            print(f"   👤 用户: {user_info['user_name']} (ID: {user_id})")
        
        if post_data.get('create_time'):
            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(post_data.get("create_time", 0)))
            print(f"   📅 发布时间: {create_time}")
        
        has_content = False
        if 'content' in post_data and post_data['content'] and post_data['content'].strip():
            content = post_data['content']
            if len(content) > 150:
                print(f"   📝 内容: {content[:150]}...")
            else:
                print(f"   📝 内容: {content}")
            has_content = True
        else:
            title = post_data.get('title', '')
            if title and title.strip():
                if len(title) > 150:
                    print(f"   📝 内容: {title[:150]}...")
                else:
                    print(f"   📝 内容: {title}")
                has_content = True
        
        if not has_content:
            print(f"   📝 内容: [此帖无文字内容]")
        
        print(f"   📊 浏览: {post_data.get('onclick', 0)} | 赞: {post_data.get('dig_count', 0)} | 评论: {post_data.get('com_count', 0)}")
        
        files = post_data.get("files", [])
        if isinstance(files, list) and files:
            image_urls = []
            for f in files:
                url = ""
                if isinstance(f, dict):
                    url = f.get('url', '')
                elif isinstance(f, str) and f.startswith('http'):
                    url = f
                
                if url and url.startswith('http'):
                    image_urls.append(url)
            
            if image_urls:
                print(f"   🖼️  图片数量: {len(image_urls)}张")
                
                for i, url in enumerate(image_urls, 1):
                    print(f"     图片{i}: {url}")
            else:
                print(f"   📁 附件数量: {len(files)}个 [无有效图片链接]")

    def get_complete_user_info(self, user_id):
        try:
            r = requests.post(
                f"{self.base_url}/api.php/user/show",
                headers=self.headers,
                json={"id": user_id},
                timeout=10
            )
            data = r.json()
            
            if data.get("code") == 1 and data.get("data"):
                user = data["data"]
                
                last_time_raw = user.get("last_time")
                last_time_str = ""
                if last_time_raw:
                    try:
                        if isinstance(last_time_raw, (int, float)) and last_time_raw > 0:
                            last_time_str = datetime.fromtimestamp(last_time_raw).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            last_time_str = str(last_time_raw)
                    except:
                        last_time_str = str(last_time_raw)
                
                complete_info = {
                    "id": user_id,
                    "user_id": user_id,
                    "user_name": user.get("user_name", f"用户_{user_id}"),
                    "name": user.get("user_name", f"用户_{user_id}"),
                    "nick_name": user.get("nick_name", ""),
                    "height": user.get("height", ""),
                    "weight": user.get("weight", ""),
                    "age": user.get("age", ""),
                    "birthday": user.get("birthday", ""),
                    "sex_text": self.get_sex_text(user),
                    "sex_o_text": self.get_sex_o_text(user),
                    "sex_p_text": self.get_sex_p_text(user),
                    "country": user.get("country", ""),
                    "country_pic": user.get("country_pic", ""),
                    "last_time": last_time_str,
                    "last_time_raw": last_time_raw,
                    "intro": user.get("intro", ""),
                    "user_url": f"{self.base_url}/pd/#/page/user_show/user_show?id={user_id}",
                    "pic": user.get("country_pic", ""),
                }
                return complete_info
                
        except Exception as e:
            print(f"❌ 获取用户{user_id}信息失败: {e}")
        
        return {
            "id": user_id,
            "user_id": user_id,
            "user_name": f"用户_{user_id}",
            "name": f"用户_{user_id}",
            "height": "",
            "weight": "",
            "age": "",
            "birthday": "",
            "sex_text": "",
            "sex_o_text": "",
            "sex_p_text": "",
            "country": "",
            "last_time": "",
            "user_url": f"{self.base_url}/pd/#/page/user_show/user_show?id={user_id}",
        }

    def display_complete_user_info(self, user_info, prefix="   ", compact=False):
        if not user_info:
            return
            
        username = user_info.get('name', '')
        user_id = user_info.get('id', '')
        
        if not compact:
            print(f"{prefix}👤 {username} (ID:{user_id})")
        
        info_lines = []
        
        age_info = ""
        if user_info.get('age'):
            age_info = f"年龄: {user_info['age']}岁"
            if user_info.get('birthday'):
                age_info += f" | 生日: {user_info['birthday']}"
            info_lines.append(age_info)
        
        gender_info_parts = []
        if user_info.get('sex_text'):
            gender_info_parts.append(f"性别: {user_info['sex_text']}")
        if user_info.get('sex_o_text'):
            gender_info_parts.append(f"性取向: {user_info['sex_o_text']}")
        if user_info.get('sex_p_text'):
            gender_info_parts.append(f"角色: {user_info['sex_p_text']}")
        
        if gender_info_parts:
            info_lines.append(" | ".join(gender_info_parts))
        
        if user_info.get('height'):
            body_info = f"身高: {user_info['height']}cm"
            if user_info.get('weight'):
                body_info += f" | 体重: {user_info['weight']}kg"
            info_lines.append(body_info)
        
        if user_info.get('country'):
            info_lines.append(f"地区: {user_info['country']}")
        
        if user_info.get('last_time'):
            info_lines.append(f"最后在线: {user_info['last_time']}")
        
        for line in info_lines:
            print(f"{prefix}{line}")
        
        if not compact and info_lines:
            print(f"{prefix}{'-' * 40}")

    def get_sex_text(self, user):
        sex_text = user.get("sex_text")
        if sex_text and sex_text != "未知" and not sex_text.startswith("用户_"):
            return sex_text
        sex_map = {1: "男", 2: "女", 3: "伪娘", 4: "跨性别男性", 5: "跨性别女性"}
        sex_val = user.get("sex", 0)
        return sex_map.get(sex_val, "")

    def get_sex_o_text(self, user):
        sex_o_text = user.get("sex_o_text")
        if sex_o_text and sex_o_text != "未知" and not sex_o_text.startswith("用户_"):
            return sex_o_text
        sex_o_map = {1: "双重", 2: "异性恋", 3: "男同", 4: "女同", 0: ""}
        sex_o_raw = user.get("sex_o", 0)
        if isinstance(sex_o_raw, str) and sex_o_raw.isdigit():
            sex_o_raw = int(sex_o_raw)
        return sex_o_map.get(sex_o_raw, "")

    def get_sex_p_text(self, user):
        sex_p_text = user.get("sex_p_text")
        if sex_p_text and sex_p_text != "未知" and not sex_p_text.startswith("用户_"):
            return sex_p_text
        sex_p_map = {1: "Dom", 2: "Sub", 3: "S", 4: "M", 5: "Switch", 0: ""}
        return sex_p_map.get(user.get("sex_p", 0), "")

    def format_user_archive_text(self, user_info):
        text = f"{'='*60}\n👤 帖子用户档案\n{'='*60}\n"
        text += f"用户ID: {user_info['id']}\n"
        
        user_name = user_info.get('name', f'用户_{user_info["id"]}')
        text += f"用户名: {user_name}\n"
        
        if user_info.get('age') and user_info['age'] != "未知":
            text += f"年龄: {user_info['age']}岁\n"
        if user_info.get('birthday') and user_info['birthday'] != "未知":
            text += f"生日: {user_info['birthday']}\n"
        
        if user_info.get('sex_text') and user_info['sex_text'] != "未知":
            text += f"性别: {user_info['sex_text']}\n"
        if user_info.get('sex_o_text') and user_info['sex_o_text'] != "未知":
            text += f"性取向: {user_info['sex_o_text']}\n"
        if user_info.get('sex_p_text') and user_info['sex_p_text'] != "未知":
            text += f"角色: {user_info['sex_p_text']}\n"
        
        if user_info.get('height'):
            text += f"身高: {user_info['height']}cm\n"
        if user_info.get('weight'):
            text += f"体重: {user_info['weight']}kg\n"
        
        if user_info.get('country'):
            text += f"地区: {user_info['country']}\n"
        
        if user_info.get('last_time'):
            text += f"最后在线时间: {user_info['last_time']}\n"
        
        text += f"档案创建时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"{'='*60}\n📝 帖子列表\n{'='*60}\n"
        
        return text

    def search_username(self):
        print("\n" + "=" * 50)
        print("🔍 用户名搜索")
        print("=" * 50)
        
        print("1. 搜索用户名")
        print("2. 搜索用户ID")
        choice = input("请选择搜索方式 (1-2): ").strip()
        
        if choice == "1":
            self.search_by_username_from_posts()
        elif choice == "2":
            self.search_by_userid()
        else:
            print("❌ 无效选择")

    def search_by_username_from_posts(self):
        keyword = input("请输入要搜索的关键词: ").strip()
        if not keyword:
            print("❌ 请输入关键词")
            return
        
        print("\n🔧 自定义配置:")
        
        try:
            max_pages = int(input(f"搜索页数 (默认30, 最大5000): ").strip() or "30")
            max_pages = max(1, min(5000, max_pages))
        except:
            max_pages = 30
        
        try:
            threads = int(input(f"线程数 (默认8, 最大200): ").strip() or "8")
            threads = max(1, min(200, threads))
        except:
            threads = 8
        
        print(f"\n{'='*60}")
        print(f"🔍 搜索用户名包含 '{keyword}' 的用户")
        print(f"📄 搜索页数: {max_pages}")
        print(f"⚡ 使用 {threads} 个线程")
        print("=" * 60)
        
        searcher = UsernamePostSearcher(self, keyword, threads, max_pages, saver=None)
        
        start_time = time.time()
        
        found_users = searcher.search_all()
        
        elapsed = time.time() - start_time
        
        print(f"\n\n✅ 搜索完成！")
        print(f"⏱️  耗时: {elapsed:.1f}秒")
        print(f"👤 找到 {len(found_users)} 个用户")
        
        if found_users:
            print("\n📊 用户统计:")
            sex_count = {}
            sex_o_count = {}
            sex_p_count = {}
            
            for user in found_users:
                sex_count[user.get('sex_text', '未知')] = sex_count.get(user.get('sex_text', '未知'), 0) + 1
                sex_o_count[user.get('sex_o_text', '未知')] = sex_o_count.get(user.get('sex_o_text', '未知'), 0) + 1
                sex_p_count[user.get('sex_p_text', '未知')] = sex_p_count.get(user.get('sex_p_text', '未知'), 0) + 1
            
            sex_count = {k: v for k, v in sex_count.items() if k and k != '未知'}
            sex_o_count = {k: v for k, v in sex_o_count.items() if k and k != '未知'}
            sex_p_count = {k: v for k, v in sex_p_count.items() if k and k != '未知'}
            
            if sex_count:
                print(f"  性别: {', '.join([f'{k}:{v}人' for k, v in sex_count.items()])}")
            if sex_o_count:
                print(f"  性取向: {', '.join([f'{k}:{v}人' for k, v in sex_o_count.items()])}")
            if sex_p_count:
                print(f"  属性: {', '.join([f'{k}:{v}人' for k, v in sex_p_count.items()])}")
        
        if found_users:
            print("\n💾 正在保存用户信息到搜索目录...")
            saved_count = 0
            for user in found_users:
                if self.save_user_info_to_search_dir(user):
                    saved_count += 1
                time.sleep(0.1)
            print(f"✅ 已将 {saved_count}/{len(found_users)} 个用户保存到 {self.search_dir}/")
        
        return found_users

    def search_by_userid(self):
        user_id = input("请输入用户ID (如88905): ").strip()
        if not user_id or not user_id.isdigit():
            print("❌ 请输入有效的用户ID")
            return
        
        user_id = int(user_id)
        print(f"\n🔍 搜索用户ID: {user_id}")
        print("=" * 60)
        
        user_info = self.get_complete_user_info(user_id)
        
        if user_info:
            print(f"\n👤 {user_info['name']} (ID:{user_info['id']})")
            self.display_complete_user_info(user_info, prefix="   ")
            
            print(f"\n💾 正在保存用户信息到搜索目录...")
            if self.save_user_info_to_search_dir(user_info):
                print(f"✅ 用户信息已保存到搜索目录: {self.search_dir}/")
        else:
            print(f"❌ 未找到用户ID: {user_id}")

    def save_user_info_to_search_dir(self, user_info):
        try:
            os.makedirs(self.search_dir, exist_ok=True)
            
            user_id = user_info['id']
            username = user_info.get('name', f"用户_{user_id}")
            
            safe_name = INVALID_CHARS.sub("_", username)[:20] if username else f"用户_{user_id}"
            filename = f"{user_id}_{safe_name}.txt"
            filepath = os.path.join(self.search_dir, filename)
            
            post_text = f"{'='*60}\n🔍 用户搜索结果档案\n{'='*60}\n"
            post_text += f"👤 用户ID: {user_id}\n"
            post_text += f"📛 用户名: {username}\n"
            
            if user_info.get('nick_name'):
                post_text += f"🏷️  昵称: {user_info['nick_name']}\n"
            
            if user_info.get('age') and user_info['age'] != "未知":
                post_text += f"🎂 年龄: {user_info['age']}岁\n"
            if user_info.get('birthday') and user_info['birthday'] != "未知":
                post_text += f"📅 生日: {user_info['birthday']}\n"
            
            if user_info.get('sex_text') and user_info['sex_text'] != "未知":
                post_text += f"⚧️ 性别: {user_info['sex_text']}\n"
            if user_info.get('sex_o_text') and user_info['sex_o_text'] != "未知":
                post_text += f"💝 性取向: {user_info['sex_o_text']}\n"
            if user_info.get('sex_p_text') and user_info['sex_p_text'] != "未知":
                post_text += f"🎭 角色: {user_info['sex_p_text']}\n"
                
            if user_info.get('height'):
                post_text += f"📏 身高: {user_info['height']}cm\n"
            if user_info.get('weight'):
                post_text += f"⚖️ 体重: {user_info['weight']}kg\n"
            
            if user_info.get('country'):
                post_text += f"📍 地区: {user_info['country']}\n"
            
            if user_info.get('last_time'):
                post_text += f"⏰ 最后在线: {user_info['last_time']}\n"
            
            post_text += f"🔗 用户链接: {user_info.get('user_url', '')}\n"
            post_text += f"📅 搜索时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            post_text += f"{'='*60}\n"
            
            post_text += f"\n📝 带中文注释的完整JSON数据:\n"
            post_text += "-" * 60 + "\n"
            
            try:
                r = requests.post(
                    f"{self.base_url}/api.php/user/show",
                    headers=self.headers,
                    json={"id": user_id},
                    timeout=10
                )
                data = r.json()
                
                if data.get("code") == 1 and data.get("data"):
                    user_raw_data = data["data"]
                    
                    full_data = {
                        "_query_info": {
                            "query_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "query_timestamp": int(time.time()),
                            "user_id": user_id,
                            "query_type": "用户信息查询"
                        },
                        "_note": "字段后的//注释为中文翻译",
                        "api_response": data
                    }
                    
                    formatted_json = self.format_json_with_comments(full_data)
                    post_text += formatted_json
                    post_text += f"\n{'='*60}\n"
                    post_text += f"💾 完整数据保存时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                else:
                    post_text += f"⚠️  无法获取用户完整JSON数据\n"
                    post_text += f"{'='*60}\n"
                    
            except Exception as e:
                post_text += f"❌ 获取用户完整数据失败: {e}\n"
                post_text += f"{'='*60}\n"
            
            post_text += f"📁 文件位置: {filepath}\n"
            post_text += "=" * 60
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(post_text)
            
            print(f"✅ 用户信息已保存到: {filepath}")
            return True
        except Exception as e:
            print(f"❌ 保存用户信息失败: {e}")
            return False

    def get_posts(self, page=None, limit=20, keyword=""):
        payload = self.payload_template.copy()
        payload["page"] = page if page else self.current_page
        try:
            r = requests.post(f"{self.base_url}/api.php/circle/list",
                              headers=self.headers, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    posts = data.get("data", {}).get("data", [])
                    info = data.get("data", {})
                    self.has_more = len(posts) >= info.get("per_page", len(posts))
                    return {"success": True, "page": self.current_page, "data": posts, "raw_data": data}
                return {"success": False, "error": data.get("msg", "未知错误")}
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_next_page(self):
        if not self.has_more:
            print("没有更多数据了")
            return None
        result = self.get_posts(page=self.current_page)
        if result["success"]:
            self.current_page += 1
        return result

    def reset_pagination(self):
        self.current_page = 1
        self.has_more = True

    def get_post_detail(self, post_id: int) -> Optional[Dict]:
        try:
            r = requests.post(f"{self.base_url}/api.php/circle/show",
                              headers=self.headers, json={"id": post_id}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1 and data.get("data"):
                    post_data = data["data"]
                    
                    user_id = post_data.get("user_id")
                    if user_id:
                        user_info = self.get_complete_user_info(user_id)
                        if user_info:
                            post_data["user"] = {
                                "id": user_id,
                                "user_name": user_info["name"],
                                "nick_name": user_info.get("nick_name", ""),
                                "age": user_info["age"],
                                "birthday": user_info["birthday"],
                                "sex_text": user_info["sex_text"],
                                "sex_o_text": user_info["sex_o_text"],
                                "sex_p_text": user_info["sex_p_text"],
                                "country": user_info["country"],
                                "country_pic": user_info.get("country_pic", ""),
                                "height": user_info.get("height", ""),
                                "weight": user_info.get("weight", ""),
                                "last_time": user_info.get("last_time", ""),
                                "intro": user_info.get("intro", ""),
                                "pic": user_info.get("country_pic", "")
                            }
                        else:
                            post_data["user"] = {
                                "id": user_id,
                                "user_name": f"用户_{user_id}"
                            }
                    
                    return post_data
        except:
            pass
        return None

    def search_posts_with_page(self, keyword, page=1):
        payload = self.payload_template.copy()
        payload["kw"] = keyword
        payload["page"] = page
        
        try:
            r = requests.post(f"{self.base_url}/api.php/circle/list",
                              headers=self.headers, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    posts = data.get("data", {}).get("data", [])
                    return {"success": True, "page": page, "data": posts, "raw_data": data}
                return {"success": False, "error": data.get("msg", "未知错误")}
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_user_posts(self, user_id: int, page: int = 1):
        payload = {
            "page": page, "order": {"create_time": "desc"}, "kw": "",
            "append": self.payload_template["append"],
            "with_count": ["comments", "favos", "digs"],
            "user_id": user_id
        }
        try:
            r = requests.post(f"{self.base_url}/api.php/circle/list",
                              headers=self.headers, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    posts = data.get("data", {}).get("data", [])
                    total_posts = data.get("data", {}).get("total", 0)
                    per_page = data.get("data", {}).get("per_page", 20)
                    has_more = len(posts) >= per_page
                    
                    return {
                        "success": True, 
                        "page": page, 
                        "data": posts, 
                        "total": total_posts,
                        "per_page": per_page,
                        "has_more": has_more,
                        "raw_data": data
                    }
                return {"success": False, "error": data.get("msg", "未知错误")}
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def crawl_user_posts(self, user_id: int):
        print(f"\n🎯 爬取用户 {user_id} 的全部帖子")
        
        user_info = self.get_complete_user_info(user_id)
        if user_info:
            print(f"\n👤 用户信息:")
            self.display_complete_user_info(user_info, prefix="   ")
        
        try:
            page_input = input("请输入搜索页数 (默认1页): ").strip()
            if not page_input:
                max_pages = 1
            else:
                max_pages = int(page_input)
                max_pages = max(1, min(5000, max_pages))
        except:
            max_pages = 1
            print(f"⚠️  输入无效，使用默认页数: {max_pages}")
        
        all_posts = []
        page = 1
        total_saved = 0
        actual_pages_crawled = 0
        
        print(f"\n📥 开始获取用户 {user_id} 的帖子...")
        print(f"📄 计划爬取: {max_pages} 页")
        
        while page <= max_pages:
            print(f"\n📄 正在获取第 {page}/{max_pages} 页...")
            result = self.get_user_posts(user_id, page)
            
            if not result["success"]:
                print(f"❌ 第 {page} 页获取失败: {result.get('error', '未知错误')}")
                break
                
            posts = result["data"]
            actual_pages_crawled += 1
            
            if not posts:
                print(f"📭 第 {page} 页没有数据，停止爬取")
                break
                
            print(f"✅ 第 {page} 页获取到 {len(posts)} 个帖子")
            all_posts.extend(posts)
            
            print(f"\n📋 第 {page} 页帖子列表:")
            print("=" * 50)
            
            for i, post in enumerate(posts, 1):
                self.display_post_for_browsing(post, index=i)
            
            if posts:
                print("\n" + "=" * 50)
                save_choice = input(f"是否保存第 {page} 页的所有帖子？(y/n/s=选择保存): ").strip().lower()
                
                if save_choice == 'y':
                    page_saved = 0
                    for i, post in enumerate(posts, 1):
                        if self.save_post_for_user_crawl(post, user_info, manual_mode=False, index=i):
                            page_saved += 1
                            total_saved += 1
                        time.sleep(0.5)
                    print(f"✅ 第 {page} 页保存了 {page_saved}/{len(posts)} 个帖子")
                    
                elif save_choice == 's':
                    print("\n🔍 请选择要保存的帖子:")
                    selected = input(f"输入第 {page} 页的帖子编号（用逗号分隔，如 1,3,5）: ").strip()
                    
                    if selected:
                        try:
                            indices = [int(idx.strip()) - 1 for idx in selected.split(',') if idx.strip().isdigit()]
                            page_saved = 0
                            for idx in indices:
                                if 0 <= idx < len(posts):
                                    if self.save_post_for_user_crawl(posts[idx], user_info, manual_mode=True):
                                        page_saved += 1
                                        total_saved += 1
                                    time.sleep(0.5)
                            print(f"✅ 第 {page} 页保存了 {page_saved}/{len(indices)} 个帖子")
                        except:
                            print("❌ 输入格式错误")
                
                else:
                    print(f"⏭️  跳过第 {page} 页保存")
            
            if not result.get("has_more", False):
                print("📭 最后一页，停止爬取")
                break
                
            page += 1
            
            if page <= max_pages:
                continue_choice = input(f"\n是否继续爬取第 {page} 页？(y/n): ").strip().lower()
                if continue_choice != 'y':
                    print("⏹️  停止爬取")
                    break
                time.sleep(1)
        
        if all_posts:
            print(f"\n{'='*50}")
            print("🎉 用户帖子爬取完成！")
            print("=" * 50)
            print(f"📊 统计:")
            print(f"  实际爬取页数: {actual_pages_crawled}/{max_pages}")
            print(f"  找到帖子总数: {len(all_posts)}")
            print(f"  保存帖子总数: {total_saved}")
            if all_posts:
                save_rate = (total_saved / len(all_posts)) * 100
                print(f"  保存率: {save_rate:.1f}%")
            
            print(f"💾 数据保存在: {self.users_dir}/")
        else:
            print(f"\n❌ 未获取到用户 {user_id} 的帖子")

    def crawl_specific_post(self, post_id: int):
        print(f"\n🎯 爬取特定帖子: {post_id}")
        detail = self.get_post_detail(post_id)
        
        if not detail:
            print(f"❌ 未找到帖子 {post_id}")
            return
        
        print(f"\n📄 帖子详情:")
        self.display_post_for_browsing(detail, index=1)
        
        user_info = detail.get("user", {})
        user_id = user_info.get("id") or detail.get("user_id")
        
        save_choice = input("是否保存此帖子？(y/n): ").strip().lower()
        if save_choice == 'y':
            if user_id:
                complete_user_info = self.get_complete_user_info(user_id)
                if complete_user_info:
                    save_success = self.save_post_for_user_crawl(detail, complete_user_info, manual_mode=True, index=1)
                    if save_success:
                        print(f"\n✅ 帖子 {post_id} 爬取并保存完成")
                    else:
                        print(f"\n⚠️  帖子 {post_id} 爬取完成但保存失败")
                else:
                    print(f"❌ 无法获取用户 {user_id} 的完整信息")
            else:
                print(f"❌ 无法获取用户ID")
        else:
            print(f"⏭️  跳过保存帖子 {post_id}")

    def save_post_for_user_crawl(self, post_data: Dict, user_info: Dict, manual_mode: bool = False, index: int = None):
        try:
            post_id = post_data.get("id")

            if user_info is None:
                user_info = {}
            elif isinstance(user_info, list):
                user_info = user_info[0] if user_info else {}

            user_id = user_info.get("id") if isinstance(user_info, dict) else None
            if not user_id:
                user_id = post_data.get("user_id")

            if not user_id:
                print(f"帖子 {post_id} 缺少用户ID")
                return False

            username = ""
            if isinstance(user_info, dict):
                username = user_info.get("user_name") or user_info.get("name") or f"用户_{user_id}"
            else:
                username = f"用户_{user_id}"
            
            safe_name = INVALID_CHARS.sub("_", username)[:20] if username else f"用户_{user_id}"
            filename = f"{user_id}_{safe_name}.txt"
            filepath = os.path.join(self.users_dir, filename)
            
            file_exists = os.path.exists(filepath)
            
            if not file_exists:
                archive_text = self.format_user_archive_text(user_info)
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(archive_text)
            
            content = post_data.get("content") or post_data.get("title") or "无内容"
            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(post_data.get("create_time", 0)))
            
            post_text = f"\n【帖子 #{post_id}】\n"
            if index is not None:
                post_text += f"序号: [{index}]\n"
            post_text += f"内容: {content}\n"
            post_text += f"发布时间: {create_time}\n"
            post_text += f"浏览量: {post_data.get('onclick', 0)}\n"
            post_text += f"点赞数: {post_data.get('dig_count', 0)}\n"
            post_text += f"评论数: {post_data.get('com_count', 0)}\n"
            
            files = post_data.get("files")
            if isinstance(files, list) and files:
                post_text += f"图片数量: {len(files)}\n"
                post_text += "图片链接:\n"
                for i, f in enumerate(files, 1):
                    if isinstance(f, dict):
                        post_text += f"{i}. {f.get('url', '')}\n"
                    else:
                        post_text += f"{i}. {f}\n"
            else:
                post_text += f"图片数量: 0\n"
            
            post_text += f"{'-'*40}\n"
            
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(post_text)
            
            if manual_mode:
                if index is not None:
                    print(f"✅ 帖子 [{index}] 已保存到用户 {user_id} 的文件\n💾 文件位置: {filepath}")
                else:
                    print(f"✅ 帖子 {post_id} 已保存到用户 {user_id} 的文件\n💾 文件位置: {filepath}")
            else:
                if index is not None:
                    print(f"✅ 帖子 [{index}] 已保存")
                else:
                    print(f"✅ 帖子 {post_id} 已保存")
            
            return True
        except Exception as e:
            print(f"❌ 保存帖子失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def extract_post_info(self, post_data: Dict) -> Dict:
        post_id = post_data.get("id")
        user_info = post_data.get("user", {})
        user_id = user_info.get("id") or post_data.get("user_id")
        
        complete_user_info = None
        if user_id:
            complete_user_info = self.get_complete_user_info(user_id)
        
        user_data = complete_user_info if complete_user_info else user_info
        
        info = {
            "帖子ID": post_id,
            "内容": post_data.get("title"),
            "发布时间": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(post_data.get("create_time", 0))),
            "浏览量": post_data.get("onclick", 0),
            "点赞数": post_data.get("dig_count", 0),
            "评论数": post_data.get("com_count", 0),
            "来源": post_data.get("source", "API")
        }
        
        info["用户"] = {
            "用户ID": user_id,
            "用户名": user_data.get("user_name") or user_data.get("name") or f"用户_{user_id}",
            "昵称": user_data.get("nick_name", ""),
            "年龄": user_data.get("age", ""),
            "生日": user_data.get("birthday", ""),
            "性别": user_data.get("sex_text", ""),
            "性取向": user_data.get("sex_o_text", ""),
            "角色": user_data.get("sex_p_text", ""),
            "地区": user_data.get("country", ""),
            "身高": user_data.get("height", ""),
            "体重": user_data.get("weight", ""),
            "最后在线": user_data.get("last_time", ""),
            "个人简介": user_data.get("intro", "")
        }
        
        files = post_data.get("files", [])
        if files:
            info["图片数量"] = len(files)
        return info

    def show_user_files(self):
        if not os.path.exists(self.users_dir):
            print("❌ 还没有保存任何文件")
            return
        
        all_files = [f for f in os.listdir(self.users_dir) if f.endswith('.txt')]
        
        if not all_files:
            print("❌ 帖子目录为空")
            return
        
        print(f"\n📁 帖子文件 ({len(all_files)} 个):")
        print("=" * 50)
        
        for filename in sorted(all_files):
            filepath = os.path.join(self.users_dir, filename)
            size = os.path.getsize(filepath)
            user_id = filename.split('_')[0] if '_' in filename else filename.replace('.txt', '')
            
            with open(filepath, encoding='utf-8') as f:
                content = f.read()
                post_cnt = content.count("【帖子 #")
            
            print(f"📄 {filename} ({size/1024:.1f} KB) | 🆔 {user_id} | 📝 {post_cnt} 帖")
        print("=" * 50)

    def manual_browse_posts(self):
        print("\n🔍 手动浏览模式（按回车继续，y=保存当前帖，q=退出到主菜单）")
        print("提示：按回车键浏览下一个帖子，按y保存当前帖子，按q退出")
        
        self.reset_pagination()
        total_saved = 0
        total_viewed = 0
        start_time = time.time()
        
        while True:
            print(f"\n📄 当前页码: {self.current_page}")
            result = self.get_next_page()
            
            if not result or not result.get("success"):
                print("❌ 获取数据失败或没有更多数据")
                break
            
            posts = result.get("data", [])
            if not posts:
                print("📭 没有数据")
                break
            
            print(f"✅ 获取到 {len(posts)} 个帖子")
            total_viewed += len(posts)
            
            for i, post in enumerate(posts, 1):
                self.display_post_for_browsing(post, index=i)
                
                print("   [回车=继续] [y=保存] [q=退出]")
                save_choice = input("   请选择: ").strip().lower()
                
                if save_choice == 'q':
                    print(f"⏹️  退出到主菜单")
                    elapsed = time.time() - start_time
                    print(f"\n📊 浏览统计:")
                    print(f"  查看页数: {self.current_page}")
                    print(f"  查看帖子: {total_viewed}")
                    print(f"  保存帖子: {total_saved}")
                    print(f"  耗时: {elapsed:.1f}秒")
                    return
                elif save_choice == 'y':
                    user_info = post.get("user", {})
                    user_id = user_info.get('id') or post.get('user_id')
                    if user_id:
                        complete_user_info = self.get_complete_user_info(user_id)
                        if complete_user_info:
                            success = self.save_post_for_user_crawl(post, complete_user_info, manual_mode=True, index=i)
                            if success:
                                total_saved += 1
                                print(f"✅ 帖子 [{i}] 已保存")
                            else:
                                print(f"❌ 帖子 [{i}] 保存失败")
                        else:
                            print(f"❌ 无法获取用户 {user_id} 的完整信息")
                    else:
                        print(f"❌ 无法获取用户ID")
                else:
                    print(f"⏭️  继续浏览...")
            
            print(f"\n第 {self.current_page} 页浏览完成")
            print(f"本页统计: 查看{len(posts)}帖 | 保存{total_saved}帖")
            
            user_input = input("\n是否继续下一页？(回车继续/q退出到主菜单): ").strip().lower()
            if user_input == 'q':
                print(f"⏹️  退出到主菜单")
                break
        
        elapsed = time.time() - start_time
        print(f"\n📊 浏览统计:")
        print(f"  浏览页数: {self.current_page}")
        print(f"  查看帖子: {total_viewed}")
        print(f"  保存帖子: {total_saved}")
        print(f"  耗时: {elapsed:.1f}秒")

    def search_and_save_posts(self):
        print("\n🔍 搜索帖子功能")
        print("=" * 40)
        
        keyword = input("请输入搜索关键词: ").strip()
        if not keyword:
            print("❌ 请输入搜索关键词")
            return
        
        try:
            page_input = input("请输入搜索页数 (默认1页): ").strip()
            if not page_input:
                max_pages = 1
            else:
                max_pages = int(page_input)
                max_pages = max(1, min(500, max_pages))
        except:
            max_pages = 1
            print("⚠️  输入无效，使用默认1页")
        
        saver = ResultSaver(self.search_dir, f"帖子搜索_{keyword}", f"第1页", f"第{max_pages}页")
        
        all_posts = []
        total_saved = 0
        start_time = time.time()
        
        for page in range(1, max_pages + 1):
            print(f"\n📄 正在搜索第 {page} 页...")
            result = self.search_posts_with_page(keyword, page)
            
            if not result or not result.get("success"):
                print(f"❌ 第 {page} 页搜索失败: {result.get('error', '未知错误')}")
                saver.save_record(f"第{page}页", "❌", f"搜索失败: {result.get('error', '未知错误')}")
                break
                
            posts = result.get("data", [])
            if not posts:
                print(f"📭 第 {page} 页没有找到相关帖子")
                saver.save_record(f"第{page}页", "📭", "没有找到相关帖子")
                if page == 1:
                    break
                else:
                    break
            
            print(f"✅ 第 {page} 页找到 {len(posts)} 个相关帖子")
            saver.save_record(f"第{page}页", "✅", f"找到{len(posts)}个帖子")
            all_posts.extend(posts)
            
            print(f"\n📋 第 {page} 页搜索结果:")
            print("=" * 50)
            
            for i, post in enumerate(posts, 1):
                self.display_post_for_browsing(post, index=i)
            
            if posts:
                print("\n" + "=" * 50)
                save_choice = input(f"是否保存第 {page} 页的所有搜索结果？(y/n/s=选择保存): ").strip().lower()
                
                if save_choice == 'y':
                    page_saved = 0
                    for post in posts:
                        user_info = post.get("user", {})
                        user_id = user_info.get("id") or post.get("user_id")
                        if user_id:
                            complete_user_info = self.get_complete_user_info(user_id)
                            if complete_user_info:
                                if self.save_post_for_user_crawl(post, complete_user_info, manual_mode=False):
                                    page_saved += 1
                                    saver.save_record(f"帖子{post.get('id')}", "✅", "自动保存")
                                else:
                                    saver.save_record(f"帖子{post.get('id')}", "❌", "保存失败")
                            else:
                                saver.save_record(f"帖子{post.get('id')}", "❌", "无法获取用户信息")
                        time.sleep(0.3)
                    total_saved += page_saved
                    print(f"✅ 第 {page} 页保存了 {page_saved}/{len(posts)} 个帖子")
                    saver.save_record(f"第{page}页", "📊", f"保存{page_saved}/{len(posts)}个帖子")
                
                elif save_choice == 's':
                    print("\n🔍 请选择要保存的帖子:")
                    selected = input(f"输入第 {page} 页的帖子编号（用逗号分隔，如 1,3,5）: ").strip()
                    
                    if selected:
                        try:
                            indices = [int(idx.strip()) - 1 for idx in selected.split(',') if idx.strip().isdigit()]
                            page_saved = 0
                            for idx in indices:
                                if 0 <= idx < len(posts):
                                    user_info = posts[idx].get("user", {})
                                    user_id = user_info.get("id") or posts[idx].get("user_id")
                                    if user_id:
                                        complete_user_info = self.get_complete_user_info(user_id)
                                        if complete_user_info:
                                            if self.save_post_for_user_crawl(posts[idx], complete_user_info, manual_mode=True):
                                                page_saved += 1
                                                saver.save_record(f"帖子{posts[idx].get('id')}", "✅", "手动选择保存")
                                    time.sleep(0.5)
                            total_saved += page_saved
                            print(f"✅ 第 {page} 页保存了 {page_saved}/{len(indices)} 个帖子")
                            saver.save_record(f"第{page}页", "📊", f"手动选择保存{page_saved}/{len(indices)}个帖子")
                        except:
                            print("❌ 输入格式错误")
                            saver.save_record(f"第{page}页", "❌", "输入格式错误")
                
                if page < max_pages:
                    continue_choice = input(f"\n是否继续搜索第 {page+1} 页？(y/n): ").strip().lower()
                    if continue_choice != 'y':
                        print("⏹️  停止搜索")
                        break
            else:
                saver.save_record(f"第{page}页", "📭", "本页无帖子可保存")
        
        elapsed = time.time() - start_time
        print(f"\n" + "=" * 50)
        print("🔍 搜索完成！")
        print("=" * 50)
        print(f"📊 统计:")
        print(f"  总搜索页数: {min(page, max_pages)}/{max_pages}")
        print(f"  找到帖子总数: {len(all_posts)}")
        print(f"  保存帖子总数: {total_saved}")
        if all_posts:
            save_rate = (total_saved / len(all_posts)) * 100
            print(f"  保存率: {save_rate:.1f}%")
        
        extra_stats = {
            "搜索关键词": keyword,
            "实际搜索页数": f"{min(page, max_pages)}/{max_pages}",
            "找到帖子数": len(all_posts),
            "保存帖子数": total_saved,
            "保存率": f"{save_rate:.1f}%" if all_posts else "0%"
        }
        saver.finalize(total_saved, len(all_posts)-total_saved, len(all_posts), elapsed, extra_stats)
        print(f"📋 搜索记录已保存: {saver.filepath}")

    def crawl_and_save_posts(self, start_page=1, max_pages=3):
        print(f"\n🎯 开始批量爬取：从第{start_page}页开始，共{max_pages}页")
        
        saver = ResultSaver(self.search_dir, f"批量爬取", f"第{start_page}页", f"第{start_page+max_pages-1}页")
        
        self.current_page = start_page
        saved_count = 0
        total_posts = 0
        start_time = time.time()
        
        for page_num in range(start_page, start_page + max_pages):
            print(f"\n📄 正在爬取第 {page_num} 页...")
            result = self.get_posts(page=page_num)
            
            if not result["success"]:
                print(f"❌ 第 {page_num} 页获取失败: {result.get('error', '未知错误')}")
                saver.save_record(f"第{page_num}页", "❌", f"获取失败: {result.get('error', '未知错误')}")
                break
                
            posts = result.get("data", [])
            if not posts:
                print(f"📭 第 {page_num} 页没有数据")
                saver.save_record(f"第{page_num}页", "📭", "没有数据")
                break
                
            print(f"✅ 获取到 {len(posts)} 个帖子")
            total_posts += len(posts)
            
            print(f"\n📋 第 {page_num} 页帖子:")
            print("-" * 50)
            
            for i, post in enumerate(posts[:5], 1):
                self.display_post_for_browsing(post, index=i)
            if len(posts) > 5:
                print(f"   ... 还有 {len(posts)-5} 个帖子")
            
            print("=" * 50)
            
        page_saved = 0
        for i, post in enumerate(posts, 1):
            user_info = post.get("user", {})
            user_id = user_info.get("id") or post.get("user_id")
            if user_id:
                complete_user_info = self.get_complete_user_info(user_id)
                if complete_user_info:
                    success = self.save_post_for_user_crawl(post, complete_user_info, manual_mode=False, index=i)
                    if success:
                        page_saved += 1
                        saved_count += 1
            time.sleep(0.3)
            
            print(f"📝 第 {page_num} 页保存了 {page_saved}/{len(posts)} 个帖子")
            saver.save_record(f"第{page_num}页", "📊", f"保存{page_saved}/{len(posts)}个帖子")
            
            if page_num < start_page + max_pages - 1:
                time.sleep(2)
        
        elapsed = time.time() - start_time
        print(f"\n🎉 批量爬取完成！")
        print(f"📊 总计:")
        print(f"  爬取页数: {page_num - start_page + 1}")
        print(f"  获取帖子: {total_posts}")
        print(f"  保存帖子: {saved_count}")
        print(f"  耗时: {elapsed:.1f}秒")
        print(f"💾 数据保存在: {self.users_dir}/")
        
        extra_stats = {
            "实际爬取页数": f"{page_num - start_page + 1}/{max_pages}",
            "获取帖子数": total_posts,
            "保存帖子数": saved_count,
            "保存率": f"{(saved_count/total_posts*100):.1f}%" if total_posts > 0 else "0%"
        }
        saver.finalize(saved_count, total_posts-saved_count, total_posts, elapsed, extra_stats)
        print(f"📋 批量爬取记录已保存: {saver.filepath}")

    def vote_check(self, task_id: int):
        url = f"{self.base_url}/api.php/play/pds"
        try:
            r = requests.post(url, headers=self.headers, json={"id": str(task_id)}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                return data.get("code") == 1, data.get("msg", ""), data.get("code", 0), data.get("data", "")
            return False, "HTTP 非 200", r.status_code, ""
        except Exception as e:
            return False, f"请求异常: {str(e)}", 0, ""

    def vote_do(self, task_id: int):
        url = f"{self.base_url}/api.php/play/pd_do"
        try:
            r = requests.post(url, headers=self.headers, json={"id": task_id, "type": 1}, timeout=5)
            if r.status_code == 200:
                data = r.json()
                code = data.get("code")
                msg = data.get("msg", "")
                
                if code == 1:
                    return True, "投票成功", code, msg, data.get("data", "")
                elif code == 0 and ("已投" in msg or "重复" in msg or "投过" in msg):
                    return True, "已投过票", code, msg, data.get("data", "")
                else:
                    return False, "投票失败", code, msg, data.get("data", "")
            return False, "HTTP 非 200", r.status_code, "", ""
        except Exception as e:
            return False, f"请求异常: {str(e)}", 0, "", ""

    def vote_single_test(self, task_id: int):
        print(f"\n🧪 测试投票任务: {task_id}")
        
        saver = ResultSaver(self.votes_dir, f"单任务投票测试", f"任务ID{task_id}")
        
        valid, status, code, data = self.vote_check(task_id)
        print(f"检查: {status} (code={code})")
        saver.save_record(f"检查任务{task_id}", "✅" if valid else "❌", f"{status} (code={code})")
        
        if valid and input("确认投票？(y/n): ").lower() == 'y':
            success, vote_status, vote_code, vote_msg, vote_data = self.vote_do(task_id)
            print(f"投票: {vote_status} (code={vote_code}, msg={vote_msg}, data={vote_data})")
            saver.save_record(f"投票任务{task_id}", "✅" if success else "❌", 
                            f"{vote_status} (code={vote_code}, msg={vote_msg})")
        else:
            saver.save_record(f"投票任务{task_id}", "⏹️", "用户取消投票")

        saver.finalize(1 if valid else 0, 0, 1, 0)
        print(f"📋 投票测试记录已保存: {saver.filepath}")

    def vote_single_gui(self, task_id: int):
        print(f"\n[单任务投票] 任务ID: {task_id}")
        print("=" * 50)

        print(f"[检查] 任务 {task_id} 状态...")
        url_check = f"{self.base_url}/api.php/play/pds"
        try:
            r_check = requests.post(url_check, headers=self.headers, json={"id": str(task_id)}, timeout=5)
            if r_check.status_code == 200:
                check_data = r_check.json()
                json_str = json.dumps(check_data, ensure_ascii=False, indent=2)
                if len(json_str) > 2000:
                    json_str = json_str[:2000] + "\n... (内容过长已截断)"
                print(f"\n[检查响应]:\n{json_str}")

                if check_data.get("code") != 1:
                    print(f"\n[失败] 任务无效: {check_data.get('msg', '未知错误')}")
                    return
                print(f"\n[通过] 任务有效，开始投票...")
            else:
                print(f"[失败] 检查请求失败: HTTP {r_check.status_code}")
                return
        except Exception as e:
            print(f"[异常] 检查请求异常: {e}")
            return

        url_vote = f"{self.base_url}/api.php/play/pd_do"
        try:
            r_vote = requests.post(url_vote, headers=self.headers, json={"id": task_id, "type": 1}, timeout=5)
            if r_vote.status_code == 200:
                vote_data = r_vote.json()
                json_str = json.dumps(vote_data, ensure_ascii=False, indent=2)
                if len(json_str) > 2000:
                    json_str = json_str[:2000] + "\n... (内容过长已截断)"
                print(f"\n[投票响应]:\n{json_str}")

                code = vote_data.get("code")
                msg = vote_data.get("msg", "")

                if code == 1:
                    print(f"\n[成功] 投票成功: {msg}")
                elif code == 0 and ("已投" in msg or "重复" in msg or "投过" in msg):
                    print(f"\n[提示] 已投过票: {msg}")
                else:
                    print(f"\n[失败] 投票失败: {msg}")
            else:
                print(f"[失败] 投票请求失败: HTTP {r_vote.status_code}")
        except Exception as e:
            print(f"[异常] 投票请求异常: {e}")

        print("=" * 50)

    def batch_vote(self):
        print("\n" + "="*60)
        print("🚀 批量投票")
        print("="*60)
        print("📋 说明: 只保存有效投票（成功和已投过票）到文件")
        print(f"💾 投票文件将保存到: {self.votes_dir}")
        print("="*60)
        
        try:
            start = int(input("起始ID: "))
            end = int(input("结束ID: "))
            if start > end: 
                start, end = end, start
                print(f"⚠️  已调整为: {start} 到 {end}")
        except:
            print("❌ 输入错误")
            return
        
        task_ids = list(range(start, end + 1))
        check_first = input("\n是否先检查任务有效性？(y/n，建议y): ").strip().lower() == 'y'
        
        try:
            recommended_threads = 100
            print(f"\n⚡ 推荐: {recommended_threads} 线程")
            threads = int(input(f"设置线程数 (推荐{recommended_threads}, 最大500): ").strip() or str(recommended_threads))
            threads = max(10, min(500, threads))
        except:
            threads = recommended_threads
        
        print(f"\n⚡ 使用 {threads} 线程")
        print(f"🎯 将投票 {len(task_ids)} 个任务 (ID: {start} 到 {end})")
        print(f"💾 结果保存到: {self.votes_dir}")
        
        if input("\n确定开始？(y/n): ").strip().lower() != 'y':
            print("❌ 已取消")
            return
        
        saver = ResultSaver(self.votes_dir, f"批量投票", f"ID{start}", f"ID{end}")
        
        results = {}
        results_lock = threading.Lock()
        output_order = list(range(start, end + 1))
        next_output_idx = 0
        output_lock = threading.Lock()
        output_buffer = {}
        success_count = 0
        already_count = 0
        failed_count = 0
        success_ids = []
        already_ids = []
        start_time = time.time()
        
        def flush_output():
            nonlocal next_output_idx, success_count, already_count, failed_count, success_ids, already_ids
            
            while next_output_idx < len(output_order):
                task_id = output_order[next_output_idx]
                if task_id in output_buffer:
                    result_type, code, msg, data = output_buffer[task_id]
                    
                    if result_type == "success":
                        success_count += 1
                        success_ids.append(task_id)
                    elif result_type == "already":
                        already_count += 1
                        already_ids.append(task_id)
                    else:
                        failed_count += 1
                    
                    if result_type == "success":
                        status_icon = "✅"
                        status_text = "成功"
                    elif result_type == "already":
                        status_icon = "🔄"
                        status_text = "已投"
                    else:
                        status_icon = "❌"
                        status_text = "失败"
                    
                    display_msg = f"{msg}"
                    if data and data != "":
                        if isinstance(data, dict):
                            data_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                            if len(data_str) > 30:
                                data_str = data_str[:30] + "..."
                            display_msg += f" data={data_str}"
                        else:
                            data_str = str(data)
                            if len(data_str) > 30:
                                data_str = data_str[:30] + "..."
                            display_msg += f" data={data_str}"
                    
                    completed = next_output_idx + 1
                    total_tasks = len(task_ids)
                    elapsed = time.time() - start_time
                    speed = completed / elapsed if elapsed > 0 else 0
                    
                    stats_info = f"✅{success_count} 🔄{already_count} ❌{failed_count} ⚡{speed:.1f}/s"
                    print(f"ID:{task_id} {status_icon}{status_text} code={code} {display_msg} | {stats_info}")
                    
                    if result_type == "success":
                        saver.save_record(f"任务{task_id}", "✅", f"投票成功: {msg}")
                    elif result_type == "already":
                        saver.save_record(f"任务{task_id}", "🔄", f"已投过票: {msg}")
                    else:
                        saver.save_record(f"任务{task_id}", "❌", f"投票失败: {msg}")
                    
                    del output_buffer[task_id]
                    next_output_idx += 1
                else:
                    break
        
        def process_task(task_id):
            result_type = "failed"
            code, msg, data = 0, "未知错误", ""
            
            try:
                if check_first:
                    valid, _, check_code, check_msg, check_data = self.vote_check(task_id)
                    if not valid:
                        result_type, code, msg, data = "failed", check_code, check_msg, check_data
                        
                        with output_lock:
                            output_buffer[task_id] = (result_type, code, msg, data)
                            flush_output()
                        
                        with results_lock:
                            results[task_id] = (result_type, code, msg, data)
                        return
                
                success, status, vote_code, vote_msg, vote_data = self.vote_do(task_id)
                
                if success:
                    if vote_code == 1:
                        result_type = "success"
                    else:
                        result_type = "already"
                    
                    code, msg, data = vote_code, vote_msg, vote_data
                else:
                    result_type = "failed"
                    code, msg, data = vote_code, vote_msg, vote_data
                    
            except Exception as e:
                result_type, msg = "failed", "处理异常"
                code, data = 0, ""
            
            with output_lock:
                output_buffer[task_id] = (result_type, code, msg, data)
                flush_output()
            
            with results_lock:
                results[task_id] = (result_type, code, msg, data)
        
        print("\n" + "="*50)
        print("🚀 开始投票...")
        print(f"💾 文件将保存到: {self.votes_dir}")
        print("="*50)
        
        try:
            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = [executor.submit(process_task, task_id) for task_id in task_ids]
                for future in as_completed(futures):
                    pass
        except Exception as e:
            print(f"\n❌ 线程池异常: {e}")
        
        elapsed = time.time() - start_time
        speed = len(task_ids) / elapsed if elapsed > 0 else 0
        
        print(f"\n" + "="*60)
        print("🎯 投票完成！")
        print("="*60)
        print(f"📊 统计:")
        print(f"  总任务: {len(task_ids)}")
        print(f"  ✅ 成功: {success_count}")
        print(f"  🔄 已投: {already_count}")
        print(f"  ❌ 失败: {failed_count}")
        
        if success_ids:
            print(f"\n✅ 成功ID ({len(success_ids)}个):")
            for i in range(0, len(success_ids), 10):
                ids_line = success_ids[i:i+10]
                print(f"  {', '.join(map(str, ids_line))}")
        
        if already_ids:
            print(f"\n🔄 已投ID ({len(already_ids)}个):")
            for i in range(0, len(already_ids), 10):
                ids_line = already_ids[i:i+10]
                print(f"  {', '.join(map(str, ids_line))}")
        
        if len(task_ids) > 0:
            success_rate = (success_count + already_count) / len(task_ids) * 100
            print(f"\n📈 有效率: {success_rate:.1f}%")
        
        print(f"\n⏱️ 耗时: {elapsed:.1f}秒")
        print(f"⚡ 速度: {speed:.1f}任务/秒")
        
        extra_stats = {
            "成功投票数": success_count,
            "已投过票数": already_count,
            "投票失败数": failed_count,
            "有效成功率": f"{success_rate:.1f}%",
            "平均速度": f"{speed:.1f}任务/秒"
        }
        saver.finalize(success_count + already_count, failed_count, len(task_ids), elapsed, extra_stats)
        print(f"\n💾 结果已保存: {saver.filepath}")
        print(f"📁 查看所有投票文件: 选择菜单选项 10")

    def show_vote_files(self):
        if not os.path.exists(self.votes_dir):
            print("❌ 还没有保存任何投票文件")
            return
        
        vote_files = [f for f in os.listdir(self.votes_dir) if f.endswith('.txt')]
        if not vote_files:
            print("❌ 投票目录为空")
            return
        
        print(f"\n🗳️  投票文件 ({len(vote_files)} 个):")
        print("=" * 50)
        
        for filename in sorted(vote_files, reverse=True):
            filepath = os.path.join(self.votes_dir, filename)
            file_size = os.path.getsize(filepath)
            file_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getctime(filepath)))
            
            print(f"📊 {filename} ({file_size/1024:.1f} KB, {file_time})")
        
        print("=" * 50)

    def get_attention_list(self, user_id, page=1):
        url = f"{self.base_url}/api.php/atten/list"
        
        payload = {
            "page": page,
            "order": {},
            "append": {"u": ["sex_text", "sex_p_text", "sex_o_text"]},
            "with_count": [],
            "kw": "",
            "user_id": int(user_id)
        }
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            result = response.json()
            return result
                
        except Exception as e:
            print(f"❌ 请求异常: {e}")
            return None

    def timestamp_to_datetime(self, timestamp):
        if not timestamp:
            return None
        try:
            if timestamp < 0 or timestamp > 2000000000:
                return None
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return None

    def parse_attention_list(self, result):
        if not result:
            print("❌ 结果为空")
            return None
            
        if result.get('code') == 1:
            data = result.get('data', {})
            attention_list = data.get('data', [])
            
            parsed_list = []
            
            for i, item in enumerate(attention_list, 1):
                followed_id = item.get('uid')
                
                user_data = item.get('u', {})
                
                user_name = user_data.get('user_name', f"用户_{followed_id}")
                nick_name = user_data.get('nick_name', user_name)
                
                age_raw = user_data.get('age', '')
                if age_raw is None:
                    age = ''
                elif isinstance(age_raw, int):
                    age = str(age_raw)
                elif isinstance(age_raw, str) and age_raw.isdigit():
                    age = age_raw
                else:
                    age = str(age_raw)
                
                birthday = user_data.get('birthday', '')
                if birthday is None:
                    birthday = ''
                
                sex_text = user_data.get('sex_text', '')
                sex_o_text = user_data.get('sex_o_text', '')
                sex_p_text = user_data.get('sex_p_text', '')
                
                last_time_raw = user_data.get('last_time')
                last_time_str = ""
                if last_time_raw:
                    try:
                        if isinstance(last_time_raw, (int, float)) and last_time_raw > 0:
                            last_time_str = datetime.fromtimestamp(last_time_raw).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            last_time_str = str(last_time_raw)
                    except:
                        last_time_str = str(last_time_raw)
                
                parsed_item = {
                    'attention_id': item.get('id'),
                    'follower_id': item.get('user_id'),
                    'user_id': followed_id,
                    'user_name': user_name,
                    'nick_name': nick_name,
                    'age': age,
                    'birthday': birthday,
                    'sex': sex_text,
                    'sex_orientation': sex_o_text,
                    'role': sex_p_text,
                    'height': user_data.get('height', ''),
                    'weight': user_data.get('weight', ''),
                    'country': user_data.get('country', ''),
                    'country_pic': user_data.get('country_pic', ''),
                    'intro': user_data.get('intro', ''),
                    'last_time': last_time_str,
                    'user_url': f"{self.base_url}/pd/#/page/user_show/user_show?id={followed_id}",
                    'create_time': self.timestamp_to_datetime(item.get('create_time')),
                    'create_time_timestamp': item.get('create_time'),
                    'update_time': self.timestamp_to_datetime(item.get('update_time')),
                    'update_time_timestamp': item.get('update_time'),
                }
                
                parsed_list.append(parsed_item)
            
            return {
                'code': 1,
                'total_pages': data.get('last_page'),
                'current_page': data.get('current_page', 1),
                'per_page': data.get('per_page', 20),
                'total_count': data.get('total'),
                'list': parsed_list,
                'query_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'query_timestamp': int(time.time())
            }
        else:
            error_msg = result.get('msg', '未知错误')
            error_code = result.get('code', -1)
            print(f"❌ API错误: {error_msg} (代码: {error_code})")
            return None

    def print_attention_list(self, parsed_data, user_id):
        if not parsed_data:
            return
        
        print(f"\n{'='*60}")
        print(f"用户 {user_id} 的关注列表")
        print(f"查询时间: {parsed_data.get('query_time', '未知')}")
        print(f"{'='*60}")
        
        if parsed_data.get('code') != 1:
            return
        
        if not parsed_data.get('list'):
            print("该用户没有关注任何人")
            return
        
        print(f"第 {parsed_data['current_page']} 页/共 {parsed_data['total_pages'] if parsed_data['total_pages'] else '未知'} 页")
        print(f"每页 {parsed_data['per_page']} 条，总关注数: {parsed_data['total_count'] if parsed_data['total_count'] else '未知'}")
        print(f"{'-'*60}")
        
        for i, user in enumerate(parsed_data['list'], 1):
            display_name = user.get('nick_name') or user.get('user_name') or f"用户{user['user_id']}"
    
            print(f"{i:2d}. ID: {user['user_id']:6d} | {display_name}")
            
            user_display_info = {
                "id": user['user_id'],
                "name": display_name,
                "nick_name": user.get('nick_name', ''),
                "age": user.get('age', ''),
                "birthday": user.get('birthday', ''),
                "sex_text": user.get('sex', ''),
                "sex_o_text": user.get('sex_orientation', ''),
                "sex_p_text": user.get('role', ''),
                "height": user.get('height', ''),
                "weight": user.get('weight', ''),
                "country": user.get('country', ''),
                "last_time": user.get('last_time', ''),
                "user_url": user.get('user_url', '')
            }
            
            self.display_complete_user_info(user_display_info, prefix="     ", compact=True)
            
            if user['create_time']:
                print(f"     关注时间: {user['create_time']}")
            
            print(f"{'-'*40}")

    def save_attention_data(self, data, user_id, page=1):
        if not data:
            print("❌ 没有数据可以保存")
            return False
        
        os.makedirs(self.attention_dir, exist_ok=True)
        
        queried_username = ""
        try:
            queried_user_info = self.get_complete_user_info(user_id)
            if queried_user_info and queried_user_info.get('name'):
                queried_username = queried_user_info['name']
        except:
            pass
        
        if queried_username:
            safe_username = INVALID_CHARS.sub("_", queried_username)[:20]
            filename = f"{user_id}_{safe_username}.txt"
        else:
            filename = f"{user_id}_用户关注列表.txt"
        
        filepath = os.path.join(self.attention_dir, filename)
        
        try:
            for item in data["data"]["data"]:
                if "u" in item:
                    item["user"] = dict(item["u"])
                    
                    uid = item["uid"]
                    item["user"]["user_url"] = f"{self.base_url}/pd/#/page/user_show/user_show?id={uid}"
                else:
                    uid = item["uid"]
                    item["user"] = {
                        "id": uid,
                        "user_name": f"用户_{uid}",
                        "user_url": f"{self.base_url}/pd/#/page/user_show/user_show?id={uid}"
                    }
            
            full_data = {
                "_query_info": {
                    "query_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "query_timestamp": int(time.time()),
                    "user_id": user_id,
                    "page": page
                },
                "_note": "字段后的//注释为中文翻译",
                "api_response": data
            }
            
            formatted_json = self.format_json_with_comments(full_data)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"{'='*60}\n")
                f.write(f"📋 用户关注列表查询结果\n")
                f.write(f"👤 被查询用户: {user_id} | {queried_username if queried_username else '未知用户'}\n")
                f.write(f"📄 页码: 第 {page} 页\n")
                f.write(f"⏰ 查询时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*60}\n\n")
                f.write("📝 带中文注释的JSON数据:\n")
                f.write("-" * 60 + "\n")
                f.write(formatted_json)
                f.write(f"\n{'='*60}\n")
                f.write(f"💾 文件保存时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"📁 文件位置: {filepath}\n")
                f.write("=" * 60)
            
            print(f"✅ 关注数据已保存: {filepath}")
            return True
            
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def query_attention_list(self):
        print("\n" + "="*60)
        print("📋 关注列表查询")
        print("=" * 60)
        
        while True:
            user_id = input("\n请输入要查询的用户ID (输入0返回): ").strip()
            
            if user_id == "0":
                return
            
            if not user_id.isdigit():
                print("❌ 用户ID必须是数字")
                continue
            
            page = input("请输入页码 (默认1): ").strip()
            page = int(page) if page.isdigit() else 1
            
            print(f"\n正在查询用户 {user_id} 的关注列表 (第 {page} 页)...")
            
            result = self.get_attention_list(user_id, page)
            
            if not result:
                print("❌ 获取数据失败")
                continue
            
            if result.get('code') != 1:
                print(f"❌ API返回错误: {result.get('msg', '未知错误')}")
                continue
            
            parsed_data = self.parse_attention_list(result)
            
            if parsed_data:
                self.print_attention_list(parsed_data, user_id)
                
                print("\n📁 保存选项:")
                print("1. 保存带中文注释的完整数据")
                print("2. 不保存")
                
                save_choice = input("\n请选择保存方式 (1-2): ").strip()
                
                if save_choice == "1":
                    self.save_attention_data(result, user_id, page)
            
            continue_query = input("\n是否继续查询其他用户？(y/N): ").strip().lower()
            if continue_query not in ['y', 'yes']:
                break

    def crawl_specific_post_gui(self, post_id: int):
        print(f"\n爬取特定帖子: {post_id}")
        print("=" * 50)

        detail = self.get_post_detail(post_id)

        if not detail:
            print(f"未找到帖子 {post_id}")
            return

        print(f"\n帖子详情:")
        self.display_post_for_browsing(detail, index=1)

        user_info = detail.get("user", {})
        user_id = user_info.get("id") or detail.get("user_id")

        if user_id:
            complete_user_info = self.get_complete_user_info(user_id)
            if complete_user_info:
                save_success = self.save_post_for_user_crawl(detail, complete_user_info, manual_mode=True, index=1)
                if save_success:
                    print(f"\n帖子 {post_id} 已保存到 {self.users_dir}/")
                else:
                    print(f"\n帖子 {post_id} 保存失败")
            else:
                print(f"无法获取用户 {user_id} 的完整信息")
        else:
            print(f"无法获取用户ID")

    def crawl_user_posts_gui(self, user_id: int, max_pages: int = 10):
        print(f"\n[爬取用户帖子] 用户ID: {user_id}")
        print(f"[计划页数] {max_pages} 页")
        print("=" * 50)

        user_info = self.get_complete_user_info(user_id)
        if user_info:
            print(f"\n[用户信息]:")
            self.display_complete_user_info(user_info, prefix="   ")

        all_posts = []
        page = 1
        total_saved = 0
        actual_pages_crawled = 0

        print(f"\n[开始] 获取用户 {user_id} 的帖子...")

        while page <= max_pages:
            print(f"\n[进度] 正在获取第 {page}/{max_pages} 页...")
            result = self.get_user_posts(user_id, page)

            if not result["success"]:
                print(f"[失败] 第 {page} 页获取失败: {result.get('error', '未知错误')}")
                break

            posts = result["data"]
            actual_pages_crawled += 1

            if not posts:
                print(f"[提示] 第 {page} 页没有数据，停止爬取")
                break

            print(f"[成功] 第 {page} 页获取到 {len(posts)} 个帖子")
            all_posts.extend(posts)

            for i, post in enumerate(posts, 1):
                post_index = len(all_posts) - len(posts) + i
                self.display_post_for_browsing(post, index=post_index)

            if posts:
                page_saved = 0
                for post in posts:
                    if self.save_post_for_user_crawl(post, user_info, manual_mode=False):
                        page_saved += 1
                        total_saved += 1
                    time.sleep(0.1)
                print(f"[保存] 第 {page} 页保存了 {page_saved}/{len(posts)} 个帖子")

            if not result.get("has_more", False):
                print("[提示] 已到最后一页")
                break

            page += 1
            time.sleep(0.5)

        print(f"\n{'='*50}")
        print("[完成] 用户帖子爬取完成!")
        print("=" * 50)
        print(f"[统计]")
        print(f"  实际爬取页数: {actual_pages_crawled}/{max_pages}")
        print(f"  找到帖子总数: {len(all_posts)}")
        print(f"  保存帖子总数: {total_saved}")
        if all_posts:
            save_rate = (total_saved / len(all_posts)) * 100
            print(f"  保存率: {save_rate:.1f}%")
        print(f"  保存位置: {self.users_dir}")

    def search_and_save_posts_gui(self, keyword, max_pages=3):
        print(f"\n🔍 搜索帖子: {keyword}")
        print("=" * 40)

        saver = ResultSaver(self.search_dir, f"帖子搜索_{keyword}", f"第1页", f"第{max_pages}页")

        all_posts = []
        total_saved = 0
        start_time = time.time()

        for page in range(1, max_pages + 1):
            print(f"\n📄 正在搜索第 {page} 页...")
            result = self.search_posts_with_page(keyword, page)

            if not result or not result.get("success"):
                print(f"❌ 第 {page} 页搜索失败: {result.get('error', '未知错误') if result else '请求失败'}")
                break

            posts = result.get("data", [])
            if not posts:
                print(f"📭 第 {page} 页没有找到相关帖子")
                if page == 1:
                    break
                else:
                    break

            print(f"✅ 第 {page} 页找到 {len(posts)} 个相关帖子")
            all_posts.extend(posts)

            page_saved = 0
            for idx, post in enumerate(posts, 1):
                post_index = len(all_posts) - len(posts) + idx
                self.display_post_for_browsing(post, post_index)

                user_info = post.get("user", {})
                user_id = user_info.get("id") or post.get("user_id")
                if user_id:
                    complete_user_info = self.get_complete_user_info(user_id)
                    if complete_user_info:
                        if self.save_post_for_user_crawl(post, complete_user_info, manual_mode=False):
                            page_saved += 1
                            total_saved += 1
                time.sleep(0.2)

            print(f"📝 第 {page} 页保存了 {page_saved}/{len(posts)} 个帖子")

            if page < max_pages:
                time.sleep(1)

        elapsed = time.time() - start_time
        print(f"\n🔍 搜索完成！")
        print(f"📊 总计: 找到 {len(all_posts)} 个帖子，保存 {total_saved} 个")
        print(f"⏱️  耗时: {elapsed:.1f}秒")
        print(f"💾 保存位置: {self.search_dir}/")

    def search_username_gui(self, keyword, max_pages=30, threads=8):
        print(f"\n🔍 搜索用户名包含 '{keyword}' 的用户")
        print(f"📄 搜索页数: {max_pages}")
        print(f"⚡ 使用 {threads} 个线程")
        print("=" * 60)

        searcher = UsernamePostSearcher(self, keyword, threads, max_pages, saver=None)

        start_time = time.time()

        found_users = searcher.search_all()

        elapsed = time.time() - start_time

        print(f"\n✅ 搜索完成！")
        print(f"⏱️  耗时: {elapsed:.1f}秒")
        print(f"👤 找到 {len(found_users)} 个用户")

        if found_users:
            print("\n💾 正在保存用户信息到搜索目录...")
            saved_count = 0
            for user in found_users:
                if self.save_user_info_to_search_dir(user):
                    saved_count += 1
                time.sleep(0.1)
            print(f"✅ 已将 {saved_count}/{len(found_users)} 个用户保存到 {self.search_dir}/")

        return found_users

    def search_userid_gui(self, user_id: int):
        print(f"\n搜索用户ID: {user_id}")
        print("=" * 60)

        user_info = self.get_complete_user_info(user_id)

        if user_info:
            print(f"\n用户: {user_info['name']} (ID:{user_info['id']})")
            self.display_complete_user_info(user_info, prefix="   ")

            print(f"\n正在保存用户信息到搜索目录...")
            if self.save_user_info_to_search_dir(user_info):
                print(f"用户信息已保存到搜索目录: {self.search_dir}/")

            user_url = f"https://dun.sdo.com/#/user/{user_id}"
            print(f"\n用户主页: {user_url}")
        else:
            print(f"未找到用户ID: {user_id}")

    def batch_vote_gui(self, start_id, end_id, threads=50):
        print(f"\n🚀 批量投票: ID {start_id} 到 {end_id}")
        print(f"⚡ 使用 {threads} 线程")
        print("=" * 60)

        task_ids = list(range(start_id, end_id + 1))

        saver = ResultSaver(self.votes_dir, f"批量投票", f"ID{start_id}", f"ID{end_id}")

        results = {}
        results_lock = threading.Lock()
        success_count = 0
        already_count = 0
        failed_count = 0
        start_time = time.time()

        def process_task(task_id):
            nonlocal success_count, already_count, failed_count
            try:
                success, status, vote_code, vote_msg, vote_data = self.vote_do(task_id)

                with results_lock:
                    if success:
                        if vote_code == 1:
                            success_count += 1
                            saver.save_record(f"任务{task_id}", "✅", f"投票成功: {vote_msg}")
                            print(f"ID:{task_id} ✅ 成功 | ✅{success_count} 🔄{already_count} ❌{failed_count}")
                        else:
                            already_count += 1
                            saver.save_record(f"任务{task_id}", "🔄", f"已投过票: {vote_msg}")
                            print(f"ID:{task_id} 🔄 已投 | ✅{success_count} 🔄{already_count} ❌{failed_count}")
                    else:
                        failed_count += 1
                        saver.save_record(f"任务{task_id}", "❌", f"投票失败: {vote_msg}")
                        print(f"ID:{task_id} ❌ 失败 | ✅{success_count} 🔄{already_count} ❌{failed_count}")

                    results[task_id] = (success, vote_code, vote_msg)
            except Exception as e:
                with results_lock:
                    failed_count += 1
                    results[task_id] = (False, 0, str(e))

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(process_task, tid) for tid in task_ids]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"⚠️ 任务异常: {e}")

        elapsed = time.time() - start_time
        print(f"\n✅ 批量投票完成！")
        print(f"📊 统计: 成功 {success_count} | 已投 {already_count} | 失败 {failed_count}")
        print(f"⏱️ 耗时: {elapsed:.1f}秒")
        print(f"💾 结果保存到: {self.votes_dir}")

        extra_stats = {
            "投票成功": success_count,
            "已投过票": already_count,
            "投票失败": failed_count,
            "成功率": f"{(success_count/(len(task_ids))*100):.1f}%" if task_ids else "0%"
        }
        saver.finalize(success_count, failed_count, len(task_ids), elapsed, extra_stats)

    def query_attention_gui(self, user_id, page=1):
        print(f"\n📋 查询用户 {user_id} 的关注列表 (第 {page} 页)")
        print("=" * 60)

        result = self.get_attention_list(user_id, page)

        if not result:
            print("❌ 获取数据失败")
            return

        if result.get('code') != 1:
            print(f"❌ API返回错误: {result.get('msg', '未知错误')}")
            return

        parsed_data = self.parse_attention_list(result)

        if parsed_data:
            self.print_attention_list(parsed_data, user_id)

            self.save_attention_data(result, user_id, page)
            print(f"💾 关注列表已保存到: {self.attention_dir}")

def load_accounts(spider):
    try:
        with open(spider.accounts_file, "r", encoding="utf-8") as f:
            acc = json.load(f)
            acc.sort(key=lambda x: x.get("最后登录", ""), reverse=True)
            return acc
    except:
        return []

def save_accounts(spider, accounts):
    with open(spider.accounts_file, "w", encoding="utf-8") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def send_sms_code(spider, phone):
    url = f"{spider.base_url}/api.php/index/pcode"
    headers = spider.headers.copy()
    headers.pop("token", None)
    
    try:
        r = requests.post(url, headers=headers, json={"scene": "login", "phone": phone}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 1:
                print("✅ 验证码发送成功")
                return True
            else:
                print(f"❌ 验证码发送失败: {data.get('msg')}")
        else:
            print(f"❌ HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ 请求异常: {e}")
    return False

def login_with_account(spider, phone="", password="", pcode="", login_type=1):
    url = f"{spider.base_url}/api.php/user/login"
    data = {"phone": phone, "type": login_type}
    if login_type == 1:
        data["password"] = password
    else:
        data["pcode"] = pcode
    
    headers = spider.headers.copy()
    headers.pop("token", None)
    
    try:
        r = requests.post(url, headers=headers, json=data, timeout=10)
        if r.status_code == 200:
            res = r.json()
            if res.get("code") == 1:
                token = res["data"].get("token")
                if token:
                    print(f"✅ 登录成功！Token: {token[:20]}...")
                    return token
            else:
                print(f"❌ 登录失败: {res.get('msg')}")
        else:
            print(f"❌ HTTP {r.status_code}")
    except Exception as e:
        print(f"❌ 请求异常: {e}")
    return None

def login_menu(spider, auto_login=True):
    print("=" * 50)
    print("🔐 登录系统")
    print("=" * 50)
    
    if auto_login:
        auto_token = spider.load_login_state()
        if auto_token:
            print(f"🔑 尝试自动登录...")
            spider.set_token(auto_token)
            
            if test_token_valid(spider, auto_token):
                print(f"✅ 自动登录成功！")
                return auto_token
            else:
                print("❌ 自动登录失败，Token已失效")
                spider.clear_login_state()
    
    accounts = load_accounts(spider)
    
    if accounts:
        print("📱 已保存账号（按最近登录排序）：")
        for i, acc in enumerate(accounts, 1):
            name = acc.get("昵称", "未命名")
            phone = acc.get("手机号", "")
            phone_display = phone[:3] + "****" + phone[-4:] if phone else "Token 用户"
            last_login = acc.get("最后登录", "")
            print(f"  {i}. {name} ({phone_display}) - {last_login}")
        
        choice = input("\n选择序号直接登录，或回车手动登录：").strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(accounts):
                token = accounts[idx]["Token"]
                spider.set_token(token)
                accounts[idx]["最后登录"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_accounts(spider, accounts)
                return token
    
    while True:
        print("\n1. 手机号+密码  2. 短信验证码  3. 直接输入 Token  4. 退出")
        ch = input("请选择：").strip()
        
        if ch == "1":
            phone = input("手机号：").strip()
            pwd = input("密码：").strip()
            if not phone or not pwd:
                continue
            
            token = login_with_account(spider, phone=phone, password=pwd, login_type=1)
            login_method = "密码"
            
        elif ch == "2":
            phone = input("手机号：").strip()
            if not phone or len(phone) != 11:
                print("❌ 手机号格式错误")
                continue
            
            if send_sms_code(spider, phone):
                code = input("验证码：").strip()
                if len(code) != 6:
                    print("❌ 验证码格式错误")
                    continue
                
                token = login_with_account(spider, phone=phone, pcode=code, login_type=2)
                login_method = "验证码"
            else:
                continue
                
        elif ch == "3":
            token = input("Token：").strip()
            if len(token) < 20:
                print("❌ Token 过短")
                continue
            print(f"✅ 直接使用Token: {token[:20]}...")
            login_method = "token"
            
        elif ch == "4":
            return None
            
        else:
            print("❌ 无效选择")
            continue
        
        if token:
            if input("保存账号？(y/n)：").lower() == "y":
                nickname = input("昵称(可选)：").strip()
                phone = input("手机号(可选)：").strip()
                accounts.append({
                    "手机号": phone or "token_user",
                    "Token": token,
                    "昵称": nickname or phone or "未命名",
                    "登录方式": login_method,
                    "最后登录": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "创建时间": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "更新时间": time.strftime("%Y-%m-%d %H:%M:%S")
                })
                save_accounts(spider, accounts)
            spider.set_token(token)
            return token
        
        print("⚠️ 登录失败，请重试")


def test_token_valid(spider, token):
    try:
        test_headers = spider.headers.copy()
        test_headers["token"] = token
        
        r = requests.post(
            f"{spider.base_url}/api.php/circle/list",
            headers=test_headers,
            json={"page": 1, "kw": "", "type": "user"},
            timeout=10
        )
        
        if r.status_code == 200:
            data = r.json()
            return data.get("code") == 1
    except:
        pass
    return False

def manage_accounts(spider):
    accounts = load_accounts(spider)
    if not accounts:
        print("📭 无保存账号")
        return
    
    print("\n📋 保存账号：")
    for i, acc in enumerate(accounts, 1):
        print(f"  {i}. {acc.get('昵称')} ({acc.get('手机号', 'Token')}) - {acc.get('最后登录')}")
    
    if input("\n删除账号？(y/n)：").lower() == "y":
        idx = int(input("输入编号(0取消)：") or 0) - 1
        if 0 <= idx < len(accounts):
            accounts.pop(idx)
            save_accounts(spider, accounts)
            print("✅ 已删除")

def check_token_status(spider, token):
    accounts = load_accounts(spider)
    if accounts and token:
        for acc in accounts:
            if acc.get("Token") == token:
                print(f"📊 当前账号: {acc.get('昵称')}")
                phone = acc.get("手机号", "")
                if phone:
                    phone_display = phone[:3] + "****" + phone[-4:]
                    print(f"   手机号: {phone_display}")
                print(f"   账号创建: {acc.get('创建时间')}")
                print(f"   最后登录: {acc.get('最后登录')}")
                print(f"   Token预览: {token[:20]}...")
                return
        
        print("📊 当前Token未在保存的账号中找到")
    else:
        print("📊 未登录或未保存任何账号")

def main():
    print("=" * 60)
    print("📱 BDSM 论坛工具")
    print("=" * 60)
    spider = BDSMForumSpider(interactive=True)
    token = login_menu(spider, auto_login=True)
    if not token:
        print("❌ 登录失败，程序退出")
        return
    
    while True:
        print("\n" + "=" * 60)
        print("📱 主菜单")
        print("=" * 60)
        print(f"当前账号: {token[:20]}...")
        print(f"数据目录: {spider.data_dir}")
        print("【爬虫】1.批量爬多页  2.爬特定帖  3.爬用户全部  4.手动浏览  5.用户文件")
        print("【搜索】6.搜索帖子  7.用户名搜索  8.搜索帖子（新帖优先）")
        print("【投票】9.单任务投票 10.批量投票  11.投票文件")
        print("【关注】12.查询关注列表")
        print("【账号】13.切换账号 14.管理账号 15.Token状态 16.清除登录状态 17.退出")
        print("=" * 60)
        choice = input("请选择(1-17)：").strip()
        
        if choice == "1":
            start = int(input("开始页码(默认1)：") or 1)
            pages = int(input("爬取页数(默认3)：") or 3)
            spider.crawl_and_save_posts(start_page=start, max_pages=pages)
            
        elif choice == "2":
            pid = int(input("帖子ID：") or 0)
            if pid:
                spider.crawl_specific_post(pid)
                
        elif choice == "3":
            uid = int(input("用户ID：") or 0)
            if uid:
                spider.crawl_user_posts(uid)
                
        elif choice == "4":
            spider.manual_browse_posts()
            
        elif choice == "5":
            spider.show_user_files()
            
        elif choice == "6":
            spider.search_and_save_posts()
            
        elif choice == "7":
            spider.search_username()
            
        elif choice == "8":
            keyword = input("请输入搜索关键词: ").strip()
            if not keyword:
                print("❌ 请输入搜索关键词")
                continue
            
            try:
                page_input = input("请输入搜索页数 (默认1页): ").strip()
                if not page_input:
                    max_pages = 1
                else:
                    max_pages = int(page_input)
                    max_pages = max(1, min(500, max_pages))
            except:
                max_pages = 1
                print("⚠️  输入无效，使用默认1页")
            
            print(f"\n🔍 搜索关键词: '{keyword}'")
            print(f"📄 搜索页数: {max_pages}页（优先保存新发布的帖子）")
            print("=" * 50)
            
            saver = ResultSaver(spider.search_dir, f"新帖优先搜索_{keyword}", f"第1页", f"第{max_pages}页")
            
            all_posts = []
            total_saved = 0
            start_time = time.time()
            
            for page in range(1, max_pages + 1):
                print(f"\n📄 正在搜索第 {page} 页...")
                result = spider.search_posts_with_page(keyword, page)
                
                if not result or not result.get("success"):
                    print(f"❌ 第 {page} 页搜索失败: {result.get('error', '未知错误')}")
                    saver.save_record(f"第{page}页", "❌", f"搜索失败: {result.get('error', '未知错误')}")
                    break
                    
                posts = result.get("data", [])
                if not posts:
                    print(f"📭 第 {page} 页没有找到相关帖子")
                    saver.save_record(f"第{page}页", "📭", "没有找到相关帖子")
                    if page == 1:
                        break
                    else:
                        break
                
                print(f"✅ 第 {page} 页找到 {len(posts)} 个相关帖子")
                saver.save_record(f"第{page}页", "✅", f"找到{len(posts)}个帖子")
                all_posts.extend(posts)
                
                print(f"\n📋 第 {page} 页搜索结果（新发布在前）:")
                print("=" * 60)
                
                for i, post in enumerate(posts, 1):
                    post_id = post.get("id")
                    create_time = post.get("create_time", 0)
                    create_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time))
                    
                    user_info = post.get("user", {})
                    user_id = user_info.get("id") or post.get("user_id")
                    username = user_info.get("user_name") or f"用户_{user_id}"
                    
                    is_new = False
                    if create_time > (time.time() - 30 * 24 * 60 * 60):
                        is_new = True
                    
                    new_mark = "🆕" if is_new else "  "
                    print(f"{new_mark}[{i}] 帖子ID: {post_id} | 用户: {username}")
                    print(f"   发布时间: {create_time_str} {'（新发布）' if is_new else ''}")
                    
                    content = post.get("content") or post.get("title", "无内容")
                    if len(content) > 100:
                        content = content[:100] + "..."
                    print(f"   内容: {content}")
                    print(f"   📊 浏览: {post.get('onclick', 0)} | 赞: {post.get('dig_count', 0)} | 评论: {post.get('com_count', 0)}")
                    print(f"   {'-'*40}")
                
                if posts:
                    print(f"\n💾 正在处理第 {page} 页的帖子保存...")
                    
                    print("🆕 优先保存新发布的帖子（最近30天内）:")
                    new_posts = []
                    other_posts = []
                    
                    for post in posts:
                        create_time = post.get("create_time", 0)
                        if create_time > (time.time() - 30 * 24 * 60 * 60):
                            new_posts.append(post)
                        else:
                            other_posts.append(post)
                    
                    if new_posts:
                        print(f"   发现 {len(new_posts)} 个新帖子，正在自动保存...")
                        for post in new_posts:
                            post_id = post.get("id")
                            create_time = post.get("create_time", 0)
                            create_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time))
                            
                            user_info = post.get("user", {})
                            user_id = user_info.get("id") or post.get("user_id")
                            if user_id:
                                complete_user_info = spider.get_complete_user_info(user_id)
                                if complete_user_info:
                                    if spider.save_post_for_user_crawl(post, complete_user_info, manual_mode=False):
                                        total_saved += 1
                                        saver.save_record(f"新帖{post_id}", "✅", f"自动保存（发布于{create_time_str}）")
                                    else:
                                        saver.save_record(f"新帖{post_id}", "❌", "保存失败")
                            time.sleep(0.2)
                        
                        print(f"   ✅ 新帖子已自动保存 {len(new_posts)} 个")
                    
                    if other_posts:
                        print(f"\n📋 还有 {len(other_posts)} 个较旧的帖子")
                        save_choice = input("是否保存较旧的帖子？(y=全部保存/s=选择保存/n=跳过): ").strip().lower()
                        
                        if save_choice == 'y':
                            print(f"   正在自动保存 {len(other_posts)} 个旧帖子...")
                            for post in other_posts:
                                post_id = post.get("id")
                                user_info = post.get("user", {})
                                user_id = user_info.get("id") or post.get("user_id")
                                if user_id:
                                    complete_user_info = spider.get_complete_user_info(user_id)
                                    if complete_user_info:
                                        if spider.save_post_for_user_crawl(post, complete_user_info, manual_mode=False):
                                            total_saved += 1
                                            saver.save_record(f"旧帖{post_id}", "✅", "自动保存")
                                time.sleep(0.2)
                            print(f"   ✅ 旧帖子已保存 {len(other_posts)} 个")
                            
                        elif save_choice == 's':
                            print("\n🔍 请选择要保存的帖子:")
                            selected = input(f"输入第 {page} 页的帖子编号（用逗号分隔，如 1,3,5）: ").strip()
                            
                            if selected:
                                try:
                                    indices = [int(idx.strip()) - 1 for idx in selected.split(',') if idx.strip().isdigit()]
                                    selected_count = 0
                                    for idx in indices:
                                        if 0 <= idx < len(other_posts):
                                            post = other_posts[idx]
                                            post_id = post.get("id")
                                            user_info = post.get("user", {})
                                            user_id = user_info.get("id") or post.get("user_id")
                                            if user_id:
                                                complete_user_info = spider.get_complete_user_info(user_id)
                                                if complete_user_info:
                                                    if spider.save_post_for_user_crawl(post, complete_user_info, manual_mode=True):
                                                        selected_count += 1
                                                        total_saved += 1
                                                        saver.save_record(f"旧帖{post_id}", "✅", "手动选择保存")
                                            time.sleep(0.3)
                                    print(f"   ✅ 选择了 {selected_count}/{len(indices)} 个帖子保存")
                                except:
                                    print("❌ 输入格式错误")
                                    saver.save_record(f"第{page}页", "❌", "输入格式错误")
                        
                        else:
                            print("⏭️  跳过保存较旧帖子")
                            saver.save_record(f"第{page}页", "⏭️", f"跳过{len(other_posts)}个旧帖子")
                    else:
                        saver.save_record(f"第{page}页", "📊", f"本页无旧帖子")
                
                if page < max_pages:
                    continue_choice = input(f"\n是否继续搜索第 {page+1} 页？(y/n): ").strip().lower()
                    if continue_choice != 'y':
                        print("⏹️  停止搜索")
                        saver.save_record("搜索", "⏹️", f"用户在第{page}页停止")
                        break
                    
                    time.sleep(1)
            
            elapsed = time.time() - start_time
            print(f"\n" + "=" * 60)
            print("🔍 搜索完成！")
            print("=" * 60)
            print(f"📊 统计:")
            print(f"  总搜索页数: {min(page, max_pages)}/{max_pages}")
            print(f"  找到帖子总数: {len(all_posts)}")
            print(f"  保存帖子总数: {total_saved}")
            
            if all_posts:
                save_rate = (total_saved / len(all_posts)) * 100
                print(f"  保存率: {save_rate:.1f}%")
            
            print(f"  ⏱️  耗时: {elapsed:.1f}秒")
            
            extra_stats = {
                "搜索关键词": keyword,
                "实际搜索页数": f"{min(page, max_pages)}/{max_pages}",
                "找到帖子数": len(all_posts),
                "保存帖子数": total_saved,
                "保存率": f"{save_rate:.1f}%" if all_posts else "0%"
            }
            
            saver.finalize(total_saved, len(all_posts)-total_saved, len(all_posts), elapsed, extra_stats)
            print(f"\n📋 搜索记录已保存: {saver.filepath}")
            print(f"💾 帖子数据保存在: {spider.users_dir}/")
            
        elif choice == "9":
            tid = int(input("投票任务ID：") or 0)
            if tid:
                spider.vote_single_test(tid)
                
        elif choice == "10":
            spider.batch_vote()
            
        elif choice == "11":
            spider.show_vote_files()
            
        elif choice == "12":
            spider.query_attention_list()
            
        elif choice == "13":
            new_token = login_menu(spider, auto_login=False)
            if new_token:
                token = new_token
                
        elif choice == "14":
            manage_accounts(spider)
            
        elif choice == "15":
            check_token_status(spider, token)
            
        elif choice == "16":
            spider.clear_login_state()
            print("🗑️  登录状态已清除，下次启动需要重新登录")
            
        elif choice == "17":
            print(f"👋 再见！数据保存在 {spider.data_dir}/")
            break
            
        else:
            print("❌ 无效选择")

if __name__ == "__main__":
    main(
