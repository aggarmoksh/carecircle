"""Fixed message templates per language (en, hi, es) for the system messages. Code fills the slots; no model rephrases these.
Hindi time rule: 12-hour clock with a time word (05:00-11:59 सुबह, 12:00-15:59 दोपहर, 16:00-20:59 शाम, 21:00-04:59 रात); never 24-hour.
Spanish: 'las 8 de la mañana' (05-11), 'las 3 de la tarde' (12-19), 'las 8 de la noche' (20-04).
Medicine names always stay in Latin letters exactly as in the record.
render(kind, lang, **slots): slots are raw values (time 'HH:MM', meds [names], date 'YYYY-MM-DD', day 'WED', part 'AM'|'PM'); the language forms are made here."""
from datetime import date

HI_DAYS = {"MON": "सोमवार", "TUE": "मंगलवार", "WED": "बुधवार", "THU": "गुरुवार", "FRI": "शुक्रवार", "SAT": "शनिवार", "SUN": "रविवार"}
ES_DAYS = {"MON": "lunes", "TUE": "martes", "WED": "miércoles", "THU": "jueves", "FRI": "viernes", "SAT": "sábado", "SUN": "domingo"}
EN_DAYS = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday"}
HI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
ES_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _hm(t):
    h, m = (int(x) for x in t.split(":"))
    return h, m, (h % 12) or 12


def en_time(t):
    h, m, hh = _hm(t)
    return f"{hh}{':%02d' % m if m else ''} {'AM' if h < 12 else 'PM'}"


def hi_time(t):
    h, m, hh = _hm(t)
    word = "सुबह" if 5 <= h < 12 else "दोपहर" if 12 <= h < 16 else "शाम" if 16 <= h < 21 else "रात"
    return f"{word} {hh}{':%02d' % m if m else ''} बजे"


def es_time(t):
    h, m, hh = _hm(t)
    part = "mañana" if 5 <= h < 12 else "tarde" if 12 <= h < 20 else "noche"
    return f"{'la' if hh == 1 else 'las'} {hh}{':%02d' % m if m else ''} de la {part}"


def _list(names, lang):
    names = list(names)
    if len(names) < 2:
        return "".join(names)
    return ", ".join(names[:-1]) + {"hi": " और ", "es": " y "}.get(lang, ", ") + names[-1]


def _date(iso, lang):
    d = date.fromisoformat(iso)
    return {"hi": f"{d.day} {HI_MONTHS[d.month - 1]}", "es": f"{d.day} de {ES_MONTHS[d.month - 1]}"}.get(lang, f"{d.day} {d.strftime('%b')}")


def _link(lang, link):
    return f" Board (optional): {link}" if link else ""


# ---- English: the wording the system has always used ----
def _en(kind, s):
    P = s.get("patient", "Nanaji")
    meds = s.get("meds") or []
    if kind == "nudge":
        if len(meds) == 1:
            return f"CareCircle: {meds[0]} {s['time']} for {P} isn't confirmed yet. If it has been given, reply 'done' or send a voice note."
        return f"Hi {s['name']}, has {P} had his {en_time(s['time'])} medicines: {_list(meds, 'en')}? Reply done, or tell me which ones."
    if kind == "escalate":
        if len(meds) == 1:
            return f"CareCircle: {s['first']} hasn't confirmed {meds[0]} {s['time']} for {P} yet. Can you check and tell me?"
        return f"CareCircle: {s['first']} hasn't confirmed the {en_time(s['time'])} medicines for {P} yet ({_list(meds, 'en')}). Can you check and tell me?"
    if kind == "relay_given":
        return f"CareCircle: {s['giver']} gave {_list(meds, 'en')} {s['time']}."
    if kind == "missed":
        return f"CareCircle: {_list(meds, 'en')} {s['time']} for {P} is recorded as missed."
    if kind == "organiser_missed":
        return f"{EN_DAYS[s['day']]} {s['part']} is still full in the organiser: that dose wasn't given."
    if kind == "schedule_live":
        return f"{s['giver']} confirmed the schedule for {P}: {s['n']} medicine(s) are now live."
    if kind == "lab_added":
        return f"{s['member']} added a lab report from {_date(s['date'], 'en')}: {s['n']} values are outside the lab's printed range. See the board." + (f" Board (optional): {s['link']}" if s.get("link") else "")
    if kind == "daily_header":
        return "CareCircle daily summary:"
    if kind == "logged":
        return f"Logged: {_list(meds, 'en')} {s['time']} given ({s['giver']}). Thanks."
    if kind == "today_caption":
        return f"Today for {P}." + _link(None, s.get("link"))
    if kind == "board_line":
        return f"Board (optional): {s['link']}"
    raise KeyError(kind)


def _hi(kind, s):
    P = s.get("patient", "Nanaji")
    meds, t = _list(s.get("meds") or [], "hi"), hi_time(s["time"]) if s.get("time") else ""
    if kind == "nudge":
        return f"नमस्ते {s['name']}, क्या {P} ने {t} वाली {meds} दवा ले ली? 'done' लिखें, या बताएं कौन सी ली।"
    if kind == "escalate":
        return f"{s['first']} ने {P} की {t} वाली {meds} दवा की पुष्टि नहीं की है। क्या आप देखकर बता सकते हैं?"
    if kind == "relay_given":
        return f"{s['giver']} ने {P} को {t} वाली {meds} दवा दे दी ({hi_time(s['clock'])})."
    if kind == "missed":
        return f"{P} की {t} वाली {meds} दवा की पुष्टि नहीं हुई।"
    if kind == "organiser_missed":
        return f"दवा के डिब्बे में {HI_DAYS[s['day']]} {'सुबह' if s['part'] == 'AM' else 'शाम'} वाला हिस्सा अभी भरा है: वह दवा नहीं दी गई।"
    if kind == "schedule_live":
        return f"{s['giver']} ने {P} की दवाओं की सूची पक्की कर दी: {s['n']} दवाएं शुरू हो गई हैं।"
    if kind == "lab_added":
        return f"{s['member']} ने {_date(s['date'], 'hi')} की लैब रिपोर्ट जोड़ी: {s['n']} नतीजे लैब की छपी हुई रेंज से बाहर हैं।" + (f" बोर्ड पर देखें: {s['link']}" if s.get("link") else "")
    if kind == "daily_header":
        return "CareCircle का दैनिक सारांश:"
    if kind == "logged":
        return f"दर्ज हो गया: {t} वाली {meds} दवा दी गई ({s['giver']})। धन्यवाद।"
    if kind == "today_caption":
        return f"आज की स्थिति, {P}।" + (f" बोर्ड (वैकल्पिक): {s['link']}" if s.get("link") else "")
    if kind == "board_line":
        return f"बोर्ड (वैकल्पिक): {s['link']}"
    raise KeyError(kind)


def _es(kind, s):
    P = s.get("patient", "Nanaji")
    meds, t = _list(s.get("meds") or [], "es"), es_time(s["time"]) if s.get("time") else ""
    if kind == "nudge":
        return f"Hola {s['name']}, ¿{P} ya tomó {meds} de {t}? Responde «done» o dime cuáles tomó."
    if kind == "escalate":
        return f"{s['first']} aún no ha confirmado que {P} tomó {meds} de {t}. ¿Puedes revisar y avisarme?"
    if kind == "relay_given":
        return f"{s['giver']} le dio a {P} {meds} de {t} ({es_time(s['clock'])})."
    if kind == "missed":
        return f"No consta que {P} haya tomado {meds} de {t}."
    if kind == "organiser_missed":
        return f"En el pastillero, el compartimento de {ES_DAYS[s['day']]} por la {'mañana' if s['part'] == 'AM' else 'tarde'} sigue lleno: esa dosis no se dio."
    if kind == "schedule_live":
        return f"{s['giver']} confirmó la lista de medicamentos de {P}: {s['n']} medicamentos activos."
    if kind == "lab_added":
        return f"{s['member']} añadió un análisis del {_date(s['date'], 'es')}: {s['n']} valores están fuera del rango impreso del laboratorio." + (f" Míralo en el tablero: {s['link']}" if s.get("link") else "")
    if kind == "daily_header":
        return "Resumen diario de CareCircle:"
    if kind == "logged":
        return f"Registrado: {meds} de {t} ({s['giver']}). Gracias."
    if kind == "today_caption":
        return f"Hoy, {P}." + (f" Tablero (opcional): {s['link']}" if s.get("link") else "")
    if kind == "board_line":
        return f"Tablero (opcional): {s['link']}"
    raise KeyError(kind)


FIXED = {  # fixed replies, written by hand in each language (never rephrased by the model)
    "medical": {"en": "I can't give medical advice. I've noted this as a question for the doctor visit. Who will ask the doctor? Reply 'I will' to take it.",
                "hi": "मैं चिकित्सा सलाह नहीं दे सकता। इसे डॉक्टर से मिलने के लिए सवाल के रूप में लिख लिया है। डॉक्टर से कौन पूछेगा? लेने के लिए 'I will' लिखें।",
                "es": "No puedo dar consejos médicos. Lo anoté como pregunta para la consulta con el médico. ¿Quién se lo preguntará al médico? Responde «I will» para encargarte."},
    "urgent": {"en": "This sounds urgent. Please call your local emergency services or the doctor right now. I can't assess symptoms.",
               "hi": "यह जरूरी लगता है। कृपया अभी अपने इलाके की आपातकालीन सेवा या डॉक्टर को फोन करें। मैं लक्षणों की जांच नहीं कर सकता।",
               "es": "Esto parece urgente. Llama ahora mismo a los servicios de emergencia de tu zona o al médico. No puedo evaluar síntomas."},
}


def render(kind, lang, **slots):
    return {"hi": _hi, "es": _es}.get(lang, _en)(kind, slots)


def fixed(kind, lang):
    return FIXED[kind].get(lang, FIXED[kind]["en"])


KINDS = ["nudge", "escalate", "relay_given", "missed", "organiser_missed", "schedule_live", "lab_added", "daily_header", "logged", "today_caption", "board_line"]
