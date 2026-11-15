import re
from education_list import DEGREE_PATTERNS, FIELDS, INSTITUTIONS

def _list_regex(items):
    parts = (r"\s*".join(map(re.escape, item.split()))
             for item in sorted(items, key=len, reverse=True))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)", re.IGNORECASE)

DEGREE_REGEX = re.compile(
    r"(?<!\w)(?:" + "|".join(p for p, _ in DEGREE_PATTERNS) + r")(?!\w)",re.IGNORECASE,)

FIELD_REGEX = _list_regex(FIELDS)

KNOWN_INSTITUTION_REGEX = _list_regex(INSTITUTIONS)

_EN_WORD = r"[A-Z][\w&.'’-]*"

INSTITUTION_REGEX = re.compile(
    r"\b(?i:University|College|Institute|Academy|School)\s+(?i:of)\s+"
    + _EN_WORD + r"(?:\s+" + _EN_WORD + r"){0,3}"
    r"|\b(?:" + _EN_WORD + r"\s+){1,4}(?i:University|College|Institute|Academy|School)\b"
    r"(?:\s+(?i:of)\s+" + _EN_WORD + r"(?:\s+" + _EN_WORD + r"){0,2})?"
    r"|(?:دانشگاه|دانشکده|مؤسسه|موسسه|آموزشکده|دبیرستان|مدرسه|حوزه\s*علمیه)"
    r"(?:\s+[\u0600-\u06FF]+){0,4}")

KEYWORD_ONLY = re.compile(
    r"(?:دانشگاه|دانشکده|مؤسسه|موسسه|آموزشکده|دبیرستان|مدرسه|حوزه\s*علمیه|"
    r"University|College|Institute|Academy|School)",
    re.IGNORECASE,)

STOP = re.compile(r"\s(?:رشته|گرایش|معدل|GPA)(?!\w)|[\d۰-۹]{4}", re.IGNORECASE)

FIELD_LABEL_REGEX = re.compile(
    r"^\s*(?:field of study|major|field|رشته(?:\s*تحصیلی)?|رشته\s*و\s*گرایش|گرایش)"
    r"\s*[:：\-–]\s*(.+)$",
    re.IGNORECASE,)

PERSIAN_FIELD_REGEX = re.compile(
    r"(?:در\s+)?(?:رشته\s*و\s*گرایش|رشته(?:\s*تحصیلی)?|گرایش)"
    r"\s*(?:[:：\-–]\s*|\s+)([\u0600-\u06FF][\u0600-\u06FF\s،-]{1,70})")

EDU_HEAD = re.compile(
    r"^(?:education|academic|تحصیلات|سوابق\s*تحصیلی|اطلاعات\s*تحصیلی|سوابق\s*آموزشی)",
    re.IGNORECASE,)

END_HEAD = re.compile(
    r"^(?:experience|work\s+experience|professional\s+(?:experience|summary)|"
    r"skills|technical\s+skills|projects?|certifications?|employment|"
    r"مهارت|تجربه|سوابق\s*کاری|پروژه|گواهینامه|افتخارات)",
    re.IGNORECASE,)

def normalize_line(line):
    line = (line.replace("ي", "ی").replace("ك", "ک")
                .replace("\u200c", " ").replace("\u200f", "").replace("\u200e", ""))
    return re.sub(r"\s+", " ", line).strip()

def is_heading(line, rx):
    return len(line.split()) <= 4 and rx.match(line) is not None

def clean_field(value):
    value = re.sub(r"[\(\[]?\s*(?:GPA|معدل)\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[\(\[]?\s*[\d۰-۹]{4}\b.*$", "", value)
    value = re.split(
        r"\b(?:University|College|Institute)\b|دانشگاه|دانشکده|مؤسسه|موسسه|آموزشکده",
        value, flags=re.IGNORECASE)[0]
    return value.strip(" \t,;:|—–-()[]") or None

def clean_institution(text):
    cuts = [DEGREE_REGEX, STOP]
    if not text.isascii():
        cuts.append(FIELD_REGEX)
    for rx in cuts:
        m = rx.search(text, text.find(" ") + 1)
        if m:
            text = text[:m.start()]
    return text.strip(" \t,;:|—–-()") or None

def find_field(text, degree_match):
    for rx in (FIELD_LABEL_REGEX, PERSIAN_FIELD_REGEX):
        m = rx.search(text)
        if m and clean_field(m.group(1)):
            return clean_field(m.group(1))
    if degree_match:
        m = re.search(r"\bin\s+(.+)$", text[degree_match.end():], re.IGNORECASE)
        if m and clean_field(m.group(1)):
            return clean_field(m.group(1))
    m = FIELD_REGEX.search(text)
    return m.group(0).strip() if m else None

def get_section(lines):
    start = next((i + 1 for i, l in enumerate(lines) if is_heading(l, EDU_HEAD)), None)
    if start is None:
        return lines
    end = next((j for j in range(start, len(lines)) if is_heading(lines[j], END_HEAD)),
               len(lines))
    return lines[start:end] or lines

def collect_records(lines):
    records, current = [], {}
    for line in lines:
        found, rest = {}, line
        km = KNOWN_INSTITUTION_REGEX.search(line)
        im = km or INSTITUTION_REGEX.search(line)
        if im:
            name = im.group(0).strip() if km else clean_institution(im.group(0))
            if name and not KEYWORD_ONLY.fullmatch(name):
                found["institution"] = name
                rest = line.replace(name, " ", 1)
        dm = DEGREE_REGEX.search(rest)
        if dm:
            found["degree"] = dm.group(0).strip()
        field = find_field(rest, dm)
        if field:
            found["field"] = field
        if not found:
            continue
        previous_institution = current.get("institution")
        if any(k in current and k in found for k in ("institution", "degree")):
            previous_institution = current.get("institution")
            records.append(current)
            current = {}
            if "degree" in found and "institution" not in found:
                found["institution"] = previous_institution
        elif "degree" in found and "institution" not in found:
            if "institution" not in current and previous_institution:
                current["institution"] = previous_institution
        for key, value in found.items():
            current.setdefault(key, value)
    if current:
        records.append(current)
    return [{"institution": r.get("institution"),
             "field": r.get("field"),
             "degree": r.get("degree")} for r in records]

def extract_education(text):
    lines = [normalize_line(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    section = get_section(lines)
    records = collect_records(section)
    if not records and section is not lines:
        records = collect_records(lines)
    unique, seen = [], set()
    for r in records:
        key = tuple((r[n] or "").casefold() for n in ("institution", "field", "degree"))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique