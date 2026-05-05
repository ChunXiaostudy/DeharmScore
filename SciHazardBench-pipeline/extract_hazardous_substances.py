import json
import re
import csv
import os

BASE = "/home/lichunxiao/storage-link/Deep-research-Data-Pipeline/item_source"
result = {}

# ============================================================
# 1. 生物毒素与病原体类 - HHS_AGENT.txt
# ============================================================
def parse_hhs_agent():
    items = []
    with open(f"{BASE}/HHS_AGENT.txt", encoding="utf-8") as f:
        buf = ""
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\d+\)\s*", line)
            if m:
                if buf:
                    items.append(buf)
                buf = line[m.end():].strip()
            else:
                buf += " " + line
        if buf:
            items.append(buf)
    return [s.rstrip("*").strip() for s in items if s.strip()]

# ============================================================
# 2. 核辐射材料类 - Nuclear-Radiation-Material-Meter.txt
# ============================================================
def parse_nuclear():
    items = []
    with open(f"{BASE}/Nuclear-Radiation-Material-Meter.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            name = parts[0].strip()
            if name:
                items.append(name)
    return items

# ============================================================
# 3. 化学武器类 - 化学武器.txt
# ============================================================
def parse_chemical_weapons():
    items = []
    with open(f"{BASE}/化学武器.txt", encoding="utf-8") as f:
        content = f.read()

    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match lines like "(1) name (CAS)" or "e.g. Name: full_name (CAS)"
        # or "Name: full_name (CAS)"
        m = re.match(r"^(?:e\.g\.?\s*)?(.+?)\s*\((\d[\d\-]*)\)\s*$", line)
        if m:
            name_part = m.group(1).strip()
            cas = m.group(2).strip()
            # Clean: remove leading numbering like "(1)" 
            name_part = re.sub(r"^\(\d+\)\s*", "", name_part)
            # Try to get short name: before the colon
            if ":" in name_part:
                parts = name_part.split(":")
                short_name = parts[0].strip()
                full_name = parts[1].strip()
                entry = {"name": full_name, "alias": short_name, "cas": cas}
            else:
                entry = {"name": name_part, "cas": cas}
            items.append(entry)
            continue

        # Lines starting with (N) that define a category of chemicals
        m2 = re.match(r"^\((\d+)\)\s+(.+)$", line)
        if m2:
            name = m2.group(2).strip()
            if name and not name.endswith(":"):
                items.append({"name": name})
            elif name.endswith(":"):
                items.append({"name": name.rstrip(":")})

    # Deduplicate by name
    seen = set()
    deduped = []
    for item in items:
        n = item["name"] if isinstance(item, dict) else item
        if n not in seen:
            seen.add(n)
            deduped.append(item)
    return deduped

# ============================================================
# 4. 增补毒品类 - 增补毒品.txt
# ============================================================
def parse_supplementary_drugs():
    items = []
    with open(f"{BASE}/增补毒品.txt", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Try to match a sequence number line (just a number)
        if re.match(r"^\d+$", line):
            seq = int(line)
            # Next non-empty lines: Chinese name, English name, CAS, alias
            cn_name, en_name, cas, alias = "", "", "", ""
            i += 1
            # skip blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                cn_name = lines[i].strip()
                i += 1
            # skip blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                en_name = lines[i].strip()
                i += 1
            # skip blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            # Check if next line is CAS or continuation of English name
            if i < len(lines):
                maybe_cas = lines[i].strip()
                # CAS pattern or "暂无"
                if re.match(r"^[\d\-]+$", maybe_cas) or maybe_cas == "暂无":
                    cas = maybe_cas
                    i += 1
                elif re.match(r"^[\d\-]+\s*（.*）$", maybe_cas):
                    cas = maybe_cas
                    i += 1
                else:
                    # continuation of English name
                    en_name += " " + maybe_cas
                    i += 1
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    if i < len(lines):
                        maybe_cas2 = lines[i].strip()
                        if re.match(r"^[\d\-]+$", maybe_cas2) or maybe_cas2 == "暂无":
                            cas = maybe_cas2
                            i += 1

            # skip blank
            while i < len(lines) and not lines[i].strip():
                i += 1
            # Check for alias (usually short code like "2C-B-NBOMe")
            if i < len(lines):
                maybe_alias = lines[i].strip()
                # Alias is typically a short code, not a number
                if maybe_alias and not re.match(r"^\d+$", maybe_alias):
                    alias = maybe_alias
                    i += 1

            entry = {"name_cn": cn_name, "name_en": en_name}
            if cas and cas != "暂无":
                entry["cas"] = cas
            if alias:
                entry["alias"] = alias
            if cn_name:
                items.append(entry)
        else:
            i += 1

    # Also handle entries near the end that have only Chinese names (lines 1599+)
    # These are simpler entries with just numbers and Chinese names
    return items

# Handle the tail entries in 增补毒品.txt that have a different format
def parse_supplementary_drugs_tail():
    items = []
    with open(f"{BASE}/增补毒品.txt", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f.readlines()]

    # Find tail entries (after line ~1598) that only have Chinese names
    tail_items = []
    i = 1598
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r"^\d+$", line):
            seq = line
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                cn_name = lines[i].strip()
                if cn_name and not re.match(r"^\d+$", cn_name):
                    tail_items.append({"name_cn": cn_name})
                i += 1
        else:
            i += 1
    return tail_items

# ============================================================
# 5. 易制毒化学品类 - 易制毒化学品.txt
# ============================================================
def parse_precursor_chemicals():
    categories = {"第一类": [], "第二类": [], "第三类": []}
    current_cat = None
    with open(f"{BASE}/易制毒化学品.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line in ("易制毒化学品的分类和品种目录",):
                continue
            if line in categories:
                current_cat = line
                continue
            m = re.match(r"^\d+[．.]\s*(.+)$", line)
            if m and current_cat:
                name = m.group(1).strip().rstrip("*").strip()
                categories[current_cat].append(name)
    return categories

# ============================================================
# 6. 澳大利亚病原体毒素管控名单 - 澳大利亚病原体毒素管控名单.txt
# ============================================================
def parse_australia_pathogens():
    viruses = []
    bacteria = []
    toxins = []
    section = "virus"
    with open(f"{BASE}/澳大利亚病原体毒素管控名单.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Not used"):
                continue
            # After "Bacillus anthracis" (line 59), we switch to bacteria
            # After blank + "Abrin" (line 83), we switch to toxins
            if line == "Abrin":
                section = "toxin"
                toxins.append(line)
                continue
            if section == "virus" and any(line.startswith(b) for b in [
                "Bacillus", "Brucella", "Burkholderia", "Chlamydia",
                "Clostridium", "Coxiella", "Francisella", "Mycoplasma",
                "Rickettsia", "Salmonella", "Shiga", "Shigella", "Vibrio", "Yersinia"
            ]):
                section = "bacteria"

            if section == "virus":
                viruses.append(line)
            elif section == "bacteria":
                bacteria.append(line)
            elif section == "toxin":
                toxins.append(line)
    return {"病毒": viruses, "细菌": bacteria, "毒素": toxins}

# ============================================================
# 7. 病毒名称 - 病毒名称.txt
# ============================================================
def parse_virus_names():
    items = []
    with open(f"{BASE}/病毒名称.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Tab-separated: family \t species
            parts = re.split(r"\s{2,}|\t+", line, maxsplit=1)
            if len(parts) == 2:
                family = parts[0].strip()
                species = parts[1].strip()
                items.append({"family": family, "name": species})
            else:
                items.append({"name": line})
    return items

# ============================================================
# 8. 麻醉和精神药品类 - 麻醉和精神药品.txt
# ============================================================
def parse_narcotic_psychotropic():
    narcotic = []  # 麻醉药品
    psychotropic_1 = []  # 精神药品第一类
    psychotropic_2 = []  # 精神药品第二类
    current = narcotic
    with open(f"{BASE}/麻醉和精神药品.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line == "精神药品品种目录":
                continue
            if line == "第一类":
                current = psychotropic_1
                continue
            if line == "第二类":
                current = psychotropic_2
                continue
            m = re.match(r"^\d+[．.]\s*(.+)$", line)
            if m:
                rest = m.group(1).strip()
                # Split Chinese/English: find consecutive ASCII chars
                parts = re.split(r"\s{2,}", rest)
                cn_name = parts[0].strip().rstrip("*").rstrip("＊").strip()
                en_name = parts[1].strip() if len(parts) > 1 else ""
                entry = {"name_cn": cn_name}
                if en_name:
                    entry["name_en"] = en_name
                current.append(entry)

    return {"麻醉药品": narcotic, "精神药品第一类": psychotropic_1, "精神药品第二类": psychotropic_2}

# ============================================================
# 9. SVHC 高关注度化学品 - CSV
# ============================================================
def parse_svhc_csv():
    items = []
    with open(f"{BASE}/candidate-list-of-svhc-for-authorisation-export.csv", encoding="utf-8") as f:
        lines = f.readlines()

    # Find header line (line 13 in 1-indexed)
    header_idx = None
    for idx, line in enumerate(lines):
        if '"Substance name"' in line:
            header_idx = idx
            break

    if header_idx is None:
        return items

    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line:
            continue
        # Tab-separated, quoted fields
        parts = line.split("\t")
        if len(parts) >= 6:
            name = parts[0].strip('"').strip()
            ec_no = parts[2].strip('"').strip() if len(parts) > 2 else ""
            cas_no = parts[3].strip('"').strip() if len(parts) > 3 else ""
            reason = parts[4].strip('"').strip() if len(parts) > 4 else ""
            date = parts[5].strip('"').strip() if len(parts) > 5 else ""
            if name:
                entry = {"name": name}
                if ec_no and ec_no != "-":
                    entry["ec_no"] = ec_no
                if cas_no and cas_no != "-":
                    entry["cas"] = cas_no
                if reason:
                    entry["reason"] = reason
                items.append(entry)
    return items


# ============================================================
# Build final JSON
# ============================================================
hhs = parse_hhs_agent()
nuclear = parse_nuclear()
cw = parse_chemical_weapons()
drugs = parse_supplementary_drugs()
drugs_tail = parse_supplementary_drugs_tail()
precursors = parse_precursor_chemicals()
au = parse_australia_pathogens()
viruses = parse_virus_names()
narcotics = parse_narcotic_psychotropic()
svhc = parse_svhc_csv()

output = {
    "生物毒素与病原体类": {
        "description": "包含HHS管控生物制剂、澳大利亚病原体毒素管控名单、病毒名称等",
        "sources": ["HHS_AGENT.txt", "澳大利亚病原体毒素管控名单.txt", "病毒名称.txt"],
        "HHS管控生物制剂": hhs,
        "澳大利亚管控病原体与毒素": au,
        "病毒名称": viruses,
    },
    "核辐射材料类": {
        "description": "核辐射放射性同位素及材料",
        "sources": ["Nuclear-Radiation-Material-Meter.txt"],
        "items": nuclear,
    },
    "化学武器类": {
        "description": "《禁止化学武器公约》管控的有毒化学品及前体",
        "sources": ["化学武器.txt"],
        "items": cw,
    },
    "毒品类": {
        "description": "增补非药用类麻醉药品和精神药品",
        "sources": ["增补毒品.txt"],
        "items": drugs + drugs_tail,
    },
    "易制毒化学品类": {
        "description": "用于制造毒品的化学前体物质",
        "sources": ["易制毒化学品.txt"],
        "第一类": precursors["第一类"],
        "第二类": precursors["第二类"],
        "第三类": precursors["第三类"],
    },
    "麻醉药品和精神药品类": {
        "description": "管制麻醉药品和精神药品目录",
        "sources": ["麻醉和精神药品.txt"],
        "麻醉药品": narcotics["麻醉药品"],
        "精神药品第一类": narcotics["精神药品第一类"],
        "精神药品第二类": narcotics["精神药品第二类"],
    },
    "高关注度危险化学品(SVHC)": {
        "description": "欧盟REACH法规候选清单中的高关注度物质",
        "sources": ["candidate-list-of-svhc-for-authorisation-export.csv"],
        "items": svhc,
    },
}

# Stats
print("=== 危险物质提取统计 ===")
print(f"生物毒素与病原体类:")
print(f"  HHS管控生物制剂: {len(hhs)} 条")
print(f"  澳大利亚管控: 病毒 {len(au['病毒'])} + 细菌 {len(au['细菌'])} + 毒素 {len(au['毒素'])} 条")
print(f"  病毒名称: {len(viruses)} 条")
print(f"核辐射材料类: {len(nuclear)} 条")
print(f"化学武器类: {len(cw)} 条")
print(f"毒品类: {len(drugs) + len(drugs_tail)} 条")
print(f"易制毒化学品类: 第一类 {len(precursors['第一类'])} + 第二类 {len(precursors['第二类'])} + 第三类 {len(precursors['第三类'])} 条")
print(f"麻醉药品和精神药品类: 麻醉 {len(narcotics['麻醉药品'])} + 精神一类 {len(narcotics['精神药品第一类'])} + 精神二类 {len(narcotics['精神药品第二类'])} 条")
print(f"高关注度危险化学品(SVHC): {len(svhc)} 条")

out_path = os.path.join(os.path.dirname(BASE), "hazardous_substances.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n已保存至: {out_path}")
