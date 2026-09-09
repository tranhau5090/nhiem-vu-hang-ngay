from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder=".")
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

DB = os.path.join(os.path.dirname(__file__), "app.db")
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CODE_TTL_MINUTES = 10

PACKAGES = [
    ("500 điểm", "50 điểm"),
    ("1.000 điểm", "100 điểm"),
    ("3.000 điểm", "300 điểm"),
    ("5.000 điểm", "500 điểm"),
    ("10.000 điểm", "1.000 điểm"),
    ("20.000 điểm", "2.000 điểm"),
]

PRODUCTS = [
    ("Nước hoa Rose Élégance", "Nước hoa nữ"),
    ("Serum Vitamin C", "Chăm sóc da"),
    ("Son Velvet Matte", "Trang điểm"),
    ("Kem dưỡng Glow Cream", "Chăm sóc da"),
    ("Nước hoa Floral Bloom", "Nước hoa nữ"),
    ("Sữa rửa mặt Gentle Clean", "Làm sạch da"),
    ("Son tint Cherry Kiss", "Trang điểm"),
    ("Nước hoa Rouge Passion", "Nước hoa"),
    ("Mặt nạ Aqua Mask", "Chăm sóc da"),
    ("Kem chống nắng Daily UV", "Bảo vệ da"),
]


def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def today_vn():
    return datetime.now(VIETNAM_TZ).date().isoformat()


def utc_sql(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    c = conn()
    try:
        try:
            c.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass

        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS progress(
            user_id INTEGER PRIMARY KEY,
            package_name TEXT,
            reward_name TEXT,
            access_code TEXT,
            likes INTEGER DEFAULT 0,
            result_code TEXT,
            last_completed_date TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS access_codes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            package_name TEXT NOT NULL,
            reward_name TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            assigned_user_id INTEGER,
            used_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            used_at DATETIME
        );

        CREATE TABLE IF NOT EXISTS task_completions(
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, task_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)

        access_cols = [r[1] for r in c.execute("PRAGMA table_info(access_codes)").fetchall()]
        if "assigned_user_id" not in access_cols:
            c.execute("ALTER TABLE access_codes ADD COLUMN assigned_user_id INTEGER")
        if "expires_at" not in access_cols:
            c.execute("ALTER TABLE access_codes ADD COLUMN expires_at DATETIME")

        progress_cols = [r[1] for r in c.execute("PRAGMA table_info(progress)").fetchall()]
        if "last_completed_date" not in progress_cols:
            c.execute("ALTER TABLE progress ADD COLUMN last_completed_date TEXT")

        c.commit()
    finally:
        c.close()


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    c = conn()
    try:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        c.close()


def get_progress(user_id):
    c = conn()
    try:
        return c.execute("SELECT * FROM progress WHERE user_id=?", (user_id,)).fetchone()
    finally:
        c.close()


def completed_today(user_id):
    prog = get_progress(user_id)
    return bool(prog and prog["last_completed_date"] == today_vn())


def make_code(prefix):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return prefix + "-" + "".join(random.choice(chars) for _ in range(6))


@app.get("/")
def index():
    if current_user():
        return redirect(url_for("packages"))
    return render_template("auth.html")


@app.post("/register")
def register():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not phone or not password or not confirm_password:
        flash("Vui lòng nhập đầy đủ thông tin.", "error")
        return redirect(url_for("index"))
    if password != confirm_password:
        flash("Mật khẩu nhập lại không khớp.", "error")
        return redirect(url_for("index"))

    c = conn()
    try:
        c.execute(
            "INSERT INTO users(name, phone, password_hash) VALUES(?,?,?)",
            (name, phone, generate_password_hash(password)),
        )
        c.commit()
        flash("Bạn đã đăng ký thành công!", "success")
    except sqlite3.IntegrityError:
        c.rollback()
        flash("Số điện thoại này đã được đăng ký.", "error")
    except sqlite3.Error:
        c.rollback()
        flash("Hệ thống đang bận. Vui lòng thử lại.", "error")
    finally:
        c.close()
    return redirect(url_for("index"))


@app.post("/login")
def login():
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    c = conn()
    try:
        u = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    finally:
        c.close()

    if not u or not check_password_hash(u["password_hash"], password):
        flash("Thông tin đăng nhập sai.", "error")
        return redirect(url_for("index"))

    session["uid"] = u["id"]
    if completed_today(u["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))
    return redirect(url_for("packages"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/packages")
def packages():
    u = current_user()
    if not u:
        return redirect(url_for("index"))
    if completed_today(u["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))
    return render_template("packages.html", packages=PACKAGES, user=u)


@app.post("/choose-package")
def choose_package():
    u = current_user()
    if not u:
        return redirect(url_for("index"))
    if completed_today(u["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))

    try:
        idx = int(request.form.get("package_idx", "-1"))
    except (TypeError, ValueError):
        idx = -1
    if idx < 0 or idx >= len(PACKAGES):
        flash("Gói điểm không hợp lệ.", "error")
        return redirect(url_for("packages"))

    package_name, reward_name = PACKAGES[idx]
    c = conn()
    try:
        c.execute("""
            INSERT INTO progress(user_id, package_name, reward_name, access_code, likes, result_code)
            VALUES(?,?,?,NULL,0,NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                package_name=excluded.package_name,
                reward_name=excluded.reward_name,
                access_code=NULL,
                likes=0,
                result_code=NULL
        """, (u["id"], package_name, reward_name))
        c.execute("DELETE FROM task_completions WHERE user_id=?", (u["id"],))
        c.commit()
    except sqlite3.Error:
        c.rollback()
        flash("Không thể lưu gói lúc này. Vui lòng thử lại.", "error")
        return redirect(url_for("packages"))
    finally:
        c.close()
    return redirect(url_for("support"))


@app.route("/support", methods=["GET", "POST"])
def support():
    u = current_user()
    if not u:
        return redirect(url_for("index"))
    if completed_today(u["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))

    c = conn()
    try:
        prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    finally:
        c.close()
    if not prog:
        return redirect(url_for("packages"))

    if request.method == "GET":
        return render_template("support.html", prog=prog)

    code = request.form.get("code", "").strip().upper()
    if not code:
        flash("Vui lòng nhập mã.", "error")
        return redirect(url_for("support"))

    c = conn()
    try:
        row = c.execute("SELECT * FROM access_codes WHERE code=?", (code,)).fetchone()
        if not row:
            flash("Mã không hợp lệ.", "error")
            return redirect(url_for("support"))
        if row["used"]:
            flash("Mã này đã được sử dụng.", "error")
            return redirect(url_for("support"))
        if row["expires_at"] is None or c.execute(
            "SELECT CASE WHEN datetime(?) <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS expired",
            (row["expires_at"],),
        ).fetchone()["expired"]:
            flash("Mã đã hết hạn. Vui lòng liên hệ Chăm sóc khách hàng để nhận mã mới.", "error")
            return redirect(url_for("support"))
        if row["assigned_user_id"] is not None and row["assigned_user_id"] != u["id"]:
            flash("Mã này được cấp cho tài khoản khác.", "error")
            return redirect(url_for("support"))
        if row["package_name"] != prog["package_name"]:
            flash("Mã không đúng với gói điểm bạn đã chọn.", "error")
            return redirect(url_for("support"))

        cur = c.execute("""
            UPDATE access_codes
            SET used=1, used_by=?, used_at=CURRENT_TIMESTAMP
            WHERE id=? AND used=0 AND expires_at IS NOT NULL AND datetime(expires_at) > CURRENT_TIMESTAMP
        """, (u["id"], row["id"]))
        if cur.rowcount != 1:
            c.rollback()
            flash("Mã đã hết hạn hoặc vừa được sử dụng. Vui lòng nhận mã mới.", "error")
            return redirect(url_for("support"))

        c.execute("""
            UPDATE progress SET access_code=?, likes=0, result_code=NULL WHERE user_id=?
        """, (code, u["id"]))
        c.execute("DELETE FROM task_completions WHERE user_id=?", (u["id"],))
        c.commit()
    except sqlite3.Error:
        c.rollback()
        flash("Hệ thống đang bận. Vui lòng thử nhập mã lại sau vài giây.", "error")
        return redirect(url_for("support"))
    finally:
        c.close()

    return redirect(url_for("tasks"))


@app.get("/tasks")
def tasks():
    u = current_user()
    if not u:
        return redirect(url_for("index"))
    if completed_today(u["id"]):
        return redirect(url_for("complete"))

    c = conn()
    try:
        prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
        if not prog or not prog["access_code"]:
            return redirect(url_for("support"))

        done_rows = c.execute(
            "SELECT task_id FROM task_completions WHERE user_id=? ORDER BY task_id",
            (u["id"],),
        ).fetchall()
        done_ids = {int(r["task_id"]) for r in done_rows}
        likes = min(len(done_ids), 10)
        result_code = prog["result_code"]

        if likes >= 10:
            if not result_code:
                result_code = make_code("KQ")
            c.execute("""
                UPDATE progress SET likes=10, result_code=?, last_completed_date=? WHERE user_id=?
            """, (result_code, today_vn(), u["id"]))
            c.commit()
            session["show_result_code"] = True
            return redirect(url_for("complete"))

        c.execute("UPDATE progress SET likes=? WHERE user_id=?", (likes, u["id"]))
        c.commit()
        prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    except sqlite3.Error:
        c.rollback()
        flash("Không tải được nhiệm vụ. Vui lòng thử lại.", "error")
        return redirect(url_for("support"))
    finally:
        c.close()

    return render_template("tasks.html", products=PRODUCTS, prog=prog, done_ids=done_ids)


@app.post("/like")
def like():
    u = current_user()
    if not u:
        return jsonify({"ok": False, "message": "Chưa đăng nhập."}), 401
    if completed_today(u["id"]):
        return jsonify({"ok": False, "daily_limit": True, "message": "Bạn đã hoàn thành nhiệm vụ hôm nay. Vui lòng quay lại vào ngày mai."}), 403

    data = request.get_json(silent=True) or {}
    try:
        task_id = int(data.get("task_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Nhiệm vụ không hợp lệ."}), 400
    if task_id < 1 or task_id > len(PRODUCTS):
        return jsonify({"ok": False, "message": "Nhiệm vụ không hợp lệ."}), 400

    c = conn()
    try:
        prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
        if not prog or not prog["access_code"]:
            return jsonify({"ok": False, "message": "Bạn chưa được mở nhiệm vụ."}), 403

        already = c.execute(
            "SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?",
            (u["id"], task_id),
        ).fetchone()
        if already:
            likes = c.execute("SELECT COUNT(*) AS n FROM task_completions WHERE user_id=?", (u["id"],)).fetchone()["n"]
            return jsonify({"ok": False, "already_done": True, "likes": likes, "message": "Nhiệm vụ này đã hoàn thành."}), 409

        c.execute("INSERT INTO task_completions(user_id, task_id) VALUES(?,?)", (u["id"], task_id))
        likes = c.execute("SELECT COUNT(*) AS n FROM task_completions WHERE user_id=?", (u["id"],)).fetchone()["n"]
        result_code = prog["result_code"]

        if likes >= 10:
            likes = 10
            if not result_code:
                result_code = make_code("KQ")
            c.execute("""
                UPDATE progress SET likes=10, result_code=?, last_completed_date=? WHERE user_id=?
            """, (result_code, today_vn(), u["id"]))
            session["show_result_code"] = True
        else:
            c.execute("UPDATE progress SET likes=? WHERE user_id=?", (likes, u["id"]))
        c.commit()
        return jsonify({"ok": True, "task_id": task_id, "likes": likes, "result_code": result_code})
    except sqlite3.IntegrityError:
        c.rollback()
        return jsonify({"ok": False, "already_done": True, "message": "Nhiệm vụ này đã hoàn thành."}), 409
    except sqlite3.Error:
        c.rollback()
        return jsonify({"ok": False, "message": "Máy chủ đang bận. Vui lòng thử lại."}), 503
    finally:
        c.close()


@app.get("/complete")
def complete():
    u = current_user()
    if not u:
        return redirect(url_for("index"))
    c = conn()
    try:
        prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    finally:
        c.close()
    if not prog or int(prog["likes"] or 0) < 10:
        return redirect(url_for("tasks"))
    show_result_code = session.pop("show_result_code", False)
    return render_template("complete.html", prog=prog, show_result_code=show_result_code)


@app.route("/cskh", methods=["GET", "POST"])
def cskh_admin():
    admin_password = os.environ.get("ADMIN_PASSWORD", "2509")

    if request.method == "POST" and request.form.get("action") == "login":
        if request.form.get("password", "") == admin_password:
            session["cskh_admin"] = True
        else:
            flash("Mật khẩu CSKH không đúng.", "error")
        return redirect(url_for("cskh_admin"))

    if not session.get("cskh_admin"):
        return render_template("cskh_login.html")

    generated_code = None
    generated_for = None

    if request.method == "POST" and request.form.get("action") == "generate":
        try:
            customer_id = int(request.form.get("customer_id", "0"))
        except ValueError:
            customer_id = 0

        c = conn()
        try:
            customer = c.execute("""
                SELECT u.id, u.name, u.phone, p.package_name, p.reward_name, p.last_completed_date
                FROM users u JOIN progress p ON p.user_id=u.id
                WHERE u.id=? AND p.package_name IS NOT NULL
            """, (customer_id,)).fetchone()

            if not customer:
                flash("Không tìm thấy khách hàng hoặc khách chưa chọn gói.", "error")
                return redirect(url_for("cskh_admin"))
            if customer["last_completed_date"] == today_vn():
                flash("Tài khoản này đã hoàn thành lượt nhiệm vụ hôm nay. Ngày mai mới có thể cấp mã mới.", "error")
                return redirect(url_for("cskh_admin"))

            expires_at = utc_sql(datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES))
            while True:
                code = make_code("NV")
                try:
                    c.execute("""
                        INSERT INTO access_codes(code, package_name, reward_name, assigned_user_id, expires_at)
                        VALUES(?,?,?,?,?)
                    """, (code, customer["package_name"], customer["reward_name"], customer["id"], expires_at))
                    c.commit()
                    generated_code = code
                    generated_for = customer
                    break
                except sqlite3.IntegrityError:
                    c.rollback()
                    continue
        except sqlite3.Error:
            c.rollback()
            flash("Không thể tạo mã lúc này. Vui lòng thử lại.", "error")
            return redirect(url_for("cskh_admin"))
        finally:
            c.close()

    c = conn()
    try:
        customers = c.execute("""
            SELECT u.id, u.name, u.phone, p.package_name, p.reward_name, p.access_code,
                   p.likes, p.result_code, p.last_completed_date
            FROM users u JOIN progress p ON p.user_id=u.id
            WHERE p.package_name IS NOT NULL ORDER BY u.id DESC
        """).fetchall()
        codes = c.execute("""
            SELECT ac.*, u.name AS customer_name, u.phone AS customer_phone,
                   CASE WHEN ac.used=0 AND ac.expires_at IS NOT NULL AND datetime(ac.expires_at) <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS expired
            FROM access_codes ac LEFT JOIN users u ON u.id=ac.assigned_user_id
            ORDER BY ac.id DESC LIMIT 50
        """).fetchall()
    finally:
        c.close()

    return render_template("cskh_admin.html", customers=customers, codes=codes, generated_code=generated_code, generated_for=generated_for)


@app.get("/cskh/logout")
def cskh_logout():
    session.pop("cskh_admin", None)
    return redirect(url_for("cskh_admin"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
