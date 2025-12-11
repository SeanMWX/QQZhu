import pandas as pd

# 读取 Excel 文件（工作表名：垂名青史）
df = pd.read_excel('input.xlsx', sheet_name='垂名青史')

# 打印所有列名以确认
print(df.columns)

# 初始 SQL 语句（SQLite 版本）
sql_drop = "DROP TABLE IF EXISTS story_fans;\nDROP TABLE IF EXISTS stories;"
sql_create = """-- 创建 stories 表
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL
);

-- 创建 story_fans 表（关联表）
CREATE TABLE IF NOT EXISTS story_fans (
    story_id INTEGER,
    fan_id INTEGER,
    PRIMARY KEY (story_id, fan_id),  -- 复合主键
    FOREIGN KEY (story_id) REFERENCES stories(id),
    FOREIGN KEY (fan_id) REFERENCES fans(id)
);
"""
sql_stories = "INSERT INTO stories (title, content) VALUES\n"
sql_story_fans = "INSERT INTO story_fans (story_id, fan_id) VALUES\n"


def esc(val):
    """简单转义单引号，避免生成的 SQL 语句报错。"""
    return str(val).replace("'", "''")


story_id = 1

# 遍历每一行数据
for _, row in df.iterrows():
    title = esc(row['标题'])
    content = row['内容']
    fans = row['圣人']

    if pd.isna(content):
        content = ''
    content = esc(content)

    sql_stories += f"('{title}', '{content}'),\n"

    if not pd.isna(fans):
        fan_ids = str(fans).split('、')
        for fan_id in fan_ids:
            sql_story_fans += f"({story_id}, {fan_id}),\n"

    story_id += 1

# 去掉最后一个逗号和换行符，并加上分号
sql_stories = sql_stories.rstrip(",\n") + ";"
sql_story_fans = sql_story_fans.rstrip(",\n") + ";"

# 将 SQL 语句写入 output_stories.txt 文件
with open('output_stories.txt', 'w', encoding='utf-8') as file:
    file.write(sql_drop + "\n\n" + sql_create + "\n\n" + sql_stories + "\n\n" + sql_story_fans)

print("SQL 语句已成功写入 output_stories.txt 文件。")
