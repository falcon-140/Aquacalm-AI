# services/convo_memory.py
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import datetime
import json

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = sa.Column(sa.Integer, primary_key=True)
    session_id = sa.Column(sa.String, index=True)
    role = sa.Column(sa.String)
    text = sa.Column(sa.Text)
    created_at = sa.Column(sa.DateTime, default=datetime.datetime.utcnow)

class Session(Base):
    __tablename__ = "sessions"
    id = sa.Column(sa.String, primary_key=True)
    user_name = sa.Column(sa.String)
    meta = sa.Column(sa.Text, default="{}")

class ConversationStore:
    def __init__(self, db_url="sqlite:///convo_memory.db"):
        self.engine = sa.create_engine(db_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def create_session(self, sid, user_name):
        s = self.Session()
        sess = Session(id=sid, user_name=user_name, meta="{}")
        s.add(sess)
        s.commit()
        s.close()

    def append_message(self, sid, role, text):
        s = self.Session()
        m = Message(session_id=sid, role=role, text=text)
        s.add(m)
        s.commit()
        s.close()

    def get_session(self, sid):
        s = self.Session()
        sess = s.query(Session).filter_by(id=sid).first()
        s.close()
        return sess

    def build_prompt(self, sid, user_text):
        # Build a prompt with limited recent history
        s = self.Session()
        msgs = s.query(Message).filter(Message.session_id==sid).order_by(Message.created_at.desc()).limit(8).all()
        s.close()
        # reverse for chronological
        msgs = list(reversed(msgs))
        # system guidance
        system = self.system_prompt()
        convo = "\n".join([f"{m.role.capitalize()}: {m.text}" for m in msgs])
        prompt = f"{convo}\nUser: {user_text}"
        return prompt

    def system_prompt(self):
        return (
            """You are a compassionate, calming psychotherapy-style conversational assistant. 
At the start of the session, you should gently clarify once that you are not a licensed therapist or medical professional. 
After that, respond naturally, empathetically, and conversationally — without repeating the disclaimer again.

Your tone should be warm, validating, and concise. Encourage reflection but keep replies short (2–4 sentences max).
"""
        )
