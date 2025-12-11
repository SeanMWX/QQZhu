import aiohttp_jinja2
import jinja2
from aiohttp import web
import configparser
import asyncio
import aiohttp
import aiosqlite
import json
import os
from urllib.parse import quote
from pypinyin import pinyin, Style


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


def require_admin(request):
    token = request.app["config"].admin_token()
    if not token:
        return True
    provided = request.headers.get("X-Admin-Token") or request.query.get("token")
    if provided and provided == token:
        return True
    raise web.HTTPUnauthorized(text="Unauthorized")


async def index(request):
    conn = request.app["db_conn"]
    songs = await fetch_songs(conn)
    languages = await fetch_unique_languages(conn)
    genres = await fetch_unique_genres(conn)
    return aiohttp_jinja2.render_template(
        "index.html",
        request,
        {"songs": songs, "languages": languages, "genres": genres},
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


async def admin_page(request):
    require_admin(request)
    conn = request.app["db_conn"]
    songs = await fetch_songs(conn)
    return aiohttp_jinja2.render_template(
        "admin.html",
        request,
        {"songs": songs, "message": request.query.get("message", ""), "token": request.query.get("token", "")},
    )


async def admin_action(request):
    conn = request.app["db_conn"]
    form = await request.post()
    provided_token = None
    token_cfg = request.app["config"].admin_token()
    if token_cfg:
        provided_token = (
            request.headers.get("X-Admin-Token")
            or request.query.get("token")
            or form.get("token")
        )
        if provided_token != token_cfg:
            raise web.HTTPUnauthorized(text="Unauthorized")
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
        else:
            message = "未知操作"
    except Exception as exc:
        message = f"操作失败: {exc}"

    params = []
    if provided_token:
        params.append(f"token={quote(provided_token)}")
    params.append(f"message={quote(message)}")
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
    app.router.add_get("/admin", admin_page)
    app.router.add_post("/admin/action", admin_action)

    async def close_db(app):
        await app["db_conn"].close()

    app.on_cleanup.append(close_db)
    return app


if __name__ == "__main__":
    port = Config("config.ini").server_port()
    web.run_app(init_app(), port=port)
