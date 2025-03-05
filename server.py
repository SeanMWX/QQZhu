import aiohttp_jinja2
import jinja2
from aiohttp import web
import configparser
import aiomysql
import asyncio
import json

class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr

class Config:
    """负责读取和管理配置文件的类。"""
    def __init__(self, filename='config.ini'):
        self.config = CaseSensitiveConfigParser()
        self.config.read(filename)

    def db_config(self):
        config = self.config['database']
        return {
            'host': config.get('host'),
            'port': int(config.get('port', 3306)),
            'user': config.get('user'),
            'password': config.get('password'),
            'db': config.get('database'), 
            'charset': 'utf8mb4',
        }

    def server_port(self):
        return int(self.config['server'].get('port', 8080))

async def create_db_pool(loop, **db_config):
    """Creates and returns an aiomysql connection pool."""
    db_config['pool_recycle'] = 3600
    db_config['autocommit'] = True
    return await aiomysql.create_pool(loop=loop, **db_config)

async def fetch_songs(pool):
    """Fetches all songs from the database."""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT name, artist, language, genre, url FROM songs")  # 查询所有歌曲
            songs = await cur.fetchall()
    return songs

async def fetch_unique_languages(pool):
    """从数据库中获取唯一的语言列表"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT DISTINCT language FROM songs")
            result = await cur.fetchall()
    return [row['language'] for row in result]

async def fetch_unique_genres(pool):
    """从数据库中获取唯一的风格列表"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT DISTINCT genre FROM songs")
            result = await cur.fetchall()
    return [row['genre'] for row in result]

async def index(request):
    """Handles the index route."""
    pool = request.app['db_pool']
    songs = await fetch_songs(pool)  # 获取所有歌曲
    languages = await fetch_unique_languages(pool)  # 获取唯一的语言列表
    genres = await fetch_unique_genres(pool)  # 获取唯一的风格列表
    return aiohttp_jinja2.render_template('index.html', request, {
        'songs': songs,
        'languages': languages,
        'genres': genres
    })

async def init_app():
    """Initializes and returns the web application."""
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))

    # 配置静态文件路由
    app.router.add_static('/static/', path='static', name='static')

    config = Config('config.ini')
    loop = asyncio.get_running_loop()
    db_pool = await create_db_pool(loop, **config.db_config())
    app['db_pool'] = db_pool
    app['config'] = config

    # index页面
    app.router.add_get('/', index)

    return app

if __name__ == "__main__":
    port = Config('config.ini').server_port()
    app = init_app()
    web.run_app(app, port=port)