"""Generate the small Persian sample documents used in the demo.

Run inside Docker (python-docx is installed there):

    docker compose run --rm web python sample_data/generate_samples.py
"""
from pathlib import Path

from docx import Document as DocxDocument

OUTPUT_DIR = Path(__file__).resolve().parent


def build(filename: str, title: str, paragraphs: list[str], table_rows: list[list[str]] | None = None):
    document = DocxDocument()
    document.add_heading(title, level=1)
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    if table_rows:
        table = document.add_table(rows=len(table_rows), cols=len(table_rows[0]))
        table.style = "Table Grid"
        for row_index, row in enumerate(table_rows):
            for column_index, value in enumerate(row):
                table.cell(row_index, column_index).text = value
    path = OUTPUT_DIR / filename
    document.save(path)
    print(f"wrote {path}")


def main() -> None:
    build(
        "01-jangal-iran.docx",
        "جنگل‌های ایران",
        [
            "جنگل‌های ایران از مهم‌ترین منابع طبیعی کشور هستند و نقش بزرگی در حفظ آب و خاک دارند.",
            "جنگل‌های هیرکانی در شمال ایران و در استان‌های گلستان، مازندران و گیلان قرار دارند. این جنگل‌ها بازمانده جنگل‌های کهن هستند و حدود ۱.۹ میلیون هکتار وسعت دارند.",
            "جنگل‌های زاگرس در غرب و جنوب غربی ایران قرار دارند و بیشتر از درختان بلوط تشکیل شده‌اند.",
            "میزان بارندگی سالانه در جنگل‌های شمال ایران بین ۸۰۰ تا ۲۰۰۰ میلی‌متر است.",
            "در این جنگل‌ها حیواناتی مانند خرس قهوه‌ای، گرگ، روباه، گوزن و انواع پرندگان زندگی می‌کنند.",
        ],
        [
            ["جنگل", "منطقه", "ویژگی"],
            ["هیرکانی", "شمال ایران", "کهن و پرباران"],
            ["زاگرس", "غرب ایران", "بلوط"],
        ],
    )

    build(
        "02-tehran.docx",
        "شهر تهران",
        [
            "تهران پایتخت ایران است و در دامنه جنوبی رشته‌کوه البرز قرار دارد.",
            "جمعیت شهر تهران حدود ۹ میلیون نفر و جمعیت استان تهران بیش از ۱۵ میلیون نفر است.",
            "برج میلاد با ارتفاع ۴۳۵ متر بلندترین برج ایران است و در شمال غرب تهران قرار دارد.",
            "متروی تهران دارای ۷ خط است و روزانه میلیون‌ها مسافر را جابه‌جا می‌کند.",
            "فرودگاه بین‌المللی امام خمینی در ۳۵ کیلومتری جنوب تهران قرار دارد.",
        ],
        [
            ["مکان", "ویژگی"],
            ["برج میلاد", "ارتفاع ۴۳۵ متر"],
            ["مترو", "۷ خط"],
            ["فرودگاه امام خمینی", "۳۵ کیلومتری جنوب تهران"],
        ],
    )

    build(
        "03-company-rules.docx",
        "قوانین شرکت",
        [
            "ساعت کاری شرکت از شنبه تا چهارشنبه ۹ تا ۱۷ و پنجشنبه ۹ تا ۱۳ است.",
            "هر کارمند سالانه ۲۶ روز مرخصی استحقاقی دارد.",
            "هر کارمند می‌تواند با هماهنگی مدیر خود حداکثر دو روز در هفته دورکاری کند.",
            "مرخصی استعلاجی تا سه روز بدون گواهی پزشک پذیرفته می‌شود.",
            "درخواست مرخصی باید حداقل ۴۸ ساعت قبل از شروع مرخصی ثبت شود.",
        ],
        [
            ["موضوع", "مقدار"],
            ["مرخصی سالانه", "۲۶ روز"],
            ["دورکاری", "۲ روز در هفته"],
            ["مرخصی استعلاجی", "۳ روز"],
        ],
    )


if __name__ == "__main__":
    main()
