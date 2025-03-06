import pandas as pd

# 读取 Excel 文件
df = pd.read_excel('input.xlsx', sheet_name='歌单')

# 打印所有列名
print(df.columns)

# 初始化 SQL 语句
sql_insert = "INSERT INTO songs (name, artist, language, genre, url) VALUES\n"

# 遍历每一行数据
for index, row in df.iterrows():
    name = row['歌名']
    artist = row['歌手']
    language = row['语言']
    genre = row['风格']
    url = row['url']
    
    # 处理 URL 为空的情况
    if pd.isna(url):
        url = '-'
    
    # 拼接 SQL 语句
    sql_insert += f"('{name}', '{artist}', '{language}', '{genre}', '{url}'),\n"

# 去掉最后一个逗号和换行符，并加上分号
sql_insert = sql_insert.rstrip(",\n") + ";"

# 将 SQL 语句写入 output.txt 文件
with open('output_songs.txt', 'w', encoding='utf-8') as file:
    file.write(sql_insert)

print("SQL 语句已成功写入 output_songs.txt 文件！")