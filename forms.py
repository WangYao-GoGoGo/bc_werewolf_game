from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange

class RegisterForm(FlaskForm):
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    nickname = StringField("昵称", validators=[DataRequired(), Length(min=2, max=32)])
    password = PasswordField("密码", validators=[DataRequired(), Length(min=6)])
    confirm = PasswordField("确认密码", validators=[DataRequired(), EqualTo("password")])
    submit = SubmitField("注册")

class LoginForm(FlaskForm):
    email = StringField("邮箱", validators=[DataRequired(), Email()])
    password = PasswordField("密码", validators=[DataRequired()])
    submit = SubmitField("登录")

class CreateRoomForm(FlaskForm):
    name = StringField("房间名")
    max_players = IntegerField("最大人数", validators=[NumberRange(min=5, max=20)], default=8)
    submit = SubmitField("创建房间")
