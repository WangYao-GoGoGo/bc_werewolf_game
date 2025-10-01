from __future__ import annotations
import os, uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, join_room, leave_room, emit
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models import Base, User, Room, Membership, Game, PlayerState, Role, Action, Phase, RoomRoleConfig
from security import hash_password, verify_password
from forms import RegisterForm, LoginForm, CreateRoomForm
from game_engine import init_roles, assign_roles, next_phase, role_by_user
from role_effects import resolve_night_with_roles, resolve_day_vote_with_roles

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("FLASK_SECRET_KEY","dev-secret")
MESSAGE_QUEUE = os.getenv("SOCKETIO_MESSAGE_QUEUE")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, expire_on_commit=False))

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", message_queue=MESSAGE_QUEUE, async_mode="eventlet")

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id: str):
    db = SessionLocal()
    try: return db.get(User, int(user_id))
    finally: db.close()

@app.teardown_appcontext
def remove_session(exc=None): SessionLocal.remove()

@app.route("/")
def index():
    if current_user.is_authenticated: return redirect(url_for("lobby"))
    return render_template("index.html")

@app.route("/register", methods=["GET","POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        db = SessionLocal()
        try:
            if db.query(User).filter(User.email==form.email.data).first():
                flash("该邮箱已注册","warning"); return render_template("register.html", form=form)
            u = User(email=form.email.data, nickname=form.nickname.data, password_hash=hash_password(form.password.data))
            db.add(u); db.commit()
            flash("注册成功，请登录","success"); return redirect(url_for("login"))
        finally: db.close()
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.email==form.email.data).first()
            if not u or not verify_password(form.password.data, u.password_hash):
                flash("邮箱或密码错误","danger"); return render_template("login.html", form=form)
            login_user(u); return redirect(url_for("lobby"))
        finally: db.close()
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout(): logout_user(); return redirect(url_for("index"))

@app.route("/lobby", methods=["GET","POST"])
@login_required
def lobby():
    form = CreateRoomForm()
    db = SessionLocal()
    try:
        rooms = db.query(Room).order_by(Room.id.desc()).limit(50).all()
        init_roles(db)
        all_roles = db.query(Role).order_by(Role.camp, Role.name).all()
        if form.validate_on_submit():
            room = Room(name=form.name.data or f"房间-{uuid.uuid4().hex[:6]}", owner_id=current_user.id,
                        max_players=max(5, int(form.max_players.data or 8)), created_at=datetime.utcnow())
            db.add(room); db.commit()
            # 保存角色配置
            for role in all_roles:
                cnt = int(request.form.get(f"role_{role.id}", 0) or 0)
                if cnt>0: db.add(RoomRoleConfig(room_id=room.id, role_id=role.id, count=cnt))
            db.commit()
            db.add(Membership(user_id=current_user.id, room_id=room.id)); db.commit()
            return redirect(url_for("room", room_id=room.id))
        return render_template("lobby.html", form=form, rooms=rooms, all_roles=all_roles)
    finally: db.close()

@app.route("/room/<int:room_id>")
@login_required
def room(room_id: int):
    db = SessionLocal()
    try:
        room = db.get(Room, room_id)
        if not room:
            flash("房间不存在","warning"); return redirect(url_for("lobby"))
        if not db.query(Membership).filter_by(user_id=current_user.id, room_id=room_id).first():
            db.add(Membership(user_id=current_user.id, room_id=room_id)); db.commit()
        game = db.query(Game).filter_by(room_id=room_id, finished=False).first()
        players = db.query(User).join(Membership, Membership.user_id==User.id).filter(Membership.room_id==room_id).all()
        return render_template("room.html", room=room, game=game, players=players)
    finally: db.close()

@app.route("/start/<int:room_id>", methods=["POST"])
@login_required
def start(room_id: int):
    db = SessionLocal()
    try:
        room = db.get(Room, room_id)
        if not room: flash("房间不存在","warning"); return redirect(url_for("lobby"))
        if room.owner_id != current_user.id:
            flash("只有房主可以开始游戏","danger"); return redirect(url_for("room", room_id=room_id))
        members = db.query(Membership).filter_by(room_id=room_id).all()
        if len(members) < 5:
            flash("至少 5 人才能开始","warning"); return redirect(url_for("room", room_id=room_id))
        old = db.query(Game).filter_by(room_id=room_id, finished=False).first()
        if old: old.finished=True; db.commit()
        game = Game(room_id=room_id, created_at=datetime.utcnow(), finished=False)
        db.add(game); db.commit()
        assign_roles(db, game.id)
        phase = Phase(game_id=game.id, number=1, type="night", ends_at=datetime.utcnow()+timedelta(seconds=90))
        db.add(phase); db.commit()
        socketio.emit("game_started", {"game_id": game.id}, to=f"room_{room_id}")
        socketio.emit("phase_change", {"phase":"night","deadline":phase.ends_at.isoformat()}, to=f"room_{room_id}")
        return redirect(url_for("room", room_id=room_id))
    finally: db.close()

# -------- API --------
@app.route("/api/state/<int:room_id>")
@login_required
def api_state(room_id: int):
    db = SessionLocal()
    try:
        game = db.query(Game).filter_by(room_id=room_id, finished=False).first()
        if not game: return jsonify({"phase":"waiting","players":[],"role_key":None})
        phase = db.query(Phase).filter_by(game_id=game.id).order_by(Phase.number.desc()).first()
        deadline = phase.ends_at.isoformat() if phase and phase.ends_at else None
        ps_list = db.query(PlayerState).filter_by(game_id=game.id).all()
        users = {u.id: u for u in db.query(User).all()}
        me_ps = next((ps for ps in ps_list if ps.user_id==current_user.id), None)
        me_role = None
        if me_ps: me_role = (db.get(Role, me_ps.role_id)).key
        players = [{"id":ps.user_id,"nickname":users[ps.user_id].nickname,"alive":ps.alive,"is_self":ps.user_id==current_user.id} for ps in ps_list]
        return jsonify({"phase":phase.type if phase else "night","deadline":deadline,"players":players,"role_key":me_role})
    finally: db.close()

# -------- Socket.IO --------
@socketio.on("connect")
def on_connect():
    if not current_user.is_authenticated: return False

@socketio.on("join_room")
def on_join(data):
    rid = int(data.get("room_id")); join_room(f"room_{rid}"); emit("joined", {"room_id":rid})

@socketio.on("leave_room")
def on_leave(data):
    rid = int(data.get("room_id")); leave_room(f"room_{rid}"); emit("left", {"room_id":rid})

@socketio.on("night_action")
def on_night_action(data):
    db = SessionLocal()
    try:
        rid = int(data.get("room_id"))
        game = db.query(Game).filter_by(room_id=rid, finished=False).first()
        if not game: return
        phase = db.query(Phase).filter_by(game_id=game.id).order_by(Phase.number.desc()).first()
        if phase.type != "night": return
        target_user_id = data.get("target_user_id")
        action_type = data.get("action")
        if target_user_id is not None: target_user_id = int(target_user_id)
        ps = db.query(PlayerState).filter_by(game_id=game.id, user_id=current_user.id).first()
        if not ps or not ps.alive: return
        # 简化的权限检查：前端负责露出对应按钮
        a = db.query(Action).filter_by(game_id=game.id, phase_number=phase.number, actor_user_id=current_user.id).first()
        if not a:
            a = Action(game_id=game.id, phase_number=phase.number, actor_user_id=current_user.id, type=action_type, target_user_id=target_user_id)
            db.add(a)
        else:
            a.type = action_type; a.target_user_id = target_user_id
        db.commit()
        emit("action_ok", {"action":action_type,"target":target_user_id})
        acts = db.query(Action).filter_by(game_id=game.id, phase_number=phase.number).all()
        res = resolve_night_with_roles(db, game.id, phase, acts)
        if res:
            np = next_phase(db, game.id, "day")
            socketio.emit("night_resolved", {"summary":res}, to=f"room_{rid}")
            socketio.emit("phase_change", {"phase":"day","deadline":np["deadline"].isoformat()}, to=f"room_{rid}")
    finally: db.close()

@socketio.on("day_vote")
def on_day_vote(data):
    db = SessionLocal()
    try:
        rid = int(data.get("room_id"))
        game = db.query(Game).filter_by(room_id=rid, finished=False).first()
        if not game: return
        phase = db.query(Phase).filter_by(game_id=game.id).order_by(Phase.number.desc()).first()
        if phase.type != "day": return
        target_user_id = data.get("target_user_id")
        if target_user_id is not None: target_user_id = int(target_user_id)
        ps = db.query(PlayerState).filter_by(game_id=game.id, user_id=current_user.id).first()
        if not ps or not ps.alive: return
        a = db.query(Action).filter_by(game_id=game.id, phase_number=phase.number, actor_user_id=current_user.id).first()
        if not a:
            a = Action(game_id=game.id, phase_number=phase.number, actor_user_id=current_user.id, type="day_vote", target_user_id=target_user_id); db.add(a)
        else:
            a.type = "day_vote"; a.target_user_id = target_user_id
        db.commit()
        acts = db.query(Action).filter_by(game_id=game.id, phase_number=phase.number).all()
        res = resolve_day_vote_with_roles(db, game.id, phase, acts)
        if res:
            np = next_phase(db, game.id, "night")
            socketio.emit("day_resolved", {"summary":res}, to=f"room_{rid}")
            socketio.emit("phase_change", {"phase":"night","deadline":np["deadline"].isoformat()}, to=f"room_{rid}")
    finally: db.close()

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        init_roles(db)  # 初始化角色库
    socketio.run(app, host="0.0.0.0", port=5000)
