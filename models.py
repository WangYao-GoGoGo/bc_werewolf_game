from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from flask_login import UserMixin

Base = declarative_base()

class User(UserMixin, Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    nickname = Column(String(64), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    def get_id(self): return str(self.id)

class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    max_players = Column(Integer, default=8)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User")

class Membership(Base):
    __tablename__ = "memberships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)

class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished = Column(Boolean, default=False)

class Phase(Base):
    __tablename__ = "phases"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    number = Column(Integer, nullable=False)
    type = Column(String(16), nullable=False)  # night/day
    ends_at = Column(DateTime, nullable=True)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    key = Column(String(32), unique=True, nullable=False)
    name = Column(String(64), nullable=False)
    description = Column(String(255), default="")
    camp = Column(String(16), default="villager")  # villager / werewolf / neutral

class RoomRoleConfig(Base):
    __tablename__ = "room_role_configs"
    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    count = Column(Integer, default=0)
    role = relationship("Role")
    room = relationship("Room")

class PlayerState(Base):
    __tablename__ = "player_states"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    alive = Column(Boolean, default=True)
    meta = Column(JSON, default=dict)

class Action(Base):
    __tablename__ = "actions"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    phase_number = Column(Integer, nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(32), nullable=False)  # wolf_kill, seer_peek, etc.
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
