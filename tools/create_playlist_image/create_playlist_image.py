from PIL import Image, ImageDraw, ImageFont
import os
import re
from pypinyin import pinyin, Style  # 需要安装pypinyin库：pip install pypinyin

def combine_background(head_img, content_img, end_img, output_height):
    """组合背景图片的三部分"""
    head_height = head_img.height
    content_height = content_img.height
    end_height = end_img.height
    
    width = head_img.width
    combined_img = Image.new('RGB', (width, output_height))
    
    combined_img.paste(head_img, (0, 0))
    content_area_height = output_height - head_height - end_height
    content_blocks = content_area_height // content_height
    
    for i in range(content_blocks):
        y_pos = head_height + i * content_height
        combined_img.paste(content_img, (0, y_pos))
    
    combined_img.paste(end_img, (0, output_height - end_height))
    return combined_img

def get_pinyin(name):
    """获取歌名的拼音（用于排序）"""
    try:
        # 获取不带声调的拼音
        py = ''.join([item[0] for item in pinyin(name, style=Style.NORMAL)])
        return py.lower()  # 转为小写
    except:
        return name  # 如果转换失败返回原字符串

def create_playlist_image(input_txt, head_img_path, content_img_path, end_img_path, 
                         output_image, font_path=None,
                         max_chars_per_line=35, max_songs_per_line=6):
    """
    创建歌单图片（先按字数排序，再按拼音排序）
    """
    # 加载背景图片
    head_img = Image.open(head_img_path)
    content_img = Image.open(content_img_path)
    end_img = Image.open(end_img_path)
    
    # 从背景色自动计算最佳文字颜色
    bg_color = content_img.getpixel((10, 10))
    text_color = (30, 30, 30) if sum(bg_color) > 382 else (240, 240, 240)
    
    # 读取歌单文本
    with open(input_txt, 'r', encoding='utf-8') as f:
        song_names = [line.strip() for line in f.readlines() if line.strip()]
    
    # 先按字数分组，再在每个分组内按拼音排序
    # 1. 创建一个字典，键是字数，值是对应的歌名列表
    length_groups = {}
    for name in song_names:
        length = len(name)
        if length not in length_groups:
            length_groups[length] = []
        length_groups[length].append(name)
    
    # 2. 对每个分组内的歌名按拼音排序
    sorted_names = []
    for length in sorted(length_groups.keys()):  # 按字数从小到大
        # 对相同字数的歌名按拼音排序
        sorted_group = sorted(length_groups[length], key=lambda x: get_pinyin(x))
        sorted_names.extend(sorted_group)
    
    # 字体设置
    try:
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 38)
        else:
            try_fonts = [
                "msyhl.ttc", "SourceHanSansSC-Light.otf",
                "msyh.ttc", "simsun.ttc", "STHeiti Light.ttc"
            ]
            for tf in try_fonts:
                try:
                    font = ImageFont.truetype(tf, 38)
                    break
                except:
                    continue
            else:
                raise Exception("找不到优雅字体，使用默认字体")
    except Exception as e:
        print(f"字体加载警告: {e}")
        font = ImageFont.load_default()
        font.size = 38
    
    # 计算行高
    line_height = max(content_img.height, 80)
    margin_left = 50
    
    # 构建每行的歌名组合
    wrapped_lines = []
    current_line = []
    current_line_chars = 0
    
    for name in sorted_names:  # 使用排序后的歌名列表
        name_len = len(name)
        
        if (current_line and 
            ((current_line_chars + name_len > max_chars_per_line) or 
             (len(current_line) >= max_songs_per_line))):
            wrapped_lines.append("  ".join(current_line))
            current_line = []
            current_line_chars = 0
        
        current_line.append(name)
        current_line_chars += name_len + 2
    
    if current_line:
        wrapped_lines.append("  ".join(current_line))
    
    # 计算所需高度
    total_height = head_img.height + len(wrapped_lines) * line_height + end_img.height
    
    # 组合背景图片
    background = combine_background(head_img, content_img, end_img, total_height)
    draw = ImageDraw.Draw(background)
    
    # 文字阴影效果
    shadow_color = (bg_color[0]-30, bg_color[1]-30, bg_color[2]-30) if sum(bg_color) > 382 else (0, 0, 0)
    
    # 绘制文本
    y_pos = head_img.height
    for line in wrapped_lines:
        text_height = font.getsize(line)[1]
        text_y = y_pos + (line_height - text_height) // 2
        
        draw.text((margin_left+2, text_y+2), line, font=font, fill=shadow_color)
        draw.text((margin_left, text_y), line, font=font, fill=text_color)
        y_pos += line_height
    
    background.save(output_image, quality=95)
    print(f"歌单图片已保存到: {output_image}")

def extract_song_names(input_sql, output_txt):
    """从SQL提取歌名"""
    with open(input_sql, "r", encoding="utf-8") as f:
        sql_content = f.read()
    
    song_names = re.findall(r"\('([^']+)'", sql_content.split("VALUES")[1])
    
    with open(output_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(song_names))
    
    print(f"歌名已提取到: {output_txt}")

if __name__ == "__main__":
    # 文件路径配置
    sql_file = "../output_songs.txt"
    playlist_file = "playlist.txt"
    output_image = "playlist.png"
    
    # 背景图片路径
    head_bg = "head_bg.png"
    content_bg = "content_bg.png"
    end_bg = "end_bg.png"
    
    # 字体路径
    font_path = None
    
    # 1. 从SQL提取歌名
    extract_song_names(sql_file, playlist_file)
    
    # 2. 生成歌单图片（先按字数排序，再按拼音排序）
    create_playlist_image(
        input_txt=playlist_file,
        head_img_path=head_bg,
        content_img_path=content_bg,
        end_img_path=end_bg,
        output_image=output_image,
        font_path=font_path,
        max_chars_per_line=35,
        max_songs_per_line=6
    )