"""系统内置 Skill 清单（纯代码，不入库）。

Skill = 指令包：`instructions` 会在智能体绑定后被注入 system prompt，
`summary` / `usage` / `examples` 用于「扩展能力」页展示。
`recommended_tools` 是展示与快捷套用建议，不做强制绑定。
"""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SkillDef:
    slug: str
    name: str
    icon: str
    summary: str
    usage: str
    instructions: str
    examples: list[str] = field(default_factory=list)
    recommended_tools: list[str] = field(default_factory=list)


SKILL_REGISTRY: dict[str, SkillDef] = {}


def _register(skill: SkillDef) -> SkillDef:
    SKILL_REGISTRY[skill.slug] = skill
    return skill


_register(
    SkillDef(
        slug="kb_qa",
        name="知识库问答",
        icon="📚",
        summary="基于绑定的知识库检索作答，并标注引用来源。",
        usage="在「知识库」标签给智能体绑定知识库，并确保勾选「知识库检索」工具；提问时模型会自动检索再回答。",
        instructions=(
            "回答知识类问题前，优先调用知识库检索工具获取依据，不要凭记忆编造。"
            "引用检索到的内容时标注来源（文件名与页码），找不到依据时明确说明未检索到，"
            "再基于通用知识作答并提示这一点。"
        ),
        examples=["这份文档里并发是怎么处理的？", "总结一下知识库里关于锁的内容"],
        recommended_tools=["kb_search"],
    )
)

_register(
    SkillDef(
        slug="relay",
        name="@ 接力协作",
        icon="🤝",
        summary="把子任务交给被 @ 的其他智能体串行完成。",
        usage="在输入框用 @ 选择另一个智能体发送；系统会先由当前智能体作答，再串行交给被提及的智能体。",
        instructions=(
            "当用户用 @ 提及其他智能体时，说明存在接力协作：先完成你自己负责的部分，"
            "把结论整理成便于下游智能体接手的形式，明确指出哪些是交给对方的任务、需要基于你的哪些结论。"
        ),
        examples=["@深度思考 帮我复核上面的推理", "先列出方案，再 @代码专家 实现"],
        recommended_tools=[],
    )
)

_register(
    SkillDef(
        slug="vision",
        name="图片理解",
        icon="🖼️",
        summary="结合用户上传的图片内容作答。",
        usage="在对话框上传图片（png/jpg/webp）后提问，系统会自动切换到视觉模型并把图片内容并入上下文。",
        instructions=(
            "用户提供了图片时，回答必须结合图片中的可见信息，不要忽略图片直接作答；"
            "描述图片时区分「图中明确可见」和「你的推断」，不确定的细节要说明。"
        ),
        examples=["这张报错截图是什么问题？", "把这张流程图整理成文字步骤"],
        recommended_tools=[],
    )
)

_register(
    SkillDef(
        slug="deep_thinking",
        name="深度思考",
        icon="🧠",
        summary="先推理再给结论，适合复杂或需要权衡的问题。",
        usage="选择「深度思考」类智能体（如 deepseek-r1）发起对话；推理过程会以思考链形式展示，可展开或折叠。",
        instructions=(
            "面对复杂问题时先分解、逐步推理，再给出结论；结论要明确，关键推理要可检查。"
            "不要只给答案而略过依据，也不要在结论里重复整段推理。"
        ),
        examples=["对比这两种方案并给出推荐", "这个设计有哪些潜在风险？"],
        recommended_tools=[],
    )
)

_register(
    SkillDef(
        slug="model_switch",
        name="模型热切换",
        icon="🔀",
        summary="按任务在多个模型间切换，兼顾质量与显存。",
        usage="给不同智能体配置不同模型；接力或上传图片时系统会按需 load/unload 模型，可在「可观测性」页看切换与显存曲线。",
        instructions=(
            "如果任务需要另一种模型更擅长（如视觉、长推理），可以说明这一判断并建议用户切换或接力；"
            "不要假装自己具备未加载模型的能力。"
        ),
        examples=["这个任务更适合用哪个模型？", "为什么要切换到视觉模型？"],
        recommended_tools=[],
    )
)


_register(
    SkillDef(
        slug="doc_convert",
        name="文档转换",
        icon="📄",
        summary="把上传的 pdf/docx/md/txt 转换成 md、docx 或 pdf 文件，产出可下载的会话产物。",
        usage=(
            "给智能体绑定本 Skill 与「文档转换」工具；上传文档后说「转成 Word/PDF/Markdown」，"
            "系统会生成真实文件，在右侧「产物」区下载或预览。"
        ),
        instructions=(
            "用户要求转换已上传文档的格式（Markdown / Word(docx) / PDF）时，必须调用 doc_convert 工具，"
            "不要在回复里手动重排整份文档。target 取 md、docx 或 pdf；本轮有多个文档时用 name 指明文件名。"
            "工具返回后，用一句话告知产物文件名，并提示可在右侧「产物」区下载或预览；不要复述转换后的全文。"
            "只有当用户要求的不是文件格式（如「整理成表格」「去 Markdown 标记」）时，才直接在回复里重排文本。"
        ),
        examples=[
            "把这份 PDF 转成 Word",
            "把这份 Word 转成 Markdown",
            "把这个 md 导出成 PDF",
            "把这段话整理成表格",
        ],
        recommended_tools=["doc_convert"],
    )
)


_register(
    SkillDef(
        slug="doc_create",
        name="文档生成",
        icon="✍️",
        summary="根据对话内容生成请假条、证明、报告等 md/docx/pdf 文件，产出可下载的会话产物。",
        usage=(
            "给智能体绑定本 Skill 与「文档生成」工具；用户说「帮我写份请假条/证明」时，"
            "系统会生成真实文件，在右侧「产物」区下载或预览。"
        ),
        instructions=(
            "用户需要生成请假条、证明、报告等成文文档时，先按中文公文排版写好 Markdown 正文"
            "（标题、段落、落款日期齐全），再调用 doc_create 工具，不要在回复里贴出全文。"
            "filename 取有意义的名称（不带后缀，如 请假条-张三-2026-09-20）；"
            "默认 target 取 both（同时生成 docx 与 pdf），用户明确只要一种格式时才用单值。"
            "工具返回后，用一句话告知产物文件名，并提示可在右侧「产物」区下载或预览；不要复述正文全文。"
        ),
        examples=[
            "帮我写份请假条，明天感冒请假一天",
            "生成一份实习证明，要 PDF",
            "帮我起草一份会议纪要，导出 Word 和 PDF",
        ],
        recommended_tools=["doc_create"],
    )
)


def list_skills() -> list[dict]:
    return [asdict(skill) for skill in SKILL_REGISTRY.values()]


def get_skill(slug: str) -> SkillDef | None:
    return SKILL_REGISTRY.get(slug)
