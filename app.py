
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, random, string
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

DB = os.path.join(os.path.dirname(__file__), "app.db")

PACKAGES = [
    ("500 điểm", "50 điểm"),
    ("1.000 điểm", "100 điểm"),
    ("3.000 điểm", "300 điểm"),
    ("5.000 điểm", "500 điểm"),
    ("10.000 điểm", "1.000 điểm"),
    ("20.000 điểm", "2.000 điểm"),
]

PRODUCTS = [
    ("Nước hoa Rose Élégance","Nước hoa nữ"),
    ("Serum Vitamin C","Chăm sóc da"),
    ("Son Velvet Matte","Trang điểm"),
    ("Kem dưỡng Glow Cream","Chăm sóc da"),
    ("Nước hoa Floral Bloom","Nước hoa nữ"),
    ("Sữa rửa mặt Gentle Clean","Làm sạch da"),
    ("Son tint Cherry Kiss","Trang điểm"),
    ("Nước hoa Rouge Passion","Nước hoa"),
    ("Mặt nạ Aqua Mask","Chăm sóc da"),
    ("Kem chống nắng Daily UV","Bảo vệ da"),
]

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
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
    # Tương thích với database cũ nếu đã chạy các bản trước.
    cols = [r[1] for r in c.execute("PRAGMA table_info(access_codes)").fetchall()]
    if "assigned_user_id" not in cols:
        c.execute("ALTER TABLE access_codes ADD COLUMN assigned_user_id INTEGER")
    c.commit()
    c.close()

def current_user():
    uid = session.get("uid")
    if not uid: return None
    c = conn()
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    c.close()
    return u

@app.route("/", methods=["GET"])
def index():
    if current_user():
        return redirect(url_for("packages"))
    return render_template("auth.html")

@app.post("/register")
def register():
    name = request.form.get("name","").strip()
    phone = request.form.get("phone","").strip()
    password = request.form.get("password","")
    if not name or not phone or not password:
        flash("Vui lòng nhập đầy đủ thông tin.", "error")
        return redirect(url_for("index"))
    c = conn()
    try:
        c.execute("INSERT INTO users(name,phone,password_hash) VALUES(?,?,?)",
                  (name, phone, generate_password_hash(password)))
        c.commit()
        flash("Bạn đã đăng ký thành công!", "success")
    except sqlite3.IntegrityError:
        flash("Số điện thoại này đã được đăng ký.", "error")
    finally:
        c.close()
    return redirect(url_for("index"))

@app.post("/login")
def login():
    phone = request.form.get("phone","").strip()
    password = request.form.get("password","")
    c = conn()
    u = c.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    c.close()
    if not u or not check_password_hash(u["password_hash"], password):
        flash("Thông tin đăng nhập sai.", "error")
        return redirect(url_for("index"))
    session["uid"] = u["id"]
    return redirect(url_for("packages"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/packages")
def packages():
    u = current_user()
    if not u: return redirect(url_for("index"))
    return render_template("packages.html", packages=PACKAGES, user=u)

@app.post("/choose-package")
def choose_package():
    u = current_user()
    if not u: return redirect(url_for("index"))
    idx = int(request.form.get("package_idx","-1"))
    if idx < 0 or idx >= len(PACKAGES):
        return redirect(url_for("packages"))
    p, r = PACKAGES[idx]
    c = conn()
    c.execute("""
      INSERT INTO progress(user_id,package_name,reward_name,likes)
      VALUES(?,?,?,0)
      ON CONFLICT(user_id) DO UPDATE SET package_name=excluded.package_name,
      reward_name=excluded.reward_name
    """, (u["id"], p, r))
    c.commit(); c.close()
    return redirect(url_for("support"))

@app.route("/support", methods=["GET","POST"])
def support():
    u = current_user()
    if not u:
        return redirect(url_for("index"))

    c = conn()
    prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    c.close()

    if not prog:
        return redirect(url_for("packages"))

    if request.method == "POST":
        code = request.form.get("code","").strip().upper()
        if not code:
            flash("Vui lòng nhập mã.", "error")
            return redirect(url_for("support"))

        c = conn()
        row = c.execute("""
            SELECT * FROM access_codes
            WHERE code=?
        """, (code,)).fetchone()

        if not row:
            c.close()
            flash("Mã không hợp lệ.", "error")
            return redirect(url_for("support"))

        if row["used"]:
            c.close()
            flash("Mã này đã được sử dụng.", "error")
            return redirect(url_for("support"))

        if row["assigned_user_id"] is not None and row["assigned_user_id"] != u["id"]:
            c.close()
            flash("Mã này được cấp cho tài khoản khác.", "error")
            return redirect(url_for("support"))

        if row["package_name"] != prog["package_name"]:
            c.close()
            flash("Mã không đúng với gói điểm bạn đã chọn.", "error")
            return redirect(url_for("support"))

        # Đánh dấu dùng mã và mở nhiệm vụ trong cùng một transaction.
        c.execute("""
            UPDATE access_codes
            SET used=1, used_by=?, used_at=CURRENT_TIMESTAMP
            WHERE id=? AND used=0
        """, (u["id"], row["id"]))

        if c.total_changes < 1:
            c.rollback()
            c.close()
            flash("Mã này vừa được sử dụng.", "error")
            return redirect(url_for("support"))

        c.execute("""
            UPDATE progress
            SET access_code=?, likes=0, result_code=NULL
            WHERE user_id=?
        """, (code, u["id"]))
        c.execute("DELETE FROM task_completions WHERE user_id=?", (u["id"],))

        c.commit()
        c.close()
        return redirect(url_for("tasks"))

    return render_template("support.html", prog=prog)

@app.route("/tasks")
def tasks():
    u = current_user()
    if not u:
        return redirect(url_for("index"))

    c = conn()
    prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    if not prog or not prog["access_code"]:
        c.close()
        return redirect(url_for("support"))

    done_rows = c.execute(
        "SELECT task_id FROM task_completions WHERE user_id=? ORDER BY task_id",
        (u["id"],)
    ).fetchall()
    done_ids = {int(r["task_id"]) for r in done_rows}

    # Database completion rows are the source of truth.
    likes = len(done_ids)
    result_code = prog["result_code"]
    if likes == 10 and not result_code:
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        result_code = "KQ-" + "".join(random.choice(chars) for _ in range(6))
    c.execute(
        "UPDATE progress SET likes=?, result_code=? WHERE user_id=?",
        (likes, result_code, u["id"])
    )
    c.commit()
    prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    c.close()

    return render_template(
        "tasks.html",
        products=PRODUCTS,
        prog=prog,
        done_ids=done_ids
    )

@app.post("/like")
def like():
    u = current_user()
    if not u:
        return jsonify({"ok":False, "message":"Chưa đăng nhập."}), 401

    data = request.get_json(silent=True) or {}
    try:
        task_id = int(data.get("task_id"))
    except (TypeError, ValueError):
        return jsonify({"ok":False, "message":"Nhiệm vụ không hợp lệ."}), 400

    if task_id < 1 or task_id > len(PRODUCTS):
        return jsonify({"ok":False, "message":"Nhiệm vụ không hợp lệ."}), 400

    c = conn()
    prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    if not prog or not prog["access_code"]:
        c.close()
        return jsonify({"ok":False, "message":"Bạn chưa được mở nhiệm vụ."}), 403

    already = c.execute(
        "SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?",
        (u["id"], task_id)
    ).fetchone()

    if already:
        likes = c.execute(
            "SELECT COUNT(*) AS n FROM task_completions WHERE user_id=?",
            (u["id"],)
        ).fetchone()["n"]
        c.close()
        return jsonify({
            "ok":False,
            "already_done":True,
            "likes":likes,
            "message":"Nhiệm vụ này đã hoàn thành."
        }), 409

    try:
        c.execute(
            "INSERT INTO task_completions(user_id,task_id) VALUES(?,?)",
            (u["id"], task_id)
        )
        likes = c.execute(
            "SELECT COUNT(*) AS n FROM task_completions WHERE user_id=?",
            (u["id"],)
        ).fetchone()["n"]

        result_code = prog["result_code"]
        if likes == 10 and not result_code:
            chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            result_code = "KQ-" + "".join(random.choice(chars) for _ in range(6))

        c.execute(
            "UPDATE progress SET likes=?, result_code=? WHERE user_id=?",
            (likes, result_code, u["id"])
        )
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback()
        c.close()
        return jsonify({
            "ok":False,
            "already_done":True,
            "message":"Nhiệm vụ này đã hoàn thành."
        }), 409

    c.close()
    return jsonify({
        "ok":True,
        "task_id":task_id,
        "likes":likes,
        "result_code":result_code
    })

@app.route("/complete")
def complete():
    u = current_user()
    if not u: return redirect(url_for("index"))
    c = conn()
    prog = c.execute("SELECT * FROM progress WHERE user_id=?", (u["id"],)).fetchone()
    c.close()
    if not prog or int(prog["likes"] or 0) < 10:
        return redirect(url_for("tasks"))
    return render_template("complete.html", prog=prog)


@app.route("/cskh", methods=["GET","POST"])
def cskh_admin():
    admin_password = os.environ.get("ADMIN_PASSWORD", "2509")

    if request.method == "POST" and request.form.get("action") == "login":
        if request.form.get("password","") == admin_password:
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
            customer_id = int(request.form.get("customer_id","0"))
        except ValueError:
            customer_id = 0

        c = conn()
        customer = c.execute("""
            SELECT u.id, u.name, u.phone, p.package_name, p.reward_name
            FROM users u
            JOIN progress p ON p.user_id=u.id
            WHERE u.id=? AND p.package_name IS NOT NULL
        """, (customer_id,)).fetchone()

        if not customer:
            c.close()
            flash("Không tìm thấy khách hàng hoặc khách chưa chọn gói.", "error")
            return redirect(url_for("cskh_admin"))

        chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            code = "NV-" + "".join(random.choice(chars) for _ in range(6))
            try:
                c.execute("""
                    INSERT INTO access_codes(
                        code, package_name, reward_name, assigned_user_id
                    ) VALUES(?,?,?,?)
                """, (
                    code,
                    customer["package_name"],
                    customer["reward_name"],
                    customer["id"]
                ))
                c.commit()
                generated_code = code
                generated_for = customer
                break
            except sqlite3.IntegrityError:
                continue
        c.close()

    c = conn()
    customers = c.execute("""
        SELECT u.id, u.name, u.phone, p.package_name, p.reward_name,
               p.access_code, p.likes, p.result_code
        FROM users u
        JOIN progress p ON p.user_id=u.id
        WHERE p.package_name IS NOT NULL
        ORDER BY u.id DESC
    """).fetchall()

    codes = c.execute("""
        SELECT ac.*, u.name AS customer_name, u.phone AS customer_phone
        FROM access_codes ac
        LEFT JOIN users u ON u.id=ac.assigned_user_id
        ORDER BY ac.id DESC
        LIMIT 50
    """).fetchall()
    c.close()

    return render_template(
        "cskh_admin.html",
        customers=customers,
        codes=codes,
        generated_code=generated_code,
        generated_for=generated_for
    )

@app.get("/cskh/logout")
def cskh_logout():
    session.pop("cskh_admin", None)
    return redirect(url_for("cskh_admin"))

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
