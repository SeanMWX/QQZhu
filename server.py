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
        elif action == "settings":
            bg_file = form.get("background_file")
            singer_file = form.get("singer_file")
            new_settings = {
                "title": form.get("title", "").strip() or DEFAULT_SETTINGS["title"],
                "live_url": form.get("live_url", "").strip() or DEFAULT_SETTINGS["live_url"],
                "background_url": form.get("background_url", "").strip() or DEFAULT_SETTINGS["background_url"],
                "singer_url": form.get("singer_url", "").strip() or DEFAULT_SETTINGS["singer_url"],
                "singer_name": form.get("singer_name", "").strip() or DEFAULT_SETTINGS["singer_name"],
                "singer_intro": form.get("singer_intro", "").strip() or DEFAULT_SETTINGS["singer_intro"],
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
    app = web.Application()
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
    app.router.add_get("/admin", admin_page)
    app.router.add_post("/admin/action", admin_action)

    async def close_db(app):
        await app["db_conn"].close()

    app.on_cleanup.append(close_db)
    return app


if __name__ == "__main__":
    port = Config("config.ini").server_port()
    web.run_app(init_app(), port=port)
