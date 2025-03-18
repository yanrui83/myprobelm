from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import os
import sqlite3
import requests
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.utils import get_column_letter
from io import BytesIO

# Initialize Flask app
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "static/uploads/"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ✅ Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = "7873585575:AAEmoQPwlnJdcfIjTLsCcuW6EqJW46GB9B8"  # Replace with your bot token
TELEGRAM_CHAT_ID = "-4650560329"  # Replace with your chat/group/channel ID

# ✅ Function to send Telegram messages (with image support)
def send_telegram_message(category, description, priority, image_filename=None):
    message = f"🚨 *New Problem Reported* 🚨\n\n📌 *Category:* {category}\n📝 *Description:* {description}\n⚠️ *Priority:* {priority}"
    
    url_text = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    try:
        # If an image is provided, send the image first
        if image_filename:
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
            if os.path.exists(image_path):
                with open(image_path, "rb") as image_file:
                    files = {"photo": image_file}
                    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": message, "parse_mode": "Markdown"}
                    response = requests.post(url_photo, data=data, files=files)
                    if response.status_code == 200:
                        print("✅ Image sent successfully to Telegram")
                    else:
                        print(f"❌ Error sending image: {response.text}")
        
        else:
            # If no image, send text only
            data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
            response = requests.post(url_text, data=data)
            if response.status_code == 200:
                print("✅ Text message sent successfully to Telegram")
            else:
                print(f"❌ Error sending message: {response.text}")

    except Exception as e:
        print(f"❌ Telegram API Error: {e}")

# ✅ Initialize Database
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Create table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS problems (
                 id INTEGER PRIMARY KEY, category TEXT, description TEXT, 
                 image TEXT, date TEXT, comment TEXT, progress TEXT, priority TEXT DEFAULT 'Medium')''')

    # Check if 'priority' column exists, if not, add it
    c.execute("PRAGMA table_info(problems)")
    columns = [col[1] for col in c.fetchall()]

    if "priority" not in columns:
        c.execute("ALTER TABLE problems ADD COLUMN priority TEXT DEFAULT 'Medium'")

    conn.commit()
    conn.close()

init_db()

# ✅ Home Page (Form + Problem List)
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        category = request.form["category"]
        description = request.form["description"]
        comment = request.form["comment"]
        progress = request.form["progress"]
        priority = request.form["priority"]
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Handle Image Upload
        image_filename = None
        if "image" in request.files:
            image = request.files["image"]
            if image.filename:
                image_filename = image.filename
                image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

        # Save to Database
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO problems (category, description, image, date, comment, progress, priority) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (category, description, image_filename, date, comment, progress, priority))
        conn.commit()
        conn.close()

        # ✅ Send Telegram Notification (now with image support)
        send_telegram_message(category, description, priority, image_filename)

        return redirect(url_for("index"))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM problems ORDER BY id DESC")
    problems = c.fetchall()
    conn.close()
    return render_template("index.html", problems=problems)

# ✅ Edit Page
@app.route("/edit/<int:id>", methods=["GET"])
def edit(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM problems WHERE id = ?", (id,))
    problem = c.fetchone()
    conn.close()

    if not problem:
        return "Problem not found", 404

    return render_template("edit.html", problem=problem)

# ✅ Update Record
@app.route("/update/<int:id>", methods=["POST"])
def update(id):
    category = request.form["category"]
    description = request.form["description"]
    comment = request.form["comment"]
    progress = request.form["progress"]
    priority = request.form["priority"]

    # Handle Image Upload
    image_filename = None
    if "image" in request.files:
        image = request.files["image"]
        if image.filename:
            image_filename = image.filename
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if image_filename:
        c.execute("UPDATE problems SET category = ?, description = ?, image = ?, comment = ?, progress = ?, priority = ? WHERE id = ?",
                  (category, description, image_filename, comment, progress, priority, id))
    else:
        c.execute("UPDATE problems SET category = ?, description = ?, comment = ?, progress = ?, priority = ? WHERE id = ?",
                  (category, description, comment, progress, priority, id))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

# ✅ Update Progress via AJAX
@app.route("/update_progress/<int:id>", methods=["POST"])
def update_progress(id):
    try:
        new_progress = request.form.get("progress")
        
        if not new_progress:
            print(f"❌ [Error] Missing 'progress' field in request for ID {id}")
            return jsonify({"error": "Missing progress value"}), 400  # Bad request

        print(f"🔄 [Debug] Received progress update request for ID {id}: {new_progress}")

        # Update the database
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("UPDATE problems SET progress = ? WHERE id = ?", (new_progress, id))
        conn.commit()
        conn.close()

        print(f"✅ [Success] Updated progress for ID {id} to {new_progress}")
        return jsonify({"message": "Progress updated successfully!", "progress": new_progress})

    except Exception as e:
        print(f"❌ [Critical Error] Failed to update progress: {e}")
        return jsonify({"error": str(e)}), 500  # Internal server error


# ✅ Delete a Problem
@app.route("/delete/<int:id>")
def delete(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM problems WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("index"))

# ✅ Export to Excel (with images)
@app.route("/export")
def export():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM problems")
    problems = c.fetchall()
    conn.close()

    # Create an in-memory workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Problem Report"

    headers = ["ID", "Category", "Description", "Image", "Date", "Comment", "Progress", "Priority"]
    ws.append(headers)

    for row_index, problem in enumerate(problems, start=2):
        ws.append([problem[0], problem[1], problem[2], "", problem[4], problem[5], problem[6], problem[7]])

    # Save the file in memory
    output = BytesIO()
    wb.save(output)
    output.seek(0)  # Move pointer back to the beginning

    return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="problem_report.xlsx")

# ✅ Dashboard Data API
@app.route("/dashboard_data")
def dashboard_data():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Total number of problems
    c.execute("SELECT COUNT(*) FROM problems")
    total_problems = c.fetchone()[0]

    # Problems by category
    c.execute("SELECT category, COUNT(*) FROM problems GROUP BY category")
    categories = {row[0]: row[1] for row in c.fetchall()}

    # Problems by progress
    c.execute("SELECT progress, COUNT(*) FROM problems GROUP BY progress")
    progress_counts = {row[0]: row[1] for row in c.fetchall()}

    # Problems by priority
    c.execute("SELECT priority, COUNT(*) FROM problems GROUP BY priority")
    priority_counts = {row[0]: row[1] for row in c.fetchall()}

    conn.close()

    return jsonify({
        "total_problems": total_problems,
        "categories": categories,
        "progress_counts": progress_counts,
        "priority_counts": priority_counts
    })

# ✅ Dashboard Page
@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# ✅ Run the app on local network
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

