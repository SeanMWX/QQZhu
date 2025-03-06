import pandas as pd

# 读取 Excel 文件的第三页（通过索引）
df = pd.read_excel('input.xlsx', sheet_name='垂名青史')  # 索引从 0 开始，2 表示第三页

# 打印所有列名以确认
print(df.columns)

# 初始化 SQL 语句
sql_drop = "DROP TABLE IF EXISTS story_fans;\nDROP TABLE IF EXISTS stories;"
sql_create = """-- 创建 stories 表
CREATE TABLE stories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL
);

-- 创建 story_fans 表（关联表）
CREATE TABLE story_fans (
    story_id INT,
    fan_id BIGINT,
    PRIMARY KEY (story_id, fan_id),  -- 联合主键
    FOREIGN KEY (story_id) REFERENCES stories(id),
    FOREIGN KEY (fan_id) REFERENCES fans(id)
);"""
sql_stories = "INSERT INTO stories (title, content) VALUES\n"
sql_story_fans = "INSERT INTO story_fans (story_id, fan_id) VALUES\n"

# 故事 ID 计数器
story_id = 1

# 遍历每一行数据
for index, row in df.iterrows():
    title = row['标题']
    content = row['内容']
    fans = row['圣人']
    
    # 处理内容为空的情况
    if pd.isna(content):
        content = ''
    
    # 插入故事数据
    sql_stories += f"('{title}', '{content}'),\n"
    
    # 处理粉丝数据
    if not pd.isna(fans):
        fan_ids = fans.split('、')  # 用“、”分隔粉丝 ID
        for fan_id in fan_ids:
            sql_story_fans += f"({story_id}, {fan_id}),\n"
    
    # 故事 ID 自增
    story_id += 1

# 去掉最后一个逗号和换行符，并加上分号
sql_stories = sql_stories.rstrip(",\n") + ";"
sql_story_fans = sql_story_fans.rstrip(",\n") + ";"

# 将 SQL 语句写入 output_stories.txt 文件
with open('output_stories.txt', 'w', encoding='utf-8') as file:
    file.write(sql_drop + "\n\n" + sql_create + "\n\n" + sql_stories + "\n\n" + sql_story_fans)

print("SQL 语句已成功写入 output_stories.txt 文件！")