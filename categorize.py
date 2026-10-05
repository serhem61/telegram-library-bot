"""تصنيف احترافي مبسّط (مستوحى من Dewey) من Bookshelves و Subjects الخاصة بـ Gutenberg."""

# (كلمات مفتاحية إنجليزية بالترتيب) → تصنيف عربي
RULES = [
    (("philosophy", "stoic", "ethics", "logic", "metaphysics"), "فلسفة"),
    (("religion", "bible", "christian", "theology", "mythology", "quran"), "دين"),
    (("history", "war", "napoleonic", "civil war", "revolution"), "تاريخ"),
    (("physics", "chemistry", "biology", "astronomy", "mathematics", "science"), "علوم"),
    (("detective", "mystery", "crime"), "روايات بوليسية"),
    (("science fiction", "fantasy", "horror", "gothic"), "خيال علمي وفانتازيا"),
    (("novel", "fiction", "short stor", "humorous stories"), "روايات"),
    (("poetry", "poems", "verse"), "شعر"),
    (("drama", "plays", "tragedy", "comedy"), "مسرح"),
    (("biograph", "autobiograph", "memoir"), "سير وتراجم"),
    (("politics", "government", "democracy", "law", "constitution"), "سياسة وقانون"),
    (("economics", "finance", "wealth", "capital"), "اقتصاد"),
    (("psychology", "psychoanalysis"), "علم نفس"),
    (("education", "teaching", "school"), "تربية وتعليم"),
    (("language", "linguistic", "grammar", "dictionary"), "لغات"),
    (("art", "music", "painting", "architecture"), "فنون"),
    (("children", "young reader", "fairy tales", "fables"), "أطفال وناشئة"),
    (("travel", "geography", "voyages", "exploration"), "جغرافيا ورحلات"),
    (("medicine", "health", "disease"), "صحة وطب"),
    (("technology", "engineering", "invention"), "تقنية"),
    (("essay", "letter", "journalism", "humor"), "أدب ومقالات"),
]


def classify(bookshelves=None, subjects=None) -> str:
    text = " | ".join([*(bookshelves or []), *(subjects or [])]).lower()
    for keys, cat in RULES:
        if any(k in text for k in keys):
            return cat
    return "عام"
