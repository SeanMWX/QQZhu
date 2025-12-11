import aiohttp_jinja2
import jinja2
from aiohttp import web
import configparser
import asyncio
import aiohttp
import aiosqlite
import json
import os
import time
import io
from urllib.parse import quote
from pypinyin import pinyin, Style

DEFAULT_SETTINGS = {
    "title": "歌单",
    "live_url": "https://live.bilibili.com/1825831614",
    "background_url": "/static/background.jpg",
    "singer_url": "/static/singer.jpg",
    "singer_name": "歌手名字",
    "singer_intro": "这里填写歌手介绍~",
}

class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr


class Config:
    """负责读取和管理配置文件的类。"""

    def __init__(self, filename="config.ini"):
        self.config = CaseSensitiveConfigParser()
        self.config.read(filename)

    def db_path(self):
        return self.config["database"].get("path", "instance/qqzhu.db")

    def server_port(self):
        return int(self.config["server"].get("port", 8080))

    def admin_token(self):
        return self.config["server"].get("admin_token", "")


async def create_db_connection(db_path):
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def ensure_settings_table(conn):
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    await conn.commit()


def ensure_upload_dir():
    os.makedirs("static/uploads", exist_ok=True)


def save_file_field(file_field, prefix):
    """Save aiohttp FileField to static/uploads and return web path."""
    ensure_upload_dir()
    filename = file_field.filename
    if not filename:
        return None
    ext = os.path.splitext(filename)[1]
    safe_name = f"{prefix}_{int(time.time())}{ext}"
    path_fs = os.path.join("static", "uploads", safe_name)
    with open(path_fs, "wb") as f:
        content = file_field.file.read()
        f.write(content)
    return f"/static/uploads/{safe_name}"


async def fetch_songs(conn):
    """获取歌曲列表并排序（中文优先，长度优先，拼音/字母排序）。"""
    cursor = await conn.execute(
        "SELECT id, name, artist, language, genre, url FROM songs"
    )
    rows = await cursor.fetchall()
    await cursor.close()
    songs = [dict(row) for row in rows]

    def sort_key(song):
        name = song["name"]
        language = song["language"]
        language_priority = 0 if language == "中文" else 1
        word_count = len(name)
        if language == "中文":
            name_for_sort = "".join(
                [item[0] for item in pinyin(name, style=Style.NORMAL)]
            )
        else:
            name_for_sort = name.lower()
        return (language_priority, word_count, name_for_sort)

    return sorted(songs, key=sort_key)


async def fetch_unique_languages(conn):
    cursor = await conn.execute("SELECT DISTINCT language FROM songs")
    rows = await cursor.fetchall()
    await cursor.close()
    return [row["language"] for row in rows]


async def fetch_unique_genres(conn):
    cursor = await conn.execute("SELECT DISTINCT genre FROM songs")
    rows = await cursor.fetchall()
    await cursor.close()
    return [row["genre"] for row in rows]


async def get_settings(conn):
    await ensure_settings_table(conn)
    cursor = await conn.execute("SELECT key, value FROM site_settings")
    rows = await cursor.fetchall()
    await cursor.close()
    stored = {row["key"]: row["value"] for row in rows}
    merged = DEFAULT_SETTINGS.copy()
    merged.update({k: v for k, v in stored.items() if v is not None})
    return merged


async def update_settings(conn, settings: dict):
    await ensure_settings_table(conn)
    for key, value in settings.items():
        await conn.execute(
            "INSERT INTO site_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    await conn.commit()


async def add_song(conn, name, artist, language, genre, url):
    await conn.execute(
        "INSERT INTO songs (name, artist, language, genre, url) VALUES (?, ?, ?, ?, ?)",
        (name, artist, language, genre, url),
    )
    await conn.commit()


async def update_song(conn, song_id, name, artist, language, genre, url):
    await conn.execute(
        """
        UPDATE songs
        SET name = ?, artist = ?, language = ?, genre = ?, url = ?
        WHERE id = ?
        """,
        (name, artist, language, genre, url, song_id),
    )
    await conn.commit()


async def delete_song(conn, song_id):
    await conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    await conn.commit()


async def backup_songs(conn, dest_path):
    songs = await fetch_songs(conn)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(songs, f, ensure_ascii=False, indent=2)
    return dest_path


def parse_backup_json(text: str):
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("备份格式错误：根节点应为列表")
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("备份格式错误：列表元素应为对象")
        for key in ("name", "artist", "language", "genre", "url"):
            if key not in item:
                raise ValueError(f"备份缺少必要字段: {key}")
    return data


async def restore_songs_from_data(conn, songs):
    # 清空并恢复
    await conn.execute("DELETE FROM songs")
    for s in songs:
        await add_song(
            conn,
            s.get("name", ""),
            s.get("artist", ""),
            s.get("language", ""),
            s.get("genre", ""),
            s.get("url", "-"),
        )
    await conn.commit()
    return len(songs)


def parse_backup_xlsx(data: bytes):
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise ImportError("未安装 openpyxl，无法解析 xlsx，请先安装 openpyxl")

    wb = load_workbook(io.BytesIO(data))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    required = ["歌名", "歌手", "语言", "风格", "url"]
    if header[:5] != required:
        raise ValueError(f"xlsx 表头需为：{' | '.join(required)}")
    songs = []
    for row in rows[1:]:
        if row is None:
            continue
        vals = list(row) + [""] * (5 - len(row))
        name, artist, language, genre, url = ["" if v is None else str(v) for v in vals[:5]]
        if not name and not artist:
            continue
        songs.append(
            {
                "name": name,
                "artist": artist,
                "language": language,
                "genre": genre,
                "url": url or "-",
            }
        )
    return songs


def require_admin(request, form=None):
    """Check admin token via header/query/form/cookie; redirect to login if missing."""
    token_cfg = request.app["config"].admin_token()
    if not token_cfg:
        return None
    provided = (
        request.headers.get("X-Admin-Token")
        or request.query.get("token")
        or (form.get("token") if form else None)
        or request.cookies.get("admin_token")
    )
    if provided == token_cfg:
        return provided
    next_url = quote(str(request.rel_url))
    raise web.HTTPFound(location=f"/admin/login?next={next_url}")


async def index(request):
    conn = request.app["db_conn"]
    songs = await fetch_songs(conn)
    languages = await fetch_unique_languages(conn)
    genres = await fetch_unique_genres(conn)
    settings = await get_settings(conn)
    return aiohttp_jinja2.render_template(
        "index.html",
        request,
        {"songs": songs, "languages": languages, "genres": genres, "settings": settings},
    )


async def proxy_image(request):
    image_url = request.query.get("url")
    if not image_url:
        raise web.HTTPBadRequest(text="Missing 'url' parameter")
    headers = {"Referer": "https://www.bilibili.com"}
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, headers=headers) as response:
            if response.status == 200:
                return web.Response(
                    body=await response.read(), content_type=response.headers["Content-Type"]
                )
            raise web.HTTPNotFound(text="Image not found")


async def admin_login_get(request):
    return aiohttp_jinja2.render_template(
        "admin_login.html",
        request,
        {"next": request.query.get("next", "/admin"), "message": request.query.get("message", "")},
    )


async def admin_login_post(request):
    form = await request.post()
    token_cfg = request.app["config"].admin_token()
    provided = form.get("token", "")
    next_url = form.get("next") or "/admin"
    if token_cfg and provided == token_cfg:
        resp = web.HTTPFound(location=next_url)
        resp.set_cookie("admin_token", provided, httponly=True, samesite="Lax")
        return resp
    return aiohttp_jinja2.render_template(
        "admin_login.html",
        request,
        {"next": next_url, "message": "Token 错误或未设置"},
    )


async def admin_logout(request):
    resp = web.HTTPFound(location="/admin/login")
    resp.del_cookie("admin_token")
    return resp


async def admin_page(request):
    _ = require_admin(request)
    conn = request.app["db_conn"]
    songs = await fetch_songs(conn)
    settings = await get_settings(conn)
    return aiohttp_jinja2.render_template(
        "admin.html",
        request,
        {
            "songs": songs,
            "settings": settings,
            "message": request.query.get("message", ""),
            "token": request.query.get("token", ""),
        },
    )


async def admin_action(request):
    conn = request.app["db_conn"]
    form = await request.post()
    require_admin(request, form)
    action = form.get("action")
    message = ""
    try:
        if action == "song_new":
            name = form.get("song_name", "").strip()
            artist = form.get("artist", "").strip()
            language = form.get("language", "").strip()
            genre = form.get("genre", "").strip()
            url = form.get("url", "").strip() or "-"
            await add_song(conn, name, artist, language, genre, url)
            message = "歌曲已添加"
        elif action == "song_update":
            song_id = int(form.get("song_id", 0))
            name = form.get("song_name", "").strip()
            artist = form.get("artist", "").strip()
            language = form.get("language", "").strip()
            genre = form.get("genre", "").strip()
            url = form.get("url", "").strip() or "-"
            await update_song(conn, song_id, name, artist, language, genre, url)
            message = "歌曲已更新"
        elif action == "song_delete":
            song_id = int(form.get("song_id", 0))
            await delete_song(conn, song_id)
            message = "歌曲已删除"
        elif action == "backup":
            dest = os.path.join("backup", "songs_backup.json")
            saved = await backup_songs(conn, dest)
            message = f"备份已生成: {saved}"
        elif action == "restore_backup":
            file_field = form.get("backup_file")
            try:
                if file_field and hasattr(file_field, "file") and file_field.filename:
                    filename = file_field.filename.lower()
                    if filename.endswith(".json"):
                        content = file_field.file.read().decode("utf-8")
                        songs = parse_backup_json(content)
                    elif filename.endswith(".xlsx"):
                        content = file_field.file.read()
                        songs = parse_backup_xlsx(content)
                    else:
                        raise ValueError("仅支持 .json 或 .xlsx 备份文件")
                    count = await restore_songs_from_data(conn, songs)
                    message = f"已从上传的备份恢复 {count} 首歌曲"
                else:
                    src = os.path.join("backup", "songs_backup.json")
                    if not os.path.exists(src):
                        raise FileNotFoundError(f"{src} 不存在")
                    with open(src, "r", encoding="utf-8") as f:
                        content = f.read()
                    songs = parse_backup_json(content)
                    count = await restore_songs_from_data(conn, songs)
                    message = f"已从本地备份恢复 {count} 首歌曲"
            except Exception as exc:
                message = f"恢复失败: {exc}"
        elif action == "settings":
            current_settings = await get_settings(conn)
            bg_file = form.get("background_file")
            singer_file = form.get("singer_file")
            new_settings = {
                "title": form.get("title", "").strip() or current_settings.get("title", DEFAULT_SETTINGS["title"]),
                "live_url": form.get("live_url", "").strip() or current_settings.get("live_url", DEFAULT_SETTINGS["live_url"]),
                "singer_name": form.get("singer_name", "").strip() or current_settings.get("singer_name", DEFAULT_SETTINGS["singer_name"]),
                "singer_intro": form.get("singer_intro", "").strip() or current_settings.get("singer_intro", DEFAULT_SETTINGS["singer_intro"]),
                "background_url": current_settings.get("background_url", DEFAULT_SETTINGS["background_url"]),
                "singer_url": current_settings.get("singer_url", DEFAULT_SETTINGS["singer_url"]),
            }
            if hasattr(bg_file, "file") and bg_file.filename:
                saved = save_file_field(bg_file, "bg")
                if saved:
                    new_settings["background_url"] = saved
            if hasattr(singer_file, "file") and singer_file.filename:
                saved = save_file_field(singer_file, "singer")
                if saved:
                    new_settings["singer_url"] = saved
            await update_settings(conn, new_settings)
            message = "站点信息已更新"
        else:
            message = "未知操作"
    except Exception as exc:
        message = f"操作失败: {exc}"

    params = [f"message={quote(message)}"]
    return web.HTTPFound(location="/admin?" + "&".join(params))


async def init_app():
    app = web.Application(client_max_size=10 * 1024 * 1024)
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("templates"))

    app.router.add_static("/static/", path="static", name="static")
    app.router.add_get("/proxy-image", proxy_image)

    config = Config("config.ini")
    db_conn = await create_db_connection(config.db_path())
    app["db_conn"] = db_conn
    app["config"] = config

    app.router.add_get("/", index)
    app.router.add_get("/admin/login", admin_login_get)
    app.router.add_post("/admin/login", admin_login_post)
    app.router.add_get("/admin/logout", admin_logout)
    app.router.add_get("/admin", admin_page)
    app.router.add_post("/admin/action", admin_action)

    async def close_db(app):
        await app["db_conn"].close()

    app.on_cleanup.append(close_db)
    return app


if __name__ == "__main__":
    port = Config("config.ini").server_port()
    web.run_app(init_app(), port=port)
