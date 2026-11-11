import re

# 读取 reaction_conditions.md 文件
with open('reaction_conditions.md', 'r') as f:
    content = f.read()

# 使用正则表达式替换步骤名称
# 将 "Step X" 替换为 "StepX to StepX+1"
def replace_step(match):
    step_num = int(match.group(1))
    return f"Step{step_num} to Step{step_num + 1}"

new_content = re.sub(r"Step (\d+)", replace_step, content)

# 将修改后的内容写回文件
with open('reaction_conditions.md', 'w') as f:
    f.write(new_content)
