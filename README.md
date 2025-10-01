# Werewolf Game (多角色版，Flask + Socket.IO + PostgreSQL)

## 运行
```bash
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # 修改 DATABASE_URL & 密钥
python app.py               # 首次会自动建表并初始化角色库
# 浏览器打开 http://localhost:5000
```

## 提示
- 该项目为教学向 MVP：已实现多角色库、房间角色配置、基础夜/昼结算、部分技能。
- 生产前请完善：严格的权限校验、倒计时自动结算、旁观/聊天频道、情侣/魅惑关系持久化等。
