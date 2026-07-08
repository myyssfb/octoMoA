"""
模型评测 — 内置测试题 + 自动评分
"""

BENCHMARK_QUESTIONS = [
    {
        "id": "logic",
        "category": "逻辑推理",
        "prompt": (
            "一个房间里有3个开关，分别控制隔壁房间的3盏灯。"
            "你只能进入隔壁房间一次。如何确定每个开关对应哪盏灯？"
            "请给出具体步骤。"
        ),
        "expected_keywords": ["先打开", "等待", "关闭", "摸温度", "热", "亮", "不亮"],
        "reference": (
            "1. 打开开关1，等待几分钟让灯泡变热。\n"
            "2. 关闭开关1，打开开关2。\n"
            "3. 进入隔壁房间：亮着的灯对应开关2，摸起来热但不亮的对应开关1，又不亮又不热的对应开关3。"
        ),
    },
    {
        "id": "code",
        "category": "代码生成",
        "prompt": (
            "用 Python 实现一个 LRU Cache，要求：\n"
            "1. 支持 get(key) 和 put(key, value) 操作\n"
            "2. 两个操作的时间复杂度都是 O(1)\n"
            "3. 容量满时淘汰最久未使用的键\n"
            "请给出完整代码。"
        ),
        "expected_keywords": ["class", "dict", "collections", "OrderedDict", "def get", "def put", "move_to_end", "popitem"],
        "reference": "from collections import OrderedDict",
    },
    {
        "id": "math",
        "category": "数学计算",
        "prompt": (
            "甲乙两人分别从A、B两地同时出发，相向而行。"
            "甲的速度是60km/h，乙的速度是40km/h。"
            "两人在距离A地120km处相遇。请问A、B两地的距离是多少公里？"
            "请给出详细的解题过程。"
        ),
        "expected_keywords": ["200", "时间相同", "120/60", "80", "120+80"],
        "reference": "200km",
    },
    {
        "id": "creative",
        "category": "创意写作",
        "prompt": (
            "用100字左右描述一个机器人第一次看到大海的场景。"
            "要求有画面感，能传达出机器人的'感受'。"
        ),
        "expected_keywords": ["海", "浪", "蓝", "广阔", "无边", "传感器", "数据", "震撼"],
        "reference": "",
    },
    {
        "id": "extract",
        "category": "信息提取",
        "prompt": (
            "从以下文本中提取关键信息，输出为 JSON 格式：\n\n"
            "张三，男，1990年5月出生，北京大学计算机系2012届本科毕业，"
            "2015年获得清华大学硕士学位。目前在腾讯担任高级工程师，月薪35000元。"
            "联系方式：手机13800138000，邮箱zhangsan@example.com。\n\n"
            "请提取：姓名、性别、出生年月、学历（含学校和专业）、工作信息（公司、职位、薪资）、联系方式。"
        ),
        "expected_keywords": ["张三", "男", "1990", "北京大学", "计算机", "清华", "硕士", "腾讯", "工程师", "35000", "13800138000", "zhangsan@example.com"],
        "reference": "",
    },
]


def score_answer(question: dict, answer: str) -> float:
    """基于关键词命中率评分，返回 0-100。"""
    if not answer:
        return 0.0
    keywords = question.get("expected_keywords", [])
    if not keywords:
        return 50.0  # 无关键词时给基础分

    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return round((hits / len(keywords)) * 100, 1)
