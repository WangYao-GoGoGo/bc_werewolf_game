from collections import Counter
from models import PlayerState, Role
from game_engine import role_by_user

def _kill(db, game_id, user_id):
    ps = db.query(PlayerState).filter_by(game_id=game_id, user_id=user_id).first()
    if ps and ps.alive:
        ps.alive = False
        db.commit()
        return True
    return False

def apply_role_effects(db, game_id, phase, actions):
    effects = {}
    for a in actions:
        ps = db.query(PlayerState).filter_by(game_id=game_id, user_id=a.actor_user_id).first()
        if not ps: continue
        role = db.get(Role, ps.role_id)
        if role.key == "seer" and a.type == "seer_peek":
            rk = role_by_user(db, game_id, a.target_user_id)
            effects.setdefault("seer", []).append({
                "actor": ps.user_id, "target": a.target_user_id,
                "is_wolf": rk in ["werewolf","white_wolf_king","wolfdog","wolf_beauty","demon"]
            })
        if role.key == "witch":
            if a.type == "witch_heal":
                effects["heal"] = a.target_user_id
            if a.type == "witch_poison":
                effects.setdefault("poison", []).append(a.target_user_id)
        if role.key == "guardian" and a.type == "guardian_protect":
            effects["guarded"] = a.target_user_id
        if role.key == "raven" and a.type == "raven_mark":
            effects.setdefault("raven_mark", []).append(a.target_user_id)
        if role.key == "cupid" and a.type == "bind_couple":
            t2 = getattr(a, "meta", None) or {}
            effects["couple"] = [a.target_user_id, t2.get("target2")]
        if role.key == "piper" and a.type == "piper_charm":
            t2 = getattr(a, "meta", None) or {}
            effects.setdefault("charmed", []).extend([a.target_user_id, t2.get("target2")])
    return effects

def resolve_night_with_roles(db, game_id, phase, actions):
    results = {}
    effects = apply_role_effects(db, game_id, phase, actions)
    # 狼人目标
    wolf_votes = [a.target_user_id for a in actions if a.type == "wolf_kill"]
    wolf_target = None
    if wolf_votes:
        c = Counter(wolf_votes)
        wolf_target, _ = c.most_common(1)[0]
    # 守卫/解救判定
    if wolf_target:
        if effects.get("guarded") == wolf_target:
            results["guarded"] = wolf_target
        elif effects.get("heal") == wolf_target:
            results["healed"] = wolf_target
        else:
            if _kill(db, game_id, wolf_target):
                results["killed"] = wolf_target
    # 女巫毒
    for t in effects.get("poison", []) or []:
        if _kill(db, game_id, t):
            results.setdefault("poisoned", []).append(t)
    # 记录情侣/魅惑（此处仅返回，真实项目应保存到关系表或 meta）
    if "couple" in effects: results["couple"] = effects["couple"]
    if "charmed" in effects: results["charmed"] = [x for x in effects["charmed"] if x]
    return results

def resolve_day_vote_with_roles(db, game_id, phase, actions):
    from game_engine import role_by_user
    tally = Counter()
    for a in actions:
        ps = db.query(PlayerState).filter_by(game_id=game_id, user_id=a.actor_user_id).first()
        rk = role_by_user(db, game_id, a.actor_user_id)
        weight = 2 if rk == "village_head" else 1
        if a.target_user_id: tally[a.target_user_id] += weight
    if not tally: return {"exiled": None}
    top, count = tally.most_common(1)[0]
    tied = [pid for pid, c in tally.items() if c == count]
    results = {}
    if len(tied) > 1:
        # 替罪羊出局
        scapegoats = [ps.user_id for ps in db.query(PlayerState).filter_by(game_id=game_id, alive=True).all()
                      if role_by_user(db, game_id, ps.user_id) == "scapegoat"]
        if scapegoats:
            _kill(db, game_id, scapegoats[0])
            results["exiled"] = scapegoats[0]
            results["scapegoat"] = True
            return results
    rk_top = role_by_user(db, game_id, top)
    if rk_top == "jester":  # 如果你后续加入小丑
        _kill(db, game_id, top)
        results["exiled"] = top
        results["win"] = "jester"
        return results
    if rk_top == "idiot":
        ps = db.query(PlayerState).filter_by(game_id=game_id, user_id=top).first()
        if not ps.meta.get("survived_once", False):
            ps.meta["survived_once"] = True
            db.commit()
            results["idiot_revealed"] = top
            results["exiled"] = None
            return results
    _kill(db, game_id, top)
    results["exiled"] = top
    return results

def death_triggers(db, game_id, dead_user_id):
    from game_engine import role_by_user
    rk = role_by_user(db, game_id, dead_user_id)
    out = {}
    if rk == "hunter":
        out["hunter_ready"] = dead_user_id
    if rk == "white_wolf_king":
        out["white_wolf_power"] = dead_user_id
    if rk == "wolf_beauty":
        # 如果实现了迷惑关系，可在此连带处死
        pass
    return out
