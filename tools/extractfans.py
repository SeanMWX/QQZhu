import pandas as pd

# 读取 Excel 文件
df = pd.read_excel('input.xlsx', sheet_name='粉丝')

# 打印所有列名
print(df.columns)

# 初始 SQL 语句（SQLite 版本）
sql_drop = "DROP TABLE IF EXISTS fans;"
sql_create = """-- 创建 fans 表
CREATE TABLE IF NOT EXISTS fans (
    id INTEGER PRIMARY KEY,  -- 使用整型 ID
    name TEXT NOT NULL,
    bili_name TEXT,  -- 粉丝的 B 站昵称
    bili_face TEXT   -- 粉丝的头像链接
);
"""
sql_insert = "INSERT INTO fans (id, name, bili_name, bili_face) VALUES\n"


def esc(val):
    """简单转义单引号，避免生成的 SQL 语句报错。"""
    return str(val).replace("'", "''")


# 遍历每一行数据
for _, row in df.iterrows():
    fan_id = row['id']
    name = esc(row['昵称（name）'])
    bili_name = row['B站名字（bili_name）']
    bili_face = row['B站图标（bili_face）']

    if pd.isna(bili_name):
        bili_name = '-'
    if pd.isna(bili_face):
        bili_face = '-'

    sql_insert += f"({fan_id}, '{name}', '{esc(bili_name)}', '{esc(bili_face)}'),\n"

# 去掉最后一个逗号和换行符，并加上分号
sql_insert = sql_insert.rstrip(",\n") + ";"

# 将 SQL 语句写入 output_fans.txt 文件
with open('output_fans.txt', 'w', encoding='utf-8') as file:
    file.write(sql_drop + "\n\n" + sql_create + "\n\n" + sql_insert)

print("SQL 语句已成功写入 output_fans.txt 文件。")
