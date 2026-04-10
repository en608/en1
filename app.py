# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI
import sys
import os
import re

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# 解决编码问题
sys.stdout.reconfigure(encoding='utf-8')
app = Flask(__name__)

app.config['SECRET_KEY'] = 'dev-secret-key-123456'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///new_users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

try:
    client = OpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4o")
except:
    client = None
    MODEL_NAME = "gpt-4o"

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录以访问此页面'

class User(UserMixin, db.Model):
    __tablename__ = 'new_user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def extract_video_info(url):
    if yt_dlp is None:
        return None, "请先安装 yt-dlp"

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['zh', 'zh-CN', 'zh-TW', 'en'],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            subtitles = info.get('subtitles', {})
            for lang in ['zh', 'zh-CN', 'zh-TW', 'en']:
                if lang in subtitles:
                    subtitle_url = subtitles[lang][0]['url']
                    import urllib.request
                    with urllib.request.urlopen(subtitle_url) as response:
                        subtitle_content = response.read().decode('utf-8')
                        clean_text = clean_subtitle(subtitle_content)
                        return clean_text, 'subtitles'

            automatic_captions = info.get('automatic_captions', {})
            for lang in ['zh', 'zh-CN', 'zh-TW', 'zh-CN-en', 'en', 'en-orig']:
                if lang in automatic_captions:
                    subtitle_url = automatic_captions[lang][0]['url']
                    import urllib.request
                    with urllib.request.urlopen(subtitle_url) as response:
                        subtitle_content = response.read().decode('utf-8')
                        clean_text = clean_subtitle(subtitle_content)
                        return f"[自动生成字幕]\n{clean_text}", 'subtitles'

            title = info.get('title', '未知标题')
            description = info.get('description', '')
            duration = info.get('duration', 0)
            duration_str = f"{duration // 60}分{duration % 60}秒" if duration else "未知"
            metadata = f"视频标题：{title}\n视频时长：{duration_str}\n视频描述：{description or '无描述'}"
            return metadata, 'metadata'
    except Exception as e:
        return None, f"提取失败：{str(e)}"

def clean_subtitle(subtitle_text):
    text = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}', '', subtitle_text)
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'WEBVTT.*\n', '', text)
    text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
    return text

def is_video_url(text):
    video_patterns = [
        r'(youtube\.com|youtu\.be)',
        r'(bilibili\.com|b23\.tv)',
        r'(douyin\.com)',
        r'(tiktok\.com)',
        r'(ixigua\.com)',
        r'(weibo\.com)',
        r'(youku\.com)',
    ]
    return any(re.search(pattern, text) for pattern in video_patterns)


@app.route('/')
def index():
    if current_user.is_authenticated:
        return render_template('index.html')
    return redirect(url_for('login'))

@app.route('/summarize', methods=['POST'])
@login_required
def summarize():
    try:
        user_input = request.form['content'].strip()
        if not user_input:
            return render_template("index.html", error="请输入内容或视频链接")

        video_content = None
        info_type = None
        if is_video_url(user_input):
            video_content, info_type = extract_video_info(user_input)
            if video_content is None:
                return render_template("index.html", error=f"无法提取视频信息：{info_type}", content=user_input)

            if info_type == 'subtitles':
                prompt = f"请根据以下视频字幕内容，分点列出主要要点：\n\n{video_content[:8000]}"
            else:
                prompt = f"请根据视频信息总结要点：\n\n{video_content}"
            source_info = f"【视频】"
        else:
            prompt = f"请分点列出以下内容的要点：\n\n{user_input[:8000]}"
            source_info = "【文本】"

        if not client or not client.api_key:
            return render_template("index.html", error="未配置OpenAI API密钥，无法生成总结", content=user_input)

        response = client.chat.completions.create(model=MODEL_NAME,messages=[{"role": "user", "content": prompt}],max_tokens=500)
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        print("错误：", e)
        summary = f"分析出错：{str(e)}"

    return render_template("index.html", summary=summary, content=user_input, source_info=source_info)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='用户名或密码错误')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password or not confirm_password:
            return render_template('register.html', error='请填写所有字段')
        if len(password) < 6:
            return render_template('register.html', error='密码长度至少为6位')
        if password != confirm_password:
            return render_template('register.html', error='两次输入的密码不一致')
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='用户名已被使用')

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return render_template('login.html', success='注册成功！请登录')

    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
if __name__ == '__main__':
    app.run(debug=True)
application = app
