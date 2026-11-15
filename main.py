import streamlit as st
import fitz
import unicodedata
import re
import langdetect
from skills_list import SKILL_ALIASES
from education_extractor import extract_education


st.title("Resume_Analyzer")

files = st.file_uploader("رزومه را انتخاب کنید", type=["pdf"], accept_multiple_files=True)

    
def extract_text(file):
    document = fitz.open(stream=file.getvalue(), filetype="pdf")
    all_words = []
    for page_number, page in enumerate(document):
        words = page.get_text("words")
        for word in words:
            all_words.append((page_number, word))
    document.close()
    return all_words


def detect_language(text):
    try:
        language = langdetect.detect(text)
        if language == "fa":
            return "rtl"
        elif language == "en":
            return "ltr"
        else:
            return "unknown"
    except langdetect.lang_detect_exception.LangDetectException:
        return "unknown"


def split_columns(words, page_width):
    if not words or page_width <= 0:
        return words, []

    width = int(page_width)
    bins = [0] * (width + 1)

    for word in words:
        x0 = max(0, int(word[0]))
        x1 = min(width, int(word[2]))

        for x in range(x0, x1):
            bins[x] += 1

    min_gap = max(20, int(width * 0.04))
    line_groups = {}

    for word in words:
        key = (word[5], word[6])
        line_groups.setdefault(key, []).append(word)

    candidates = []

    for boundary in range(int(width * 0.30), int(width * 0.70)):
        left_lines = 0
        right_lines = 0
        crossing_lines = 0

        for line in line_groups.values():
            line_x0 = min(word[0] for word in line)
            line_x1 = max(word[2] for word in line)

            if line_x0 < boundary < line_x1:
                crossing_lines += 1
            elif line_x1 <= boundary:
                left_lines += 1
            elif line_x0 >= boundary:
                right_lines += 1

        if left_lines < 2 or right_lines < 2:
            continue

        if crossing_lines > 3:
            continue

        start = max(0, boundary - min_gap // 2)
        end = min(width, boundary + min_gap // 2)

        occupied = sum(1 for x in range(start, end) if bins[x] > 0)
        gap_score = (end - start) - occupied

        candidates.append((gap_score, -crossing_lines, boundary))

    if not candidates:
        return words, []

    best_score = max(candidates)
    boundary = best_score[2]

    left = []
    right = []

    for word in words:
        x0, x1 = word[0], word[2]

        if x1 <= boundary:
            left.append(word)
        elif x0 >= boundary:
            right.append(word)
        elif boundary - x0 >= x1 - boundary:
            left.append(word)
        else:
            right.append(word)

    if not left or not right:
        return words, []

    return left, right

def build_lines(words):

    lines = {}

    for word in words:
        block_number = word[5]
        line_number = word[6]
        key = (block_number, line_number)

        if key not in lines:
            lines[key] = []
        lines[key].append(word)

    result = []

    for key, words_in_line in lines.items():
        if all(word[4].isascii() for word in words_in_line):
            words_in_line.sort(key = lambda word :word[0])
        else:
            words_in_line.sort(key = lambda word :word[0], reverse = True)
        words_text = [word[4] for word in words_in_line]
        line_text = " ".join(words_text)
        x = words_in_line[0][0]
        y = words_in_line[0][1]
        result.append((x, y, line_text))
    result.sort(key=lambda line: (line[1], -line[0]))
    
    return result

def clean_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200c", " ")
    text = re.sub(r"[^\w\s.,،@()+\-/:#_;!?%&'-=()\[\]{}<>|]","", text)
    cleaned_lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", line)
        line = re.sub(r"،\s*([\u0600-\u06FF]+)", r"\1،", line)
        line = re.sub(r"\s+([.,:;!?])", r"\1", line)
        line = line.strip()
        cleaned_lines.append(line)
    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result


def extract_email(text):
    email_pattern = r'[\w.-]+@[\w.-]+\.\w+'
    match = re.search(email_pattern, text)
    if match:
        return match.group()
    return None


def extract_phone(text):
    normalized = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩","01234567890123456789"))
    phone_pattern = (r"(?<!\w)\+?\d(?:[\d\s().-]*\d)?(?!\w)")
    candidates = re.findall(phone_pattern, normalized)
    valid_candidates = []
    for candidate in candidates:
        digits = re.sub(r"\D", "", candidate)
        if not 7 <= len(digits) <= 15:
            continue
        if len(set(digits)) == 1:
            continue
        valid_candidates.append(candidate.strip())
    if not valid_candidates:
        return None
    valid_candidates.sort(
        key=lambda value: (
            len(re.sub(r"\D", "", value)),
            bool(re.search(r"[().+]|-", value))),
        reverse=True)
    return valid_candidates[0]


def extract_skills(text):
    found_skills = []
    match = re.search(
        r"(?:^|\n)\s*(?:"
        r"skills|technical\s+skills|"
        r"مهارت‌ها|مهارت ها|"
        r"مهارت‌های فنی|مهارت های فنی"
        r")\s*:?\s*(.*?)"
        r"(?=\n\s*(?:"
        r"education|experience|work experience|"
        r"projects|certifications|summary|languages|"
        r"professional summary|"
        r"تحصیلات|سوابق کاری|تجربه کاری|"
        r"پروژه‌ها|پروژه ها|گواهینامه‌ها|"
        r"خلاصه رزومه|خلاصه حرفه‌ای|"
        r"زبان‌ها|زبان ها"
        r")\s*:?\s*(?:\n|$)|\Z)",
        text, re.IGNORECASE | re.DOTALL)
    skills_text = match.group(1) if match else text
    for skill, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
            if re.search(pattern, skills_text, re.IGNORECASE):
                found_skills.append(skill)
                break
    return found_skills


def extract_persian_resume(file):
    data = extract_text(file)
    raw_text = " ".join(word[4] for page_number, word in data)
    pages = {}
    for page_number, word in data:
        if page_number not in pages:
            pages[page_number] = []
        pages[page_number].append(word)
    cleaned_lines = []
    for page_number, words in pages.items():
        page_width = max(word[2] for word in words)
        first_column, second_column = split_columns(words,page_width)
        first_lines = build_lines(first_column)
        second_lines = build_lines(second_column)
        all_lines = first_lines + second_lines
        for x, y, line in all_lines:
            cleaned_line = clean_text(line)
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
    cleaned_text = "\n".join(cleaned_lines)
    return {
        "filename": file.name,
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "contact": {
            "email": extract_email(cleaned_text),
            "phone": extract_phone(cleaned_text)},
        "skills": extract_skills(cleaned_text),
        "education": extract_education(cleaned_text)}


def extract_english_resume(file):
    document = fitz.open(stream=file.getvalue(),filetype="pdf")
    page_texts = []
    for page in document:
        words = page.get_text("words")
        left_words, right_words = split_columns(words, page.rect.width)
        if not right_words:
            page_texts.append(page.get_text("text", sort=True))
            continue
        columns = [left_words, right_words]
        column_texts = []
        for column in columns:
            lines = {}
            for word in column:
                key = (word[5], word[6])
                lines.setdefault(key, []).append(word)
            ordered_lines = sorted(
                lines.values(),
                key=lambda line: (min(word[1] for word in line), min(word[0] for word in line))
            )
            column_texts.append(
                "\n".join(
                    " ".join(word[4] for word in sorted(line, key=lambda word: word[0]))
                    for line in ordered_lines
                )
            )
        page_texts.append("\n".join(column_texts))
    document.close()
    raw_text = "\n".join(page_texts)
    cleaned_text = clean_text(raw_text)
    return {
        "filename": file.name,
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "contact": {
            "email": extract_email(cleaned_text),
            "phone": extract_phone(cleaned_text)},
        "skills": extract_skills(cleaned_text),
        "education": extract_education(cleaned_text)}


job_data = {}
if "job_data" not in st.session_state:
    st.session_state.job_data = {}
st.subheader("موقعیت شغلی")
with st.expander("تعریف موقعیت شغلی"):
    with st.form("job_form"):
        job_data["title"] = st.text_input("عنوان شغلی")
        job_data["age"] = st.text_input("سن")
        job_data["work_location"] = st.text_input("محل کار")
        job_data["residence"] = st.text_input("محل زندگی")
        job_data["gender"] = st.text_input("جنسیت")
        job_data["experience"] = st.text_input("سابقه کاری")
        job_data["skills"] = st.text_input("مهارت‌های موردنیاز", placeholder="Python, Django, SQL")
        job_data["education"] = st.text_input("تحصیلات مورد نیاز")
        job_data["military_status"] = st.text_input("شرط سربازی")
        job_data["employment_type"] = st.text_input("نوع همکاری")
        job_data["salary"] = st.text_input("حقوق")
        job_data["working_hours"] = st.text_input("ساعات کاری")
        job_data["benefits"] = st.text_input("تسهیلات و مزایا")
        job_data["explanation"] = st.text_input("توضیحات")
        submitted = st.form_submit_button("ثبت موقعیت شغلی")
    if submitted:
        if not job_data["title"].strip():
            st.error("عنوان شغلی را وارد کنید.")
        else:
            st.session_state.job_data = job_data.copy()
            st.success("اطلاعات موقعیت شغلی ثبت شد.")
            st.json(st.session_state.job_data)

def normalize_skills(skills):
    normalized_skills = []

    if isinstance(skills, str):
        skills = skills.split(",")

    for skill in skills:
        skill = skill.strip().casefold()

        for standard_name, aliases in SKILL_ALIASES.items():
            all_names = [standard_name] + aliases

            if skill in [name.casefold() for name in all_names]:
                normalized_skills.append(standard_name)
                break

    return sorted(set(normalized_skills))


def compare_skills(resume_data, job_data):
    resume_skills = resume_data["skills"]
    required_skills = job_data["skills"]
    required_skills = normalize_skills(required_skills)
    matched_skills = sorted(set(resume_skills) & set(required_skills))
    missing_skills = sorted(set(required_skills) - set(resume_skills))
    if not required_skills:
        match_score = None
    else:
        match_score = round(len(matched_skills) / len(required_skills) * 100, 1)
    return {"matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "match_score": match_score}

match_result = []

resume_results = []

if files:
    st.subheader("خروجی رزومه ها")
    for file in files:
        detection_data = extract_text(file)
        detection_text = " ".join(word[4] for page_number, word in detection_data)
        language = detect_language(detection_text)
        if language == "rtl":
            resume_data = extract_persian_resume(file)
        elif language == "ltr":
            resume_data = extract_english_resume(file)
        else:
            st.warning(
                "زبان رزومه تشخیص داده نشد. " 
                "لطفاً متن PDF را بررسی کنید.")
            continue
        
        job_data = st.session_state.get("job_data")
        comparison = None
        if job_data:
            comparison = compare_skills(resume_data, job_data)
            match_result.append({
    "نام فایل": resume_data["filename"],
    "مهارت‌های شناسایی‌شده": ", ".join(resume_data["skills"]),
    "مهارت‌های موجود": ", ".join(comparison["matched_skills"]),
    "مهارت های یافت نشده": ", ".join(comparison["missing_skills"]),
    "امتیاز تطابق": (f'{comparison["match_score"]}%'
        if comparison["match_score"] is not None
        else "محاسبه‌نشده")})
        
        resume_results.append({"resume_data": resume_data, "comparison": comparison}) 


for item in resume_results:
    resume = item["resume_data"]
    with st.expander(resume["filename"]):

        st.subheader("اطلاعات تماس")
        st.write(resume["contact"])

        st.subheader("تحصیلات")
        st.write(resume["education"])

        st.subheader("مهارت‌ها")
        st.write(resume["skills"])

        st.subheader("متن تمیزشده")
        st.text(resume["cleaned_text"])

        st.subheader("متن خام")
        st.text(resume["raw_text"])

if match_result:
    match_result.sort(key=lambda x: float(x["امتیاز تطابق"].replace("%", "")), reverse=True)
    st.subheader("نتایج مقایسه مهارت‌ها")
    st.dataframe(match_result, use_container_width=True)
