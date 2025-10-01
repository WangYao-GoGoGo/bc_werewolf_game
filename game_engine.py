from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from models import Role, Game, PlayerState, Membership, Phase, RoomRoleConfig

# 全量角色库（来自你的清单），附带阵营
ROLE_LIBRARY = {
    # villager camp
    "seer": ("预言家", "夜晚查验一人身份", "villager"),
    "witch": ("女巫", "解药+毒药各一瓶", "villager"),
    "hunter": ("猎人", "死亡时可带走一人", "villager"),
    "guardian": ("守卫", "夜间守护一人", "villager"),
    "idiot": ("白痴", "首次被投免死并亮身份", "villager"),
    "little_girl": ("小女孩", "夜晚可偷看狼人", "villager"),
    "thief": ("盗贼", "开局二选一身份", "villager"),
    "village_head": ("村长", "白天多一票", "villager"),
    "scapegoat": ("替罪羊", "平票时被处死", "villager"),
    "snow_blender": ("混雪儿", "特殊村民变种", "villager"),
    "wild_kid": ("野孩子", "认师父,师父死转狼阵营", "villager"),
    "raven": ("乌鸦", "夜里给人加一票", "villager"),
    "fox": ("狐狸", "查三人中是否有狼", "villager"),
    "bear": ("熊", "邻座有狼会被提醒", "villager"),
    "stutter_judge": ("口吃法官", "可打断流程(主持类)", "villager"),
    "knight": ("绣刃骑士", "白天翻牌挑战狼人", "villager"),
    "changeling": ("变脸者", "特定时刻换身份", "villager"),
    "maid": ("顺从的女仆", "执行主人的指令", "villager"),
    "nine_tailed_fox": ("九尾妖狐", "查验为好人但需独活", "villager"),
    "villager": ("村民", "无技能", "villager"),
    # werewolf camp
    "werewolf": ("狼人", "夜晚击杀一人", "werewolf"),
    "white_wolf_king": ("白狼王", "死后带走一人", "werewolf"),
    "wolfdog": ("狼狗", "昼为好人 夜为狼人", "werewolf"),
    "breeder_wolf": ("种狼", "可复活被杀的狼人", "werewolf"),
    "wild_wolf": ("野狼", "更强攻击力", "werewolf"),
    "wolf_beauty": ("狼美人", "迷惑一人 自死同死", "werewolf"),
    "demon": ("恶魔", "特殊技能狼人", "werewolf"),
    # neutral camp
    "cupid": ("丘比特", "绑定情侣 一死俱死", "neutral"),
    "piper": ("吹笛者", "每晚魅惑两人 魅惑全灭胜", "neutral"),
    "angel": ("天使", "第1天未死则胜", "neutral"),
}

def init_roles(db: Session):
    existing = {r.key for r in db.query(Role).all()}
    for key, (name, desc, camp) in ROLE_LIBRARY.items():
        if key not in existing:
            db.add(Role(key=key, name=name, description=desc, camp=camp))
    db.commit()

def role_by_user(db: Session, game_id: int, user_id: int) -> Optional[str]:
    ps = db.query(PlayerState).filter_by(game_id=game_id, user_id=user_id).first()
    if not ps: return None
    r = db.get(Role, ps.role_id)
    return r.key if r else None

def assign_roles(db: Session, game_id: int):
    init_roles(db)
    game = db.get(Game, game_id)
    members = db.query(Membership).filter_by(room_id=game.room_id).all()
    user_ids = [m.user_id for m in members]
    # 从房间配置构建角色池
    configs = db.query(RoomRoleConfig).filter_by(room_id=game.room_id).all()
    role_pool = []
    for rc in configs:
        role_pool.extend([rc.role.key] * rc.count)
    # 其余补村民
    while len(role_pool) < len(user_ids):
        role_pool.append("villager")
    import random
    random.shuffle(user_ids); random.shuffle(role_pool)
    key_to_id = {r.key: r.id for r in db.query(Role).all()}
    for uid, rkey in zip(user_ids, role_pool):
        db.add(PlayerState(game_id=game.id, user_id=uid, role_id=key_to_id[rkey], alive=True, meta={}))
    db.commit()

def next_phase(db: Session, game_id: int, to_type: str, seconds: int = 120) -> dict:
    last = db.query(Phase).filter_by(game_id=game_id).order_by(Phase.number.desc()).first()
    number = 1 if not last else last.number + 1
    from datetime import datetime, timedelta
    ends = datetime.utcnow() + timedelta(seconds=seconds)
    db.add(Phase(game_id=game_id, number=number, type=to_type, ends_at=ends))
    db.commit()
    return {"deadline": ends}
