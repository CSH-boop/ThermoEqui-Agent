import sys
sys.path.insert(0, ".")

from thermo_engine.identity import resolve_literal_components

# Test the question
msg = "共沸剂移除水的相平衡分析"
components = resolve_literal_components(msg)

print(f"Message: {msg}")
print(f"Resolved components: {len(components)}")
for item in components:
    print(f"  Type: {type(item)}, Value: {item}")
    if hasattr(item, 'name'):
        print(f"    name: {item.name}, CAS: {item.cas_number}")

# Also check what Chinese aliases matched
from thermo_engine.identity import _CHINESE_ALIAS_MAP
for alias, name in _CHINESE_ALIAS_MAP.items():
    if alias in msg:
        print(f"  Alias '{alias}' -> {name}")

# Test more questions
questions = [
    "共沸剂移除水的相平衡分析",
    "在精馏塔设计过程中，我的相平衡数据来自NRTL模型",
    "什么是活度系数",
    "计算苯-甲苯气液平衡",
    "某二元体系在25℃下的NRTL模型计算得到吉布斯混合自由能ΔG_mix",
    "苯和甲苯的Antoine参数是什么",
]

print("\n--- All questions ---")
for q in questions:
    comps = resolve_literal_components(q)
    if isinstance(comps, list) and len(comps) > 0:
        comp_names = []
        for c in comps:
            if hasattr(c, 'name'):
                comp_names.append(c.name)
            elif isinstance(c, tuple) and len(c) >= 2:
                comp_names.append(str(c[1]))
            else:
                comp_names.append(str(c))
    else:
        comp_names = []
    print(f"  '{q[:50]}' -> {comp_names}")