import aiohttp_jinja2
import jinja2
from aiohttp import web
import configparser
import aiomysql
import asyncio
import json
import aiohttp
import re

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

async def fetch_stories(pool):
    """获取所有故事及其关联的粉丝信息"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT 
                    stories.id AS story_id,
                    stories.title,
                    stories.content,
                    GROUP_CONCAT(
                        CONCAT(
                            fans.id, '|',  -- 粉丝 ID
                            fans.name, '|',  -- 粉丝名字
                            fans.bili_name, '|',  -- 粉丝 B 站昵称
                            fans.bili_face  -- 粉丝头像链接
                        ) SEPARATOR ';'
                    ) AS fans_info  -- 将多个粉丝的信息聚合到一个字段中
                FROM stories
                JOIN story_fans ON stories.id = story_fans.story_id
                JOIN fans ON story_fans.fan_id = fans.id
                GROUP BY stories.id;  -- 按故事分组
            """)
            stories = await cur.fetchall()

            # 解析 fans_info 字段
            for story in stories:
                if story['fans_info']:
                    fans = []
                    for fan_info in story['fans_info'].split(';'):
                        fan_id, name, bili_name, bili_face = fan_info.split('|')
                        fans.append({
                            'fan_id': fan_id,
                            'name': name,
                            'bili_name': bili_name,
                            'bili_face': bili_face
                        })
                    story['fans'] = fans
                else:
                    story['fans'] = []

                # 替换 <img> 标签为 [图片]
                story['content'] = re.sub(r'<img[^>]*>', '[图片]', story['content'])
    return stories

async def fetch_fans_rank(pool):
    """获取粉丝排行榜（按参与的故事数量排序，支持共享排名，过滤点数为 0 的粉丝）"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT 
                    fans.id AS fan_id,
                    fans.name,
                    fans.bili_name,
                    fans.bili_face,
                    COUNT(story_fans.story_id) AS saint_points  -- 计算圣人点数（参与的故事数量）
                FROM fans
                LEFT JOIN story_fans ON fans.id = story_fans.fan_id
                GROUP BY fans.id
                HAVING saint_points > 0  -- 过滤掉圣人点数为 0 的粉丝
                ORDER BY saint_points DESC;  -- 按圣人点数排序
            """)
            fans_rank = await cur.fetchall()

            # 计算排名（支持共享排名）
            ranked_fans = []
            previous_points = None
            rank = 0
            skip = 0  # 用于跳过排名
            for fan in fans_rank:
                if fan['saint_points'] != previous_points:
                    rank += 1 + skip
                    skip = 0
                else:
                    skip += 1  # 如果点数相同，跳过下一个排名
                fan['rank'] = rank
                ranked_fans.append(fan)
                previous_points = fan['saint_points']
    return ranked_fans

# 新增路由处理函数
async def history(request):
    """垂名青史列表页"""
    pool = request.app['db_pool']
    stories = await fetch_stories(pool)
    return aiohttp_jinja2.render_template('history.html', request, {'stories': stories})

async def rank(request):
    """圣人排行榜页"""
    pool = request.app['db_pool']
    fans_rank = await fetch_fans_rank(pool)
    return aiohttp_jinja2.render_template('rank.html', request, {'fans_rank': fans_rank})

async def story_detail(request):
    """故事详情页"""
    pool = request.app['db_pool']
    story_id = request.match_info['id']
    story = await fetch_story_by_id(pool, story_id)
    if not story:
        raise web.HTTPNotFound(text="故事不存在")
    return aiohttp_jinja2.render_template('story.html', request, {'story': story})

async def fetch_story_by_id(pool, story_id):
    """根据故事 ID 获取单个故事的详细信息"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT 
                    stories.id AS story_id,
                    stories.title,
                    stories.content,
                    GROUP_CONCAT(
                        CONCAT(
                            fans.id, '|',  -- 粉丝 ID
                            fans.name, '|',  -- 粉丝名字
                            fans.bili_name, '|',  -- 粉丝 B 站昵称
                            fans.bili_face  -- 粉丝头像链接
                        ) SEPARATOR ';'
                    ) AS fans_info  -- 将多个粉丝的信息聚合到一个字段中
                FROM stories
                JOIN story_fans ON stories.id = story_fans.story_id
                JOIN fans ON story_fans.fan_id = fans.id
                WHERE stories.id = %s
                GROUP BY stories.id;  -- 按故事分组
            """, (story_id,))
            story = await cur.fetchone()

            # 解析 fans_info 字段
            if story and story['fans_info']:
                fans = []
                for fan_info in story['fans_info'].split(';'):
                    fan_id, name, bili_name, bili_face = fan_info.split('|')
                    fans.append({
                        'fan_id': fan_id,
                        'name': name,
                        'bili_name': bili_name,
                        'bili_face': bili_face
                    })
                story['fans'] = fans
            else:
                story['fans'] = []
    return story

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

async def proxy_image(request):
    # 获取外部图片的 URL
    image_url = request.query.get('url')
    if not image_url:
        raise web.HTTPBadRequest(text="Missing 'url' parameter")

    # 设置 Referer 头（如果需要）
    headers = {
        'Referer': 'https://www.bilibili.com'  # 设置为 B 站的域名
    }

    # 发起请求获取图片
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, headers=headers) as response:
            if response.status == 200:
                # 返回图片内容
                return web.Response(
                    body=await response.read(),
                    content_type=response.headers['Content-Type']
                )
            else:
                raise web.HTTPNotFound(text="Image not found")

async def init_app():
    """Initializes and returns the web application."""
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))

    # 配置静态文件路由
    app.router.add_static('/static/', path='static', name='static')

    # 添加代理路由
    app.router.add_get('/proxy-image', proxy_image)

    config = Config('config.ini')
    loop = asyncio.get_running_loop()
    db_pool = await create_db_pool(loop, **config.db_config())
    app['db_pool'] = db_pool
    app['config'] = config

    # 路由
    app.router.add_get('/', index)
    app.router.add_get('/history', history)  # 垂名青史列表页
    app.router.add_get('/history/{id}', story_detail)  # 故事详情页
    app.router.add_get('/rank', rank)  # 圣人排行榜页

    return app

if __name__ == "__main__":
    port = Config('config.ini').server_port()
    app = init_app()
    web.run_app(app, port=port)