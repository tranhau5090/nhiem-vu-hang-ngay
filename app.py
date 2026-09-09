from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import random
import sqlite3
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


def db():
    connection = sqlite3.connect(DB, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def today_vn():
    return datetime.now(VIETNAM_TZ).date().isoformat()


def utc_sql(dt=None):
    value = dt or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def add_column_if_missing(connection, table, column, definition):
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    connection = db()
    try:
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            pass

        connection.executescript(
            """
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
            """
        )

        # Tương thích với database cũ đã tồn tại từ các phiên bản trước.
        migrations = [
            ("progress", "package_name", "TEXT"),
            ("progress", "reward_name", "TEXT"),
            ("progress", "access_code", "TEXT"),
            ("progress", "likes", "INTEGER DEFAULT 0"),
            ("progress", "result_code", "TEXT"),
            ("progress", "last_completed_date", "TEXT"),
            ("access_codes", "package_name", "TEXT"),
            ("access_codes", "reward_name", "TEXT"),
            ("access_codes", "used", "INTEGER DEFAULT 0"),
            ("access_codes", "assigned_user_id", "INTEGER"),
            ("access_codes", "used_by", "INTEGER"),
            ("access_codes", "created_at", "DATETIME"),
            ("access_codes", "expires_at", "DATETIME"),
            ("access_codes", "used_at", "DATETIME"),
        ]
        for table, column, definition in migrations:
            try:
                add_column_if_missing(connection, table, column, definition)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise

        connection.commit()
    finally:
        connection.close()


def current_user():
    user_id = session.get("uid")
    if not user_id:
        return None
    connection = db()
    try:
        return connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    finally:
        connection.close()


def get_progress(user_id):
    connection = db()
    try:
        return connection.execute("SELECT * FROM progress WHERE user_id=?", (user_id,)).fetchone()
    finally:
        connection.close()


def completed_today(user_id):
    progress = get_progress(user_id)
    return bool(progress and progress["last_completed_date"] == today_vn())


def make_code(prefix):
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return prefix + "-" + "".join(random.choice(chars) for _ in range(6))


def code_is_expired(value):
    if not value:
        return True
    try:
        expires = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) >= expires
    except (TypeError, ValueError):
        return True


@app.errorhandler(500)
def handle_server_error(error):
    app.logger.exception("Unhandled server error: %s", error)
    flash("Hệ thống vừa gặp lỗi. Vui lòng thử lại sau vài giây.", "error")
    if session.get("uid"):
        return redirect(url_for("packages"))
    return redirect(url_for("index"))


@app.get("/health")
def health():
    try:
        connection = db()
        connection.execute("SELECT 1").fetchone()
        connection.close()
        return jsonify({"ok": True})
    except Exception:
        return jsonify({"ok": False}), 500


@app.get("/")
def index():
    if current_user():
        return redirect(url_for("packages"))
    return render_template("auth.html")


@app.get("/about")
def about():
    return render_template("about.html")


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.post("/register")
def register():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not phone or not password or not confirm_password:
        flash("Vui lòng nhập đầy đủ thông tin.", "error")
        return redirect(url_for("index"))
    if len(password) < 6:
        flash("Mật khẩu phải có ít nhất 6 ký tự.", "error")
        return redirect(url_for("index"))
    if password != confirm_password:
        flash("Mật khẩu nhập lại không khớp.", "error")
        return redirect(url_for("index"))

    connection = db()
    try:
        connection.execute(
            "INSERT INTO users(name, phone, password_hash) VALUES(?,?,?)",
            (name, phone, generate_password_hash(password)),
        )
        connection.commit()
        flash("Bạn đã đăng ký thành công!", "success")
    except sqlite3.IntegrityError:
        connection.rollback()
        flash("Số điện thoại này đã được đăng ký.", "error")
    except sqlite3.Error:
        connection.rollback()
        flash("Hệ thống đang bận. Vui lòng thử lại.", "error")
    finally:
        connection.close()
    return redirect(url_for("index"))


@app.post("/login")
def login():
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    connection = db()
    try:
        user = connection.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    finally:
        connection.close()

    if not user or not check_password_hash(user["password_hash"], password):
        flash("Thông tin đăng nhập sai.", "error")
        return redirect(url_for("index"))

    session["uid"] = user["id"]
    if completed_today(user["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))
    return redirect(url_for("packages"))


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.get("/packages")
def packages():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    if completed_today(user["id"]):
        session.pop("show_result_code", None)
        return redirect(url_for("complete"))
    return render_template("packages.html", packages=PACKAGES, user=user)


@app.post("/choose-package")
def choose_package():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    if completed_today(user["id"]):
        return redirect(url_for("complete"))

    try:
        package_index = int(request.form.get("package_idx", "-1"))
    except (TypeError, ValueError):
        package_index = -1

    if package_index < 0 or package_index >= len(PACKAGES):
        flash("Gói điểm không hợp lệ.", "error")
        return redirect(url_for("packages"))

    package_name, reward_name = PACKAGES[package_index]
    connection = db()
    try:
        existing = connection.execute("SELECT user_id FROM progress WHERE user_id=?", (user["id"],)).fetchone()
        if existing:
            connection.execute(
                "UPDATE progress SET package_name=?,reward_name=?,access_code=NULL,likes=0,result_code=NULL WHERE user_id=?",
                (package_name, reward_name, user["id"]),
            )
        else:
            connection.execute(
                "INSERT INTO progress(user_id,package_name,reward_name,access_code,likes,result_code,last_completed_date) VALUES(?,?,?,NULL,0,NULL,NULL)",
                (user["id"], package_name, reward_name),
            )
        connection.execute("DELETE FROM task_completions WHERE user_id=?", (user["id"],))
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        flash("Không thể lưu gói lúc này. Vui lòng thử lại.", "error")
        return redirect(url_for("packages"))
    finally:
        connection.close()

    return redirect(url_for("support"))


@app.route("/support", methods=["GET", "POST"])
def support():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    if completed_today(user["id"]):
        return redirect(url_for("complete"))

    progress = get_progress(user["id"])
    if not progress or not progress["package_name"]:
        return redirect(url_for("packages"))

    if request.method == "GET":
        return render_template("support.html", prog=progress)

    code = request.form.get("code", "").strip().upper()
    if not code:
        flash("Vui lòng nhập mã.", "error")
        return redirect(url_for("support"))

    connection = db()
    try:
        row = connection.execute("SELECT * FROM access_codes WHERE code=?", (code,)).fetchone()
        if not row:
            flash("Mã không hợp lệ.", "error")
            return redirect(url_for("support"))
        if int(row["used"] or 0) == 1:
            flash("Mã này đã được sử dụng.", "error")
            return redirect(url_for("support"))
        if row["assigned_user_id"] is not None and int(row["assigned_user_id"]) != int(user["id"]):
            flash("Mã này được cấp cho tài khoản khác.", "error")
            return redirect(url_for("support"))
        if row["package_name"] != progress["package_name"]:
            flash("Mã không đúng với gói điểm bạn đã chọn.", "error")
            return redirect(url_for("support"))
        if code_is_expired(row["expires_at"]):
            flash("Mã đã hết hạn. Vui lòng liên hệ Chăm sóc khách hàng để nhận mã mới.", "error")
            return redirect(url_for("support"))

        cursor = connection.execute(
            "UPDATE access_codes SET used=1,used_by=?,used_at=? WHERE id=? AND used=0",
            (user["id"], utc_sql(), row["id"]),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            flash("Mã vừa được sử dụng hoặc không còn hiệu lực. Vui lòng nhận mã mới.", "error")
            return redirect(url_for("support"))

        connection.execute(
            "UPDATE progress SET access_code=?,likes=0,result_code=NULL WHERE user_id=?",
            (code, user["id"]),
        )
        connection.execute("DELETE FROM task_completions WHERE user_id=?", (user["id"],))
        connection.commit()
    except sqlite3.Error as exc:
        connection.rollback()
        app.logger.exception("Code redemption database error: %s", exc)
        flash("Không thể xác nhận mã lúc này. Vui lòng thử lại sau vài giây.", "error")
        return redirect(url_for("support"))
    finally:
        connection.close()

    return redirect(url_for("tasks"))


@app.get("/tasks")
def tasks():
    user = current_user()
    if not user:
        return redirect(url_for("index"))
    if completed_today(user["id"]):
        return redirect(url_for("complete"))

    connection = db()
    try:
        progress = connection.execute("SELECT * FROM progress WHERE user_id=?", (user["id"],)).fetchone()
        if not progress or not progress["access_code"]:
            flash("Bạn cần nhập mã hợp lệ trước khi làm nhiệm vụ.", "error")
            return redirect(url_for("support"))

        completed_rows = connection.execute(
            "SELECT task_id FROM task_completions WHERE user_id=? ORDER BY task_id",
            (user["id"],),
        ).fetchall()
        done_ids = {int(row["task_id"]) for row in completed_rows}
        likes = min(len(done_ids), 10)

        if int(progress["likes"] or 0) != likes:
            connection.execute("UPDATE progress SET likes=? WHERE user_id=?", (likes, user["id"]))
            connection.commit()
            progress = connection.execute("SELECT * FROM progress WHERE user_id=?", (user["id"],)).fetchone()

        if likes >= 10:
            result_code = progress["result_code"] or make_code("KQ")
            connection.execute(
                "UPDATE progress SET likes=10,result_code=?,last_completed_date=? WHERE user_id=?",
                (result_code, today_vn(), user["id"]),
            )
            connection.commit()
            session["show_result_code"] = True
            return redirect(url_for("complete"))

        return render_template("tasks.html", products=PRODUCTS, prog=progress, done_ids=done_ids)
    except sqlite3.Error as exc:
        app.logger.exception("Tasks database error: %s", exc)
        flash("Không tải được nhiệm vụ. Vui lòng thử lại.", "error")
        return redirect(url_for("support"))
    finally:
        connection.close()


@app.post("/like")
def like():
    user = current_user()
    if not user:
        return jsonify({"ok": False, "message": "Chưa đăng nhập."}), 401
    if completed_today(user["id"]):
        return jsonify({"ok": False, "daily_limit": True, "message": "Bạn đã hoàn thành nhiệm vụ hôm nay. Vui lòng quay lại vào ngày mai."}), 403

    data = request.get_json(silent=True) or {}
    try:
        task_id = int(data.get("task_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "message": "Nhiệm vụ không hợp lệ."}), 400

    if task_id < 1 or task_id > len(PRODUCTS):
        return jsonify({"ok": False, "message": "Nhiệm vụ không hợp lệ."}), 400

    connection = db()
    try:
        progress = connection.execute("SELECT * FROM progress WHERE user_id=?", (user["id"],)).fetchone()
        if not progress or not progress["access_code"]:
            return jsonify({"ok": False, "message": "Bạn chưa được mở nhiệm vụ."}), 403

        try:
            connection.execute(
                "INSERT INTO task_completions(user_id,task_id) VALUES(?,?)",
                (user["id"], task_id),
            )
        except sqlite3.IntegrityError:
            likes = connection.execute(
                "SELECT COUNT(*) AS total FROM task_completions WHERE user_id=?",
                (user["id"],),
            ).fetchone()["total"]
            return jsonify({"ok": False, "already_done": True, "likes": min(int(likes), 10), "message": "Nhiệm vụ này đã hoàn thành."}), 409

        likes = connection.execute(
            "SELECT COUNT(*) AS total FROM task_completions WHERE user_id=?",
            (user["id"],),
        ).fetchone()["total"]
        likes = min(int(likes), 10)

        result_code = progress["result_code"]
        if likes >= 10:
            result_code = result_code or make_code("KQ")
            connection.execute(
                "UPDATE progress SET likes=10,result_code=?,last_completed_date=? WHERE user_id=?",
                (result_code, today_vn(), user["id"]),
            )
            session["show_result_code"] = True
        else:
            connection.execute("UPDATE progress SET likes=? WHERE user_id=?", (likes, user["id"]))

        connection.commit()
        return jsonify({"ok": True, "task_id": task_id, "likes": likes, "result_code": result_code})
    except sqlite3.Error as exc:
        connection.rollback()
        app.logger.exception("Like database error: %s", exc)
        return jsonify({"ok": False, "message": "Máy chủ đang bận. Vui lòng thử lại."}), 503
    finally:
        connection.close()


@app.get("/complete")
def complete():
    user = current_user()
    if not user:
        return redirect(url_for("index"))

    progress = get_progress(user["id"])
    if not progress or int(progress["likes"] or 0) < 10:
        return redirect(url_for("tasks"))

    show_result_code = session.pop("show_result_code", False)
    return render_template("complete.html", prog=progress, show_result_code=show_result_code)


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
        except (TypeError, ValueError):
            customer_id = 0

        connection = db()
        try:
            customer = connection.execute(
                """
                SELECT u.id,u.name,u.phone,p.package_name,p.reward_name,p.last_completed_date
                FROM users u JOIN progress p ON p.user_id=u.id
                WHERE u.id=? AND p.package_name IS NOT NULL
                """,
                (customer_id,),
            ).fetchone()

            if not customer:
                flash("Không tìm thấy khách hàng hoặc khách chưa chọn gói.", "error")
                return redirect(url_for("cskh_admin"))
            if customer["last_completed_date"] == today_vn():
                flash("Tài khoản này đã hoàn thành lượt nhiệm vụ hôm nay. Ngày mai mới có thể cấp mã mới.", "error")
                return redirect(url_for("cskh_admin"))

            expires_at = utc_sql(datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES))
            for _ in range(30):
                new_code = make_code("NV")
                try:
                    connection.execute(
                        "INSERT INTO access_codes(code,package_name,reward_name,assigned_user_id,expires_at) VALUES(?,?,?,?,?)",
                        (new_code, customer["package_name"], customer["reward_name"], customer["id"], expires_at),
                    )
                    connection.commit()
                    generated_code = new_code
                    generated_for = customer
                    break
                except sqlite3.IntegrityError:
                    connection.rollback()

            if not generated_code:
                flash("Không thể tạo mã mới. Vui lòng thử lại.", "error")
        except sqlite3.Error as exc:
            connection.rollback()
            app.logger.exception("Admin code generation error: %s", exc)
            flash("Không thể tạo mã lúc này. Vui lòng thử lại.", "error")
            return redirect(url_for("cskh_admin"))
        finally:
            connection.close()

    connection = db()
    try:
        customers = connection.execute(
            """
            SELECT u.id,u.name,u.phone,p.package_name,p.reward_name,p.access_code,p.likes,p.result_code,p.last_completed_date
            FROM users u JOIN progress p ON p.user_id=u.id
            WHERE p.package_name IS NOT NULL
            ORDER BY u.id DESC
            """
        ).fetchall()
        codes = connection.execute(
            """
            SELECT ac.*,u.name AS customer_name,u.phone AS customer_phone,
                   CASE WHEN ac.used=0 AND ac.expires_at IS NOT NULL AND datetime(ac.expires_at)<=CURRENT_TIMESTAMP
                        THEN 1 ELSE 0 END AS expired
            FROM access_codes ac
            LEFT JOIN users u ON u.id=ac.assigned_user_id
            ORDER BY ac.id DESC LIMIT 50
            """
        ).fetchall()
    finally:
        connection.close()

    return render_template(
        "cskh_admin.html",
        customers=customers,
        codes=codes,
        generated_code=generated_code,
        generated_for=generated_for,
    )


@app.get("/cskh/logout")
def cskh_logout():
    session.pop("cskh_admin", None)
    return redirect(url_for("cskh_admin"))


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
