from flask import Flask, request, render_template_string
import json, os

app = Flask(__name__)
CFG_PATH = "/userapp/picoclaw/config.json"

TPL = """
<!DOCTYPE html>
<html>
<head>
    <title>PicoClaw Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; background: #080816; color: #e6ebff; padding: 20px; }
        .card { background: #12142e; padding: 20px; border-radius: 10px; border: 1px solid #00b9ff; }
        input, select { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; border: none; }
        button { background: #00b9ff; color: white; border: none; padding: 10px 20px; border-radius: 5px; width: 100%; cursor: pointer; }
        .msg { color: #00d26e; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>PicoClaw Setup</h2>
        <form method="POST">
            <label>AI Profile:</label>
            <select name="profile">
                <option value="claude">Claude (Anthropic)</option>
                <option value="gemini">Gemini (Google)</option>
                <option value="openai">OpenAI</option>
            </select>
            <label>API Key (Saved to device):</label>
            <input type="password" name="api_key" placeholder="sk-...">
            <button type="submit">Save Settings</button>
        </form>
        {% if msg %}<div class="msg">{{ msg }}</div>{% endif %}
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
@app.route("/picoclaw_login", methods=["GET", "POST"])
def index():
    msg = None
    if request.method == "POST":
        prof = request.form.get("profile")
        key = request.form.get("api_key")
        
        cfg = {}
        if os.path.exists(CFG_PATH):
            try:
                with open(CFG_PATH) as f: cfg = json.load(f)
            except: pass
        
        cfg["profile"] = prof
        if key:
            # Simple saving for now. In a real app we'd put this in the right profile file.
            cfg["last_key"] = key
            
        with open(CFG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        msg = "Settings saved! You can close this page."
        
    return render_template_string(TPL, msg=msg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
