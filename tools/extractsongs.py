import pandas as pd

# 读取 Excel 文件
df = pd.read_excel('input.xlsx', sheet_name='歌单')

# 打印所有列名
print(df.columns)

# 初始 SQL 语句（SQLite 版本）
sql_drop = "DROP TABLE IF EXISTS songs;"
sql_create = """-- 创建 songs 表
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,  -- 歌名
    artist TEXT NOT NULL,  -- 歌手
    language TEXT,  -- 语言
    genre TEXT,  -- 风格
    url TEXT NOT NULL  -- 歌曲的 URL
);
"""
sql_insert = "INSERT INTO songs (name, artist, language, genre, url) VALUES\n"


def esc(val):
    """简单转义单引号，避免生成的 SQL 语句报错。"""
    return str(val).replace("'", "''")


# 遍历每一行数据
for _, row in df.iterrows():
    name = esc(row['歌名'])
    artist = esc(row['歌手'])
    language = esc(row['语言'])
    genre = esc(row['风格'])
    url = row['url']

    if pd.isna(url):
        url = '-'
    url = esc(url)

    sql_insert += f"('{name}', '{artist}', '{language}', '{genre}', '{url}'),\n"

# 去掉最后一个逗号和换行符，并加上分号
sql_insert = sql_insert.rstrip(",\n") + ";"

# 将 SQL 语句写入 output.txt 文件
with open('output_songs.txt', 'w', encoding='utf-8') as file:
    file.write(sql_drop + "\n\n" + sql_create + "\n\n" + sql_insert)

print("SQL 语句已成功写入 output_songs.txt 文件。")
