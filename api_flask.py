#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, hmac, hashlib, sqlite3, urllib.parse, random
from datetime import date, datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or "0")
DB_PATH = os.getenv("DB_PATH", "gift_roulette.db")

app = Flask(__name__)
CORS(app)
bot = Bot(BOT_TOKEN) if BOT_TOKEN else None

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def get_config(key):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    r = cur.fetchone()
    con.close()
    return r["value"] if r else ""

def ensure_user(uid):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    con.commit()
    con.close()

def refresh(uid):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT free_spins,last_free_date FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    today = date.today().isoformat()
    daily = int(get_config("daily_free_spins") or "0")
    if r and r["last_free_date"] != today:
        cur.execute("UPDATE users SET free_spins=?, last_free_date=? WHERE user_id=?",
                    (daily, today, uid))
        con.commit()
    con.close()

def load_gifts():
    g=[]
    for i in range(1,5):
        g.append({
            "idx": i,
            "name": (get_config(f"gift{i}_name") or f"هدية {i}"),
            "weight": int(get_config(f"gift{i}_weight") or 1),
            "sticker": (get_config(f"gift{i}_sticker") or "")
        })
    return g

def pick(gifts):
    t=sum(x["weight"] for x in gifts)
    r=random.randint(1,t)
    u=0
    for g in gifts:
        u+=g["weight"]
        if r<=u:
            return g
    return gifts[0]

def verify(init_data):
    parsed=dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    h=parsed.get("hash","")
    if not h: return None
    s="\n".join(f"{k}={v}" for k,v in sorted(parsed.items()) if k!="hash")
    sec=hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc=hmac.new(sec, s.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc,h): return None
    return parsed

def user_id(parsed):
    try:
        return json.loads(parsed["user"])["id"]
    except:
        return None

@app.post("/state")
def state():
    p=verify(request.json.get("initData",""))
    if not p: return jsonify(error="auth"),401
    uid=user_id(p)
    ensure_user(uid); refresh(uid)
    con=db(); cur=con.cursor()
    cur.execute("SELECT free_spins FROM users WHERE user_id=?", (uid,))
    fs=cur.fetchone()["free_spins"]; con.close()
    gifts=load_gifts()
    return jsonify(ok=True, free_spins=fs,
        required_channel=get_config("required_channel"),
        gifts=[{"name":g["name"],"weight":g["weight"]} for g in gifts])

@app.post("/spin")
def spin():
    p=verify(request.json.get("initData",""))
    if not p: return jsonify(error="auth"),401
    uid=user_id(p)
    ensure_user(uid); refresh(uid)
    con=db(); cur=con.cursor()
    cur.execute("SELECT free_spins FROM users WHERE user_id=?", (uid,))
    fs=cur.fetchone()["free_spins"]
    if fs<=0: return jsonify(error="no spins"),403
    gifts=load_gifts(); g=pick(gifts)
    cur.execute("UPDATE users SET free_spins=free_spins-1 WHERE user_id=?", (uid,))
    cur.execute("INSERT INTO spins(user_id,result_name,result_sticker,created_at) VALUES(?,?,?,?)",
                (uid,g["name"],g["sticker"],datetime.utcnow().isoformat()))
    con.commit()
    cur.execute("SELECT free_spins FROM users WHERE user_id=?", (uid,))
    fs2=cur.fetchone()["free_spins"]; con.close()
    try:
        bot.send_sticker(uid, g["sticker"])
    except: pass
    return jsonify(ok=True, free_spins=fs2, gift={"name":g["name"]}, segment_index=g["idx"]-1)

if __name__=="__main__":
    app.run()
