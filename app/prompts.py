"""Pure constants: extraction prompts and strict schemas (no imports with side effects, no file reads)."""
TYPES = ["discharge_sheet", "prescription", "pill_organiser", "lab_report", "other"]
DOSE_UNITS = ["mg", "mcg", "g", "mL", "units", "tablet", "puff", "drop", "tsf", "tbsp", "sachet", "other"]
FREQS = ["once_daily", "twice_daily", "three_times_daily", "four_times_daily", "every_n_hours", "at_bedtime", "as_needed", "weekly"]
FOOD = ["yes", "no", "unspecified"]
SLOTS14 = [f"{d}_{p}" for d in "MON TUE WED THU FRI SAT SUN".split() for p in ("AM", "PM")]

CLASSIFY_SCHEMA = {"name": "image_type", "schema": {"type": "object", "additionalProperties": False, "required": ["type", "confidence", "has_handwriting"],
                   "properties": {"type": {"type": "string", "enum": TYPES}, "confidence": {"type": "number"}, "has_handwriting": {"type": "boolean"}}}}
CLASSIFY_PROMPT = ("Classify this image sent to a family care app. Choose one type: discharge_sheet (a hospital discharge summary or medicine list), "
                   "prescription, pill_organiser (a weekly pill box with compartments), lab_report (test results), other. "
                   "Give a confidence from 0 to 1. has_handwriting = true if any of the writing on the page is handwritten (pen or pencil), false if everything is printed. Do not read out or interpret any content.")

EXTRACT_SCHEMA = {"name": "discharge_sheet", "schema": {
    "type": "object", "additionalProperties": False, "required": ["meds"],
    "properties": {"meds": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["name", "name_as_printed", "generic_if_printed", "legibility", "dose_amount", "dose_unit", "unit_as_printed", "frequency", "times", "with_food", "notes"],
        "properties": {"name": {"type": "string"}, "name_as_printed": {"type": "string"}, "generic_if_printed": {"type": "string"},
                       "legibility": {"type": "string", "enum": ["clear", "unsure"]}, "dose_amount": {"type": "number"}, "dose_unit": {"type": "string", "enum": DOSE_UNITS}, "unit_as_printed": {"type": "string"},
                       "frequency": {"type": "string", "enum": FREQS}, "times": {"type": "array", "items": {"type": "string"}},
                       "with_food": {"type": "string", "enum": FOOD}, "notes": {"type": "string"}}}}}}}
EXTRACT_PROMPT = (
    "This is a photo of a fictional discharge sheet. Extract every medicine listed on it as structured data. "
    "Rules: name = generic drug name exactly as printed, lowercase (if only a brand is printed, copy the brand as printed). "
    "name_as_printed = the medicine name exactly as written on the sheet, including a brand name. generic_if_printed = the generic name only if the sheet prints one "
    "next to the brand, otherwise an empty string; never fill it from your own knowledge. "
    "legibility = clear if you can read the name, dose and frequency with confidence, otherwise unsure (handwriting, smudges, cut-off text). "
    "dose_amount = number only. dose_unit = the unit exactly as printed (tsf = teaspoon, tbsp = tablespoon, sachet); NEVER convert one unit into another (2 TSF stays 2 tsf, never mL). If the printed unit is not in the list, use other and put the unit in unit_as_printed; otherwise unit_as_printed is an empty string. "
    "times = clock times in HH:MM 24h ONLY if the sheet prints clock times; otherwise an empty list. Never invent or infer times. "
    "with_food: yes = with or after food; no = before food or empty stomach; unspecified = the sheet says nothing. "
    "A medicine that is crossed out or marked STOP is not listed. notes = any extra instruction text as printed. "
    "Copy what is printed; give no medical advice and add nothing that is not on the sheet.")


LAB_SCHEMA = {"name": "lab_report", "schema": {
    "type": "object", "additionalProperties": False, "required": ["lab", "report_date", "tests"],
    "properties": {
        "lab": {"type": "string"}, "report_date": {"type": "string"},
        "tests": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["test", "value", "unit", "range_text", "range_low", "range_high", "printed_flag"],
            "properties": {"test": {"type": "string"}, "value": {"type": "number"}, "unit": {"type": "string"},
                           "range_text": {"type": "string"}, "range_low": {"type": ["number", "null"]}, "range_high": {"type": ["number", "null"]},
                           "printed_flag": {"type": "string"}}}}}}}
LAB_PROMPT = (
    "This is a photo of a fictional lab report: a table with columns Test, Result, Unit, Reference range, Flag. The photo may be tilted, "
    "so follow each row's lines to keep every value with its own test. Copy what is printed, row by row, and nothing else. "
    "lab = the laboratory name at the top. report_date = the report date as YYYY-MM-DD. "
    "For each row: test = the test name as printed, lowercase. value = the printed result as a plain number (no thousands separators). "
    "unit = the printed unit exactly. range_text = the text in the Reference range column exactly as printed, or an empty string if that cell is blank. "
    "range_low / range_high = the numbers in range_text (null where range_text has no lower or no upper bound, and both null if range_text is empty). "
    "printed_flag = the letter printed in the Flag column (for example H or L), or an empty string if that cell is blank. "
    "Never invent, fill in or recall a reference range or a flag that is not printed on this page. Do not judge, explain or interpret any value.")

