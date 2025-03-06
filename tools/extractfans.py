import pandas as pd

# 读取 Excel 文件
df = pd.read_excel('input.xlsx', sheet_name='粉丝') 

# 打印所有列名
print(df.columns)

# 初始化 SQL 语句
sql_drop = "DROP TABLE IF EXISTS fans;"
sql_create = """-- 创建 fans 表
CREATE TABLE fans (
    id BIGINT PRIMARY KEY,  -- 使用 BIGINT 类型
    name VARCHAR(255) NOT NULL,
    bili_name VARCHAR(255),  -- 粉丝的 B 站昵称
    bili_face VARCHAR(255)   -- 粉丝的头像链接
);
"""
sql_insert = "INSERT INTO fans (id, name, bili_name, bili_face) VALUES\n"

# 遍历每一行数据
for index, row in df.iterrows():
    id = row['id']
    name = row['昵称（name）']
    bili_name = row['B站名字（bili_name）']
    bili_face = row['B站图标（bili_face）']

    # 处理 B站名字 为空的情况
    if pd.isna(bili_name):
        bili_name = '-'
    
    # 处理 B站图标 为空的情况
    if pd.isna(bili_face):
        bili_face = '-'
    
    # 拼接 SQL 语句
    sql_insert += f"({id}, '{name}', '{bili_name}', '{bili_face}'),\n"

# 去掉最后一个逗号和换行符，并加上分号
sql_insert = sql_insert.rstrip(",\n") + ";"

# 将 SQL 语句写入 output_fans.txt 文件
with open('output_fans.txt', 'w', encoding='utf-8') as file:
    file.write(sql_drop + "\n\n" + sql_create + "\n\n" + sql_insert)

print("SQL 语句已成功写入 output_fans.txt 文件！")